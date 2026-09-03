"""Explicit orchestration: route, plan, retrieve, support, generate, validate."""

from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from uuid import uuid4

from firelens.answering.adaptive_retrieval import refine_if_needed
from firelens.answering.capability_execution import (
    bind_quote_candidates,
    bind_retrieval_bundle,
    capability_query_plan,
)
from firelens.answering.context import (
    EvidenceIndex,
    build_evidence_packet,
    decide_support,
)
from firelens.answering.execution import (
    AskExecution as AskExecution,
)
from firelens.answering.execution import (
    ExecutionObservation,
    ExecutionObserver,
    SearchExecution,
)
from firelens.answering.grounded import (
    GroundedAnswerEngine,
    compile_without_generation,
)
from firelens.answering.intent import (
    SUGGESTED_QUESTIONS,
    TOPIC_CATALOGUE,
    apply_planning_decision,
    plan_query,
    publication_question,
    resolved_user_question,
    reviewed_guidance_plan,
    skips_provider_planning,
)
from firelens.answering.live_request_intent import uses_selected_live_binding
from firelens.answering.planner import planning_messages, planning_schema
from firelens.answering.product_scope import SCOPE_NOTE, is_outside_wildfire_scope
from firelens.answering.responses import (
    conflict_response as _conflict_response,
)
from firelens.answering.responses import (
    safe_abstention as _safe_abstention,
)
from firelens.answering.responses import (
    unavailable_response as _unavailable_response,
)
from firelens.answering.scope import (
    candidate_contains_identifier as _candidate_contains_identifier,
)
from firelens.answering.scope import (
    candidate_source_reference_present as _candidate_source_reference_present,
)
from firelens.answering.scope import (
    mixed_scope_request as _mixed_scope_request,
)
from firelens.answering.service_support import (
    StaticRAGSupport,
    is_personalized_conditional_request,
)
from firelens.answering.service_support import (
    with_support_limitations as _with_support_limitations,
)
from firelens.answering.typed_snapshot import extract_snapshot
from firelens.claim_trust import GROUNDED_PUBLIC_WORDING
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    EvidencePacket,
    PlanningResponse,
    QueryPlan,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    RetrievalBundle,
    SearchResponse,
    SupportDecision,
    SupportStatus,
)
from firelens.errors import ProviderError
from firelens.guidance_capabilities import CapabilityBinding, resolve_capability
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.publication.fallback import official_handoff_response
from firelens.retrieval.bm25 import BM25Index
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.traces import TraceRecorder


class StaticRAGService(StaticRAGSupport):
    def __init__(
        self,
        chunks: Sequence[ChunkRecord],
        *,
        corpus_version: str,
        retrieval: RetrievalPipeline,
        provider: AIProvider,
        config: FireLensConfig,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.chunks = tuple(chunks)
        self.evidence_index = EvidenceIndex.from_chunks(self.chunks)
        self.corpus_version = corpus_version
        self.planning_index = BM25Index(self.chunks)
        self.retrieval = retrieval
        self.provider = provider
        self.grounded_answers = GroundedAnswerEngine(provider)
        self._active_operations: dict[str, tuple[float, tuple[str, ...]]] = {}
        self.config = config
        self.trace_recorder = trace_recorder or TraceRecorder(
            config.trace_dir,
            include_content=config.trace_content,
            max_files=config.trace_max_files,
            max_bytes=config.trace_max_bytes,
        )

    async def _retrieve_for_plan(
        self,
        plan: QueryPlan,
        request: QueryRequest,
        *,
        planning: PlanningResponse | None,
        planning_ms: float,
        capability: CapabilityBinding | None = None,
    ) -> tuple[RetrievalBundle, EvidencePacket]:
        bundle = (
            RetrievalBundle()
            if capability is not None and capability.source_mode == "corpus"
            else await self.retrieval.search(plan)
        )
        if planning is not None:
            bundle.provider_usage["planning"] = planning.usage
            bundle.provider_attempts["planning"] = planning.attempts
            bundle.provider_models["planning"] = planning.model
        bundle.timings_ms["planning"] = planning_ms
        packet_hits = tuple(bundle.reranked_hits)
        coverage_hits = tuple(bundle.fused_hits)
        if capability is not None and capability.source_mode == "corpus":
            bundle, packet_hits = bind_retrieval_bundle(
                bundle,
                capability,
                self.evidence_index.by_id,
            )
            coverage_hits = packet_hits
        request_queries = tuple(item.query for item in plan.retrieval_requests)
        packet = build_evidence_packet(
            plan.normalized_question,
            packet_hits,
            self.chunks,
            corpus_version=self.corpus_version,
            config=self.config,
            evidence_index=self.evidence_index,
            selection_aspects=tuple(dict.fromkeys([*plan.required_aspects, *request_queries])),
            coverage_hits=coverage_hits,
        )
        if capability is not None and capability.source_mode == "corpus":
            packet = bind_quote_candidates(packet, capability)
        if self.config.retrieval_strategy == "adaptive_v1":
            refined = await refine_if_needed(
                plan=plan,
                request_queries=request_queries,
                first_bundle=bundle,
                first_packet=packet,
                chunks=self.chunks,
                corpus_version=self.corpus_version,
                config=self.config,
                searcher=self.retrieval,
                evidence_index=self.evidence_index,
            )
            return refined.bundle, refined.packet
        return bundle, packet

    async def execute_search(
        self,
        request: QueryRequest,
        *,
        trace_id: str | None = None,
        allow_live: bool = True,
    ) -> SearchExecution:
        active_trace_id = trace_id or uuid4().hex
        plan = plan_query(request, allow_live=allow_live)
        planning: PlanningResponse | None = None
        packet: EvidencePacket | None = None
        place_label = request.location.label if request.location is not None else None
        capability = resolve_capability(request.question, place_label=place_label)

        if (
            plan.route == QueryRoute.RELATED
            and capability is not None
            and capability.source_mode == "corpus"
        ):
            plan = capability_query_plan(plan, capability)
            bundle, packet = await self._retrieve_for_plan(
                plan,
                request,
                planning=None,
                planning_ms=0.0,
                capability=capability,
            )
        elif plan.route == QueryRoute.RELATED and skips_provider_planning(request):
            resolved = resolved_user_question(request)
            if resolved != plan.normalized_question:
                plan = plan.model_copy(update={"normalized_question": resolved})
            plan = reviewed_guidance_plan(plan)
            bundle, packet = await self._retrieve_for_plan(
                plan,
                request,
                planning=None,
                planning_ms=0.0,
            )
        elif plan.route == QueryRoute.RELATED:
            planning_started = perf_counter()
            planning_candidates = self._planning_candidates(plan.normalized_question)
            planning_request = request.model_copy(update={"question": plan.normalized_question})
            mixed_scope = False
            try:
                planning = await self.provider.plan(
                    planning_messages(planning_request, corpus_candidates=planning_candidates),
                    output_schema=planning_schema(),
                )
                if _mixed_scope_request(request.question, planning_candidates):
                    mixed_scope = True
                    planning = planning.model_copy(
                        update={
                            "decision": planning.decision.model_copy(
                                update={
                                    "relation": QueryRelation.TANGENT,
                                    "retrieval_queries": [],
                                    "required_aspects": [],
                                    "explanation": (
                                        "The request mixes a corpus-supported clause with an "
                                        "unrelated clause and must be asked as a focused question."
                                    ),
                                }
                            )
                        }
                    )
                elif planning.decision.relation in {
                    QueryRelation.TANGENT,
                    QueryRelation.ADJACENT,
                } and (
                    _candidate_contains_identifier(request.question, planning_candidates)
                    or self._planning_identifier_present(request.question)
                    or _candidate_source_reference_present(
                        request.question, planning_candidates
                    )
                ):
                    planning = planning.model_copy(
                        update={
                            "decision": planning.decision.model_copy(
                                update={
                                    "relation": QueryRelation.GROUNDED_CANDIDATE,
                                    "retrieval_queries": [request.question],
                                    "required_aspects": [request.question],
                                    "explanation": (
                                        "A reviewed guidance topic or explicit source reference "
                                        "appears in the current corpus preflight."
                                    ),
                                }
                            )
                        }
                    )
                plan = (
                    plan.model_copy(
                        update={
                            "route": QueryRoute.TANGENT,
                            "relation": QueryRelation.TANGENT,
                            "retrieval_requests": [],
                            "required_aspects": [],
                        }
                    )
                    if mixed_scope
                    else apply_planning_decision(plan, planning.decision)
                )
            except ProviderError as exc:
                planning_ms = (perf_counter() - planning_started) * 1_000
                bundle = RetrievalBundle(
                    complete=False,
                    errors=[exc.kind.value],
                    timings_ms={"planning": planning_ms},
                )
            else:
                if plan.retrieval_requests:
                    bundle, packet = await self._retrieve_for_plan(
                        plan,
                        request,
                        planning=planning,
                        planning_ms=(perf_counter() - planning_started) * 1_000,
                    )
                else:
                    bundle = RetrievalBundle()
        else:
            bundle = RetrievalBundle()

        support = decide_support(plan, packet, bundle)
        response = SearchResponse(
            trace_id=active_trace_id,
            plan=plan,
            retrieval=bundle,
            evidence=[] if packet is None else packet.items,
            support=support,
        )
        await self.trace_recorder.record(
            active_trace_id,
            question=request.question,
            payload={
                "operation": "search",
                "route": plan.route.value,
                "relation": plan.relation.value if plan.relation else None,
                "support": support.status.value,
                "history_turn_count": len(request.history),
                "stage_counts": {
                    "bm25": len(bundle.bm25_hits),
                    "vector": len(bundle.vector_hits),
                    "fused": len(bundle.fused_hits),
                    "reranked": len(bundle.reranked_hits),
                    "evidence": len(response.evidence),
                },
                "stage_rankings": {
                    **bundle.rankings,
                    "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
                    "vector": [hit.chunk_id for hit in bundle.vector_hits],
                    "fused": [hit.chunk_id for hit in bundle.fused_hits],
                    "reranked": [hit.chunk_id for hit in bundle.reranked_hits],
                    "evidence": [item.evidence_id for item in response.evidence],
                },
                "versions": {
                    "corpus": self.corpus_version,
                    "retrieval_text_strategy": self.config.retrieval_text_strategy.value,
                    "embedding_model": self.config.embedding_model,
                    "rerank_model": self.config.rerank_model,
                    "generation_model": self.config.generation_model,
                },
                "timings_ms": bundle.timings_ms,
                "provider_usage": bundle.provider_usage,
                "provider_attempts": bundle.provider_attempts,
                "provider_models": bundle.provider_models,
                "error_count": len(bundle.errors),
                "error_types": bundle.errors,
            },
        )
        return SearchExecution(
            public_response=response,
            evidence_packet=packet,
            observation=ExecutionObservation(planning=planning, retrieval=bundle),
        )

    async def execute_ask(self, request: QueryRequest) -> AskExecution:
        """Run one ask request and return typed internal observations directly."""

        observer = ExecutionObserver()
        response = await self.ask(request, observer=observer)
        if observer.search is None:
            raise RuntimeError("ask execution did not record its search stage")
        return AskExecution(
            response=response,
            plan=observer.search.public_response.plan,
            planning_decision=(
                observer.search.observation.planning.decision
                if observer.search.observation.planning is not None
                else None
            ),
            retrieval=observer.search.observation.retrieval,
            search=observer.search,
            generations=tuple(observer.generations),
        )

    async def search(
        self, request: QueryRequest, *, trace_id: str | None = None
    ) -> SearchResponse:
        return (await self.execute_search(request, trace_id=trace_id)).public_response

    async def ask(
        self,
        request: QueryRequest,
        *,
        observer: ExecutionObserver | None = None,
        allow_live: bool = True,
        prefer_reviewed_quotes: bool = False,
    ) -> AskResponse:
        trace_id = uuid4().hex
        try:
            return await self._ask_with_trace(
                request,
                trace_id=trace_id,
                observer=observer,
                allow_live=allow_live,
                prefer_reviewed_quotes=prefer_reviewed_quotes,
            )
        finally:
            self._active_operations.pop(trace_id, None)

    async def _ask_with_trace(
        self,
        request: QueryRequest,
        *,
        trace_id: str,
        observer: ExecutionObserver | None,
        allow_live: bool,
        prefer_reviewed_quotes: bool = False,
    ) -> AskResponse:
        operation_started = perf_counter()
        question = publication_question(request)
        unknown_identifiers = self._unknown_corpus_identifiers(question)
        if unknown_identifiers:
            plan = plan_query(request, allow_live=allow_live)
            bundle = RetrievalBundle()
            support = SupportDecision(
                status=SupportStatus.INSUFFICIENT_EVIDENCE,
                reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
                explanation=(
                    "The requested source identifier is not in the approved reviewed-source "
                    "collection."
                ),
            )
            self._active_operations[trace_id] = (operation_started, ())
            if observer is not None:
                observer.search = SearchExecution(
                    public_response=SearchResponse(
                        trace_id=trace_id,
                        plan=plan,
                        retrieval=bundle,
                        support=support,
                    ),
                    evidence_packet=None,
                    observation=ExecutionObservation(planning=None, retrieval=bundle),
                )
            response = self._unknown_source_identifier_response(
                trace_id,
                unknown_identifiers,
                plan.limitations,
            )
            return await self._record_ask(request, response, route=plan.route.value)

        execution = await self.execute_search(request, trace_id=trace_id, allow_live=allow_live)
        self._active_operations[trace_id] = (
            operation_started,
            tuple(execution.observation.retrieval.provider_models),
        )
        if observer is not None:
            observer.search = execution
        search = execution.public_response
        route = search.plan.route
        publication_packet = _with_support_limitations(
            execution.evidence_packet, search.support
        )
        place_label = request.location.label if request.location is not None else None
        capability = resolve_capability(request.question, place_label=place_label)
        allowed_typed_claim_ids = (
            capability.typed_claim_ids
            if capability is not None and capability.source_mode == "corpus"
            else None
        )
        allowed_quote_texts = (
            capability.exact_quote_texts
            if capability is not None and capability.source_mode == "corpus"
            else None
        )

        if route == QueryRoute.CAPABILITY:
            topics = ", ".join(topic for topic, _example in TOPIC_CATALOGUE)
            response = AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=trace_id,
                response_mode=ResponseMode.CAPABILITY,
                answer=(
                    "FireLens can show current official B.C. wildfire records, present "
                    "reviewed preparedness guidance with exact source wording, and make "
                    "deterministic record-based counts, rankings, and distances. It can help "
                    f"with {topics}. {GROUNDED_PUBLIC_WORDING} Grounded answers pair each "
                    "claim with reviewed local evidence and an exact supporting quote. Verify "
                    "time-sensitive evacuation notices, roads, and personal safety decisions "
                    "with the issuing officials; FireLens does not decide whether to leave, "
                    "stay, return, or take a route."
                ),
                limitations=search.plan.limitations,
                suggested_questions=list(SUGGESTED_QUESTIONS[:6]),
                reason_code=ReasonCode.CAPABILITY_OVERVIEW,
            )
            return await self._record_ask(request, response, route=route.value)

        if route == QueryRoute.TANGENT and is_outside_wildfire_scope(request):
            response = AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=trace_id,
                response_mode=ResponseMode.CAPABILITY,
                answer=SCOPE_NOTE,
                limitations=search.plan.limitations,
                suggested_questions=list(SUGGESTED_QUESTIONS[:6]),
                reason_code=ReasonCode.CAPABILITY_OVERVIEW,
            )
            return await self._record_ask(request, response, route=route.value)

        if route == QueryRoute.TANGENT:
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
            )

        if route in {QueryRoute.LIVE, QueryRoute.PROHIBITED}:
            response = _safe_abstention(
                trace_id,
                answer=search.support.explanation,
                reason_code=search.support.reason_code,
                limitations=search.plan.limitations,
            )
            return await self._record_ask(request, response, route=route.value)

        if not search.retrieval.complete:
            is_planning_failure = not search.plan.retrieval_requests
            if is_planning_failure:
                return await self._background_answer(
                    request,
                    trace_id=trace_id,
                    route=route.value,
                    limitations=[
                        *search.plan.limitations,
                        "The retrieval planner was unavailable; this response uses labelled general knowledge only.",
                    ],
                    observer=observer,
                )
            response = _unavailable_response(
                trace_id,
                reason_code=ReasonCode.RETRIEVAL_UNAVAILABLE,
                error_kind=search.retrieval.errors[0] if search.retrieval.errors else "unknown",
                limitations=search.plan.limitations,
            )
            return await self._record_ask(request, response, route=route.value)

        question = publication_question(request)
        snapshot = extract_snapshot(question)
        current_request = snapshot.freshness_live
        selected_live_request = uses_selected_live_binding(request)
        personalized_conditional_request = is_personalized_conditional_request(question)
        explicit_corpus_request = self._explicit_corpus_request(question) or bool(
            capability is not None and capability.source_mode == "corpus"
        )
        # Only an actual conflicting EvidencePacket may take precedence over
        # an ordinary Tier-C explanation.  ``SupportDecision`` is separately
        # testable and may be injected as CONFLICT without source conflicts;
        # that metadata alone cannot manufacture a conflict response.
        if (
            search.support.status == SupportStatus.CONFLICT
            and execution.evidence_packet is not None
            and execution.evidence_packet.conflicts
        ):
            response = _conflict_response(trace_id, execution.evidence_packet)
            return await self._record_ask(request, response, route=route.value)
        if self._allows_general_background_fallback(
            request,
            search.plan,
            search.support,
            explicit_corpus_request=explicit_corpus_request,
        ):
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
            )

        # Until direct-support calibration is complete, an adjacent classification
        # is intentionally background-only. Dense retrieval always returns nearby
        # chunks, so packet presence by itself is not proof of semantic support.
        # An explicit reviewed-guidance tool call may keep quote-ready support.
        if (
            search.plan.relation == QueryRelation.ADJACENT
            and not explicit_corpus_request
            and not current_request
            and not selected_live_request
            and not personalized_conditional_request
            and not (
                prefer_reviewed_quotes
                and search.support.status in {SupportStatus.ANSWERABLE, SupportStatus.PARTIAL}
            )
        ):
            compiled = compile_without_generation(
                publication_question(request),
                publication_packet,
                trace_id=trace_id,
                supported_aspects=search.support.supported_aspects,
                allowed_typed_claim_ids=allowed_typed_claim_ids,
                allowed_quote_texts=allowed_quote_texts,
            )
            if compiled is not None:
                return await self._record_ask(request, compiled, route=route.value)
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
            )

        if search.support.status == SupportStatus.CONFLICT:
            if execution.evidence_packet is None or not execution.evidence_packet.conflicts:
                response = _safe_abstention(
                    trace_id,
                    answer=(
                        "Conflicting evidence was detected, but its source packet was unavailable."
                    ),
                    reason_code=ReasonCode.CONFLICTING_EVIDENCE,
                    limitations=search.plan.limitations,
                )
            else:
                response = _conflict_response(trace_id, execution.evidence_packet)
            return await self._record_ask(request, response, route=route.value)

        if search.support.status not in {SupportStatus.ANSWERABLE, SupportStatus.PARTIAL}:
            if explicit_corpus_request:
                response = self._unsupported_source_request_response(
                    trace_id=trace_id,
                    packet=publication_packet,
                    support=search.support,
                    limitations=search.plan.limitations,
                )
                return await self._record_ask(request, response, route=route.value)
            if personalized_conditional_request or current_request or selected_live_request:
                response = official_handoff_response(trace_id)
                return await self._record_ask(request, response, route=route.value)
            compiled = compile_without_generation(
                publication_question(request),
                publication_packet,
                trace_id=trace_id,
                supported_aspects=search.support.supported_aspects,
                force_partial=True,
                allowed_typed_claim_ids=allowed_typed_claim_ids,
                allowed_quote_texts=allowed_quote_texts,
            )
            if compiled is not None:
                return await self._record_ask(request, compiled, route=route.value)
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
                evidence_packet=publication_packet,
            )

        packet = publication_packet
        if packet is None:
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
            )
        generation_question = publication_question(request)
        outcome = await self.grounded_answers.answer(
            generation_question,
            packet,
            observer,
            trace_id=trace_id,
            force_partial=search.support.status == SupportStatus.PARTIAL,
            supported_aspects=search.support.supported_aspects,
            allowed_typed_claim_ids=allowed_typed_claim_ids,
            allowed_quote_texts=allowed_quote_texts,
        )
        if (
            outcome.response.reason_code
            in {ReasonCode.DRAFT_VALIDATION_FAILED, ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED}
            and not outcome.response.claims
            and self._allows_general_background_fallback(
                request,
                search.plan,
                search.support.model_copy(
                    update={"status": SupportStatus.INSUFFICIENT_EVIDENCE}
                ),
                explicit_corpus_request=explicit_corpus_request,
            )
        ):
            # An ordinary explanatory question whose generated summary could not
            # be tied to the retrieved passages, or whose passages yielded no
            # publishable exact wording, gets the same labelled general
            # background it would have received had retrieval found nothing,
            # instead of a "validation failed" or "no structured claim" handoff.
            # Reviewed-guidance, live, personalized, and Tier A/B questions are
            # excluded by ``_allows_general_background_fallback``.
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
                evidence_packet=packet,
            )
        return await self._record_ask(
            request,
            outcome.response,
            route=route.value,
            model=outcome.model,
            generation_ms=outcome.latency_ms,
            generation_usage=outcome.usage,
            generation_attempts=outcome.attempts,
            repair_count=outcome.repair_count,
            validation=(
                outcome.validation.model_dump(mode="json")
                if outcome.validation is not None
                else None
            ),
            cited_evidence_ids=list(outcome.cited_evidence_ids),
        )
