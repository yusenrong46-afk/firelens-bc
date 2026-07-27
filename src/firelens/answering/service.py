"""Explicit orchestration: route, plan, retrieve, support, generate, validate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import HttpUrl

from firelens.answering.context import (
    EvidenceIndex,
    build_evidence_packet,
    decide_support,
)
from firelens.answering.generate import (
    background_messages,
    background_schema,
    draft_schema,
    generation_messages,
)
from firelens.answering.intent import (
    SUGGESTED_QUESTIONS,
    TOPIC_CATALOGUE,
    apply_planning_decision,
    plan_query,
)
from firelens.answering.planner import planning_messages, planning_schema
from firelens.answering.validate import validate_background_draft, validate_draft
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    BackgroundDraft,
    ClaimSupport,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceStatus,
    GroundedDraft,
    PlanningDecision,
    PlanningResponse,
    PublicClaim,
    PublicEvidence,
    QueryPlan,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    RetrievalBundle,
    SearchResponse,
    SupportStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.errors import ProviderError
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.traces import TraceRecorder


@dataclass(frozen=True)
class ExecutionObservation:
    """Typed internal measurements for evaluation without rereading traces."""

    planning: PlanningResponse | None
    retrieval: RetrievalBundle


@dataclass(frozen=True)
class SearchExecution:
    public_response: SearchResponse
    evidence_packet: EvidencePacket | None
    observation: ExecutionObservation


@dataclass(frozen=True)
class GenerationObservation:
    stage: str
    model: str | None
    usage: dict[str, Any]
    attempts: int
    latency_ms: float
    validation: ValidationReport | None = None
    error_kind: str | None = None


@dataclass
class ExecutionObserver:
    """Per-request capture object used by benchmarks; safe for concurrent calls."""

    search: SearchExecution | None = None
    generations: list[GenerationObservation] = field(default_factory=list)


@dataclass(frozen=True)
class AskExecution:
    """Complete private execution record consumed by benchmark runners."""

    response: AskResponse
    plan: QueryPlan
    planning_decision: PlanningDecision | None
    retrieval: RetrievalBundle
    search: SearchExecution
    generations: tuple[GenerationObservation, ...]


def _unique_claim_supports(
    quote_ids: Sequence[str], quote_candidates: Mapping[str, EvidenceQuoteCandidate]
) -> list[ClaimSupport]:
    supports: list[ClaimSupport] = []
    seen: set[tuple[str, str]] = set()
    for quote_id in quote_ids:
        candidate = quote_candidates[quote_id]
        pair = (candidate.evidence_id, candidate.text)
        if pair not in seen:
            seen.add(pair)
            supports.append(
                ClaimSupport(evidence_id=candidate.evidence_id, quote=candidate.text)
            )
    return supports


def _unavailable_response(
    trace_id: str,
    *,
    reason_code: ReasonCode,
    error_kind: str,
    limitations: Sequence[str],
) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ERROR,
        trace_id=trace_id,
        response_mode=ResponseMode.ABSTENTION,
        reason_code=reason_code,
        error_kind=error_kind,
        limitations=list(limitations),
    )


def _safe_abstention(
    trace_id: str,
    *,
    answer: str,
    reason_code: ReasonCode,
    limitations: Sequence[str],
) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=trace_id,
        response_mode=ResponseMode.ABSTENTION,
        answer=answer,
        limitations=list(limitations),
        reason_code=reason_code,
    )


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
        self.retrieval = retrieval
        self.provider = provider
        self.config = config
        self.trace_recorder = trace_recorder or TraceRecorder(
            config.trace_dir,
            include_content=config.trace_content,
            max_files=config.trace_max_files,
            max_bytes=config.trace_max_bytes,
        )

    async def _record_ask(
        self,
        request: QueryRequest,
        response: AskResponse,
        *,
        route: str,
        **details: object,
    ) -> AskResponse:
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
        self, request: QueryRequest, *, trace_id: str | None = None
    ) -> SearchExecution:
        active_trace_id = trace_id or uuid4().hex
        plan = plan_query(request)
        planning: PlanningResponse | None = None
        packet: EvidencePacket | None = None

        if plan.route == QueryRoute.RELATED:
            planning_started = perf_counter()
            try:
                planning = await self.provider.plan(
                    planning_messages(request), output_schema=planning_schema()
                )
                plan = apply_planning_decision(plan, planning.decision)
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
            response = _unavailable_response(
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
        self, request: QueryRequest, *, observer: ExecutionObserver | None = None
    ) -> AskResponse:
        trace_id = uuid4().hex
        execution = await self.execute_search(request, trace_id=trace_id)
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

        if search.support.status != SupportStatus.ANSWERABLE:
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

        started = perf_counter()
        try:
            generated = await self.provider.generate_grounded(
                generation_messages(packet, original_question=request.question),
                output_schema=draft_schema(packet),
            )
        except ProviderError as exc:
            if observer is not None:
                observer.generations.append(
                    GenerationObservation(
                        stage="grounded_generation",
                        model=None,
                        usage={},
                        attempts=0,
                        latency_ms=(perf_counter() - started) * 1_000,
                        error_kind=exc.kind.value,
                    )
                )
            response = _unavailable_response(
                trace_id,
                reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                error_kind=exc.kind.value,
                limitations=packet.limitations,
            )
            return await self._record_ask(request, response, route=route.value)

        generation_ms = (perf_counter() - started) * 1_000
        if not isinstance(generated.draft, GroundedDraft):
            if observer is not None:
                observer.generations.append(
                    GenerationObservation(
                        stage="grounded_generation",
                        model=generated.model,
                        usage=generated.usage,
                        attempts=generated.attempts,
                        latency_ms=generation_ms,
                    )
                )
            response = _safe_abstention(
                trace_id,
                answer="The generated answer did not match the grounded-answer format.",
                reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                limitations=packet.limitations,
            )
            return await self._record_ask(request, response, route=route.value)
        validation = validate_draft(generated.draft, packet)
        if observer is not None:
            observer.generations.append(
                GenerationObservation(
                    stage="grounded_generation",
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
                answer="The generated answer did not pass FireLens validation.",
                reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                limitations=packet.limitations,
            ).model_copy(update={"validation": validation})
            return await self._record_ask(
                request,
                response,
                route=route.value,
                model=generated.model,
                generation_ms=generation_ms,
                generation_usage=generated.usage,
                generation_attempts=generated.attempts,
                validation=validation.model_dump(mode="json"),
            )

        quote_candidates = {
            candidate.quote_id: candidate for candidate in packet.quote_candidates
        }
        public_claims: list[PublicClaim] = [
            PublicClaim(
                claim_id=f"C{claim_index}",
                text=claim.text,
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=_unique_claim_supports(claim.evidence_quote_ids, quote_candidates),
            )
            for claim_index, claim in enumerate(generated.draft.claims, start=1)
        ]
        cited_ids = {
            support.evidence_id for claim in public_claims for support in claim.supports
        }
        evidence = [
            PublicEvidence(
                evidence_id=item.evidence_id,
                title=item.title,
                publisher=item.publisher,
                canonical_url=HttpUrl(item.canonical_url),
                locator=item.locator,
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text=item.primary_text,
                context_text=item.context_text,
            )
            for item in packet.items
            if item.evidence_id in cited_ids
        ]
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=ResponseMode.GROUNDED,
            answer=" ".join(claim.text.strip() for claim in public_claims),
            claims=public_claims,
            evidence=evidence,
            limitations=generated.draft.limitations,
            validation=validation,
        )
        return await self._record_ask(
            request,
            response,
            route=route.value,
            model=generated.model,
            generation_ms=generation_ms,
            generation_usage=generated.usage,
            generation_attempts=generated.attempts,
            validation=validation.model_dump(mode="json"),
            cited_evidence_ids=sorted(cited_ids),
        )
