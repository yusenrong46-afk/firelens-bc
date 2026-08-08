"""Explicit orchestration: route, plan, retrieve, support, generate, validate."""

from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from uuid import uuid4

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
from firelens.answering.generate import (
    background_messages,
    background_schema,
)
from firelens.answering.grounded import GenerationObservation, GroundedAnswerEngine
from firelens.answering.intent import (
    SUGGESTED_QUESTIONS,
    TOPIC_CATALOGUE,
    apply_planning_decision,
    plan_query,
    resolved_user_question,
)
from firelens.answering.planner import planning_messages, planning_schema
from firelens.answering.responses import (
    conflict_response as _conflict_response,
)
from firelens.answering.responses import (
    provider_abstention as _provider_abstention,
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
    corpus_identifiers,
)
from firelens.answering.scope import (
    mixed_scope_request as _mixed_scope_request,
)
from firelens.answering.validate import (
    validate_background_draft,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    BackgroundDraft,
    EvidencePacket,
    EvidenceStatus,
    PlanningResponse,
    PublicClaim,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    RetrievalBundle,
    SearchResponse,
    SupportStatus,
)
from firelens.errors import ProviderError
from firelens.ingestion.chunking import ChunkRecord
from firelens.operational_logging import log_operation
from firelens.providers.base import AIProvider
from firelens.retrieval.bm25 import BM25Index
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.traces import TraceRecorder


class StaticRAGService:
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
            include_question_fingerprint=config.deployment_environment != "production",
            max_files=config.trace_max_files,
            max_bytes=config.trace_max_bytes,
        )

    def _planning_candidates(self, question: str) -> list[dict[str, str]]:
        """Expose bounded corpus vocabulary without treating snippets as evidence."""

        candidates: list[dict[str, str]] = []
        for result in self.planning_index.search(question, top_k=5):
            snippet = " ".join(result.text.split())[:360]
            candidates.append(
                {
                    "chunk_id": result.chunk_id,
                    "source_id": result.source_id,
                    "title": result.title,
                    "publisher": result.publisher,
                    "section": result.section_title or "",
                    "snippet": snippet,
                }
            )
        return candidates

    def _planning_identifier_present(self, question: str) -> bool:
        identifiers = corpus_identifiers(question)
        return any(
            identifier in result.text.casefold()
            for identifier in identifiers
            for result in self.planning_index.search(question, top_k=5)
        )

    async def _record_ask(
        self,
        request: QueryRequest,
        response: AskResponse,
        *,
        route: str,
        **details: object,
    ) -> AskResponse:
        operation = self._active_operations.pop(response.trace_id, None)
        if operation is not None:
            started, provider_models = operation
            visible_models = list(provider_models)
            visible_stages: list[str] = []
            if self.config.embedding_model in provider_models:
                visible_stages.append("query_embedding")
            if self.config.rerank_model in provider_models:
                visible_stages.append("rerank")
            if details.get("model"):
                visible_models.append(str(details["model"]))
                visible_stages.append(
                    "background_generation"
                    if response.response_mode == ResponseMode.BACKGROUND
                    else "grounded_generation"
                )
            if isinstance(details.get("repair_count"), int) and details["repair_count"]:
                visible_stages.append("grounded_repair")
            log_operation(
                trace_id=response.trace_id,
                route=route,
                response_mode=response.response_mode.value,
                status=response.status.value,
                latency_ms=(perf_counter() - started) * 1_000,
                provider_stages=visible_stages,
                provider_models=visible_models,
                error_category=response.error_kind,
                evidence_count=len(response.evidence),
                claim_count=len(response.claims),
                live_result_count=len(response.live_results),
                validation_disposition=(
                    "accepted"
                    if response.validation is not None and response.validation.accepted
                    else "rejected"
                    if response.validation is not None
                    else "not_applicable"
                ),
                corpus_version=self.corpus_version,
                release_version=self.config.release_version,
                build_commit=self.config.build_commit,
                deployment_environment=self.config.deployment_environment,
            )
        await self.trace_recorder.record(
            response.trace_id,
            question=request.question,
            payload={
                "operation": "ask",
                "route": route,
                "status": response.status.value,
                "response_mode": response.response_mode.value,
                "reason_code": response.reason_code,
                "error_kind": response.error_kind,
                "history_turn_count": len(request.history),
                **details,
            },
        )
        return response

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

        if plan.route == QueryRoute.RELATED:
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
                                        "An explicit source reference appears in the current "
                                        "corpus preflight."
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
                bundle = RetrievalBundle(
                    complete=False,
                    errors=[exc.kind.value],
                    timings_ms={"planning": (perf_counter() - planning_started) * 1_000},
                )
            else:
                if plan.retrieval_requests:
                    bundle = await self.retrieval.search(plan)
                    bundle.provider_usage["planning"] = planning.usage
                    bundle.provider_attempts["planning"] = planning.attempts
                    bundle.provider_models["planning"] = planning.model
                    bundle.timings_ms["planning"] = (perf_counter() - planning_started) * 1_000
                    packet = build_evidence_packet(
                        plan.normalized_question,
                        bundle.reranked_hits,
                        self.chunks,
                        corpus_version=self.corpus_version,
                        config=self.config,
                        evidence_index=self.evidence_index,
                        selection_aspects=tuple(
                            dict.fromkeys(
                                [
                                    *plan.required_aspects,
                                    *(request.query for request in plan.retrieval_requests),
                                ]
                            )
                        ),
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
                "errors": bundle.errors,
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

    async def _background_answer(
        self,
        request: QueryRequest,
        *,
        trace_id: str,
        route: str,
        limitations: Sequence[str],
        observer: ExecutionObserver | None,
    ) -> AskResponse:
        started = perf_counter()
        try:
            generated = await self.provider.generate_background(
                background_messages(request), output_schema=background_schema()
            )
        except ProviderError as exc:
            if observer is not None:
                observer.generations.append(
                    GenerationObservation(
                        stage="background_generation",
                        model=None,
                        usage={},
                        attempts=0,
                        latency_ms=(perf_counter() - started) * 1_000,
                        error_kind=exc.kind.value,
                    )
                )
            response = _provider_abstention(
                trace_id,
                reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                error_kind=exc.kind.value,
                limitations=limitations,
            )
            return await self._record_ask(request, response, route=route)
        generation_ms = (perf_counter() - started) * 1_000
        if not isinstance(generated.draft, BackgroundDraft):
            if observer is not None:
                observer.generations.append(
                    GenerationObservation(
                        stage="background_generation",
                        model=generated.model,
                        usage=generated.usage,
                        attempts=generated.attempts,
                        latency_ms=generation_ms,
                    )
                )
            response = _safe_abstention(
                trace_id,
                answer="The background answer did not match the required FireLens format.",
                reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                limitations=limitations,
            )
            return await self._record_ask(request, response, route=route)
        validation = validate_background_draft(generated.draft)
        if observer is not None:
            observer.generations.append(
                GenerationObservation(
                    stage="background_generation",
                    model=generated.model,
                    usage=generated.usage,
                    attempts=generated.attempts,
                    latency_ms=generation_ms,
                    validation=validation,
                )
            )
        if not validation.accepted:
            response = _safe_abstention(
                trace_id,
                answer="The generated background answer did not pass FireLens validation.",
                reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                limitations=generated.draft.limitations,
            ).model_copy(update={"validation": validation})
            return await self._record_ask(request, response, route=route)
        claims = [
            PublicClaim(
                claim_id=f"C{index}",
                text=claim.text,
                evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            )
            for index, claim in enumerate(generated.draft.claims, start=1)
        ]
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=ResponseMode.BACKGROUND,
            answer=" ".join(claim.text for claim in claims),
            claims=claims,
            limitations=generated.draft.limitations,
            validation=validation,
        )
        return await self._record_ask(
            request,
            response,
            route=route,
            model=generated.model,
            generation_ms=generation_ms,
            generation_usage=generated.usage,
            generation_attempts=generated.attempts,
        )

    async def ask(
        self,
        request: QueryRequest,
        *,
        observer: ExecutionObserver | None = None,
        allow_live: bool = True,
    ) -> AskResponse:
        trace_id = uuid4().hex
        try:
            return await self._ask_with_trace(
                request,
                trace_id=trace_id,
                observer=observer,
                allow_live=allow_live,
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
    ) -> AskResponse:
        operation_started = perf_counter()
        execution = await self.execute_search(request, trace_id=trace_id, allow_live=allow_live)
        self._active_operations[trace_id] = (
            operation_started,
            tuple(execution.observation.retrieval.provider_models),
        )
        if observer is not None:
            observer.search = execution
        search = execution.public_response
        route = search.plan.route

        if route == QueryRoute.CAPABILITY:
            topics = ", ".join(topic for topic, _example in TOPIC_CATALOGUE)
            response = AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=trace_id,
                response_mode=ResponseMode.CAPABILITY,
                answer=(
                    f"FireLens can help with {topics}. Its reviewed collection includes "
                    "PreparedBC, FireSmart BC, BC Wildfire Service, and BCCDC guidance. "
                    "Verified answers pair each claim with reviewed local evidence and an "
                    "exact supporting quote."
                ),
                limitations=search.plan.limitations,
                suggested_questions=list(SUGGESTED_QUESTIONS[:6]),
                reason_code=ReasonCode.CAPABILITY_OVERVIEW,
            )
            return await self._record_ask(request, response, route=route.value)

        if route == QueryRoute.TANGENT:
            response = AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=trace_id,
                response_mode=ResponseMode.SCOPE_REDIRECT,
                answer=(
                    "That request is outside FireLens's wildfire-preparedness scope. "
                    "Here are some questions this collection can help with."
                ),
                limitations=search.plan.limitations,
                suggested_questions=list(SUGGESTED_QUESTIONS[:6]),
                reason_code=ReasonCode.SCOPE_REDIRECT,
            )
            return await self._record_ask(request, response, route=route.value)

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
            response = _unavailable_response(
                trace_id,
                reason_code=(
                    ReasonCode.PLANNING_UNAVAILABLE
                    if is_planning_failure
                    else ReasonCode.RETRIEVAL_UNAVAILABLE
                ),
                error_kind=search.retrieval.errors[0] if search.retrieval.errors else "unknown",
                limitations=search.plan.limitations,
            )
            return await self._record_ask(request, response, route=route.value)

        # Until direct-support calibration is complete, an adjacent classification
        # is intentionally background-only. Dense retrieval always returns nearby
        # chunks, so packet presence by itself is not proof of semantic support.
        if search.plan.relation == QueryRelation.ADJACENT:
            return await self._background_answer(
                request,
                trace_id=trace_id,
                route=route.value,
                limitations=search.plan.limitations,
                observer=observer,
            )

        if search.support.status == SupportStatus.CONFLICT:
            if execution.evidence_packet is None:
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
            response = _safe_abstention(
                trace_id,
                answer=(
                    f"{search.support.explanation} Try a more specific question about "
                    "the FireLens guidance topics."
                ),
                reason_code=search.support.reason_code,
                limitations=search.plan.limitations,
            ).model_copy(update={"suggested_questions": list(SUGGESTED_QUESTIONS[:6])})
            return await self._record_ask(request, response, route=route.value)

        packet = execution.evidence_packet
        if packet is None:
            response = _safe_abstention(
                trace_id,
                answer="No approved evidence packet was available.",
                reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
                limitations=search.plan.limitations,
            )
            return await self._record_ask(request, response, route=route.value)
        if search.support.status == SupportStatus.PARTIAL:
            packet = packet.model_copy(
                update={
                    "limitations": [
                        *packet.limitations,
                        "Not supported by selected evidence: "
                        + "; ".join(search.support.missing_aspects),
                    ]
                }
            )

        generation_question = resolved_user_question(request)
        outcome = await self.grounded_answers.answer(
            generation_question,
            packet,
            observer,
            trace_id=trace_id,
            force_partial=search.support.status == SupportStatus.PARTIAL,
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
