"""Support mixin for the static RAG service's bounded response paths."""

from __future__ import annotations

import re
from collections.abc import Sequence
from time import perf_counter

from firelens.answering.execution import ExecutionObserver
from firelens.answering.generate import background_messages, background_schema
from firelens.answering.grounded import GenerationObservation, GroundedAnswerEngine
from firelens.answering.intent import (
    explicit_corpus_attribution,
    publication_question,
    skips_provider_planning,
)
from firelens.answering.live_request_intent import uses_selected_live_binding
from firelens.answering.registered_suggestions import registered_suggestions
from firelens.answering.responses import (
    provider_abstention as _provider_abstention,
)
from firelens.answering.responses import (
    safe_abstention as _safe_abstention,
)
from firelens.answering.risk_policy import RiskTier
from firelens.answering.scope import (
    candidate_contains_identifier as _candidate_contains_identifier,
)
from firelens.answering.scope import (
    candidate_source_reference_present as _candidate_source_reference_present,
)
from firelens.answering.scope import (
    corpus_identifiers,
)
from firelens.answering.typed_snapshot import classify_text, extract_snapshot
from firelens.answering.validate import validate_background_draft
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    BackgroundDraft,
    EvidencePacket,
    EvidenceStatus,
    PublicClaim,
    QueryPlan,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    SupportDecision,
    SupportStatus,
    render_claim_texts,
)
from firelens.errors import ProviderError
from firelens.ingestion.chunking import ChunkRecord
from firelens.operational_logging import log_operation, usage_cost_usd, usage_tokens
from firelens.providers.base import AIProvider
from firelens.publication.fallback import background_authority
from firelens.retrieval.bm25 import BM25Index
from firelens.source_requirements import SourceRequirement, source_requirement_for_question
from firelens.traces import TraceRecorder, project_ask_trace_details

_SOURCE_IDENTITY_STOPWORDS = frozenset(
    {
        "british",
        "columbia",
        "document",
        "emergency",
        "fire",
        "fires",
        "government",
        "guide",
        "guidance",
        "preparedness",
        "source",
        "wildfire",
        "wildfires",
    }
)
_PERSONALIZED_CONDITIONAL_DECISION = re.compile(
    r"\b(?:what|how)\s+(?:should|can|could|may)\s+(?:i|we)\s+"
    r"(?:do|handle|respond)\b.{0,80}\b(?:if|when)\b",
    re.IGNORECASE,
)


def is_personalized_conditional_request(question: str) -> bool:
    """Whether this request asks for a personal conditional decision."""

    return _PERSONALIZED_CONDITIONAL_DECISION.search(question) is not None


def with_support_limitations(
    packet: EvidencePacket | None, support: SupportDecision
) -> EvidencePacket | None:
    """Project unsupported selected aspects into the compiled packet limitation."""

    if packet is None or not support.missing_aspects:
        return packet
    aspects = list(dict.fromkeys(aspect for aspect in support.missing_aspects if aspect))
    if not aspects:
        return packet
    limitation = "Not supported by selected evidence: " + "; ".join(aspects)
    if limitation in packet.limitations:
        return packet
    return packet.model_copy(update={"limitations": [*packet.limitations, limitation]})


class StaticRAGSupport:
    """Helpers shared by orchestration without changing the service public API."""

    chunks: tuple[ChunkRecord, ...]
    planning_index: BM25Index
    provider: AIProvider
    grounded_answers: GroundedAnswerEngine
    _active_operations: dict[str, tuple[float, tuple[str, ...]]]
    config: FireLensConfig
    trace_recorder: TraceRecorder
    corpus_version: str

    def _planning_candidates(self, question: str) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        for result in self.planning_index.search(question, top_k=5):
            candidates.append(
                {
                    "chunk_id": result.chunk_id,
                    "source_id": result.source_id,
                    "title": result.title,
                    "publisher": result.publisher,
                    "section": result.section_title or "",
                    "snippet": " ".join(result.text.split())[:360],
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

    def _unknown_corpus_identifiers(self, question: str) -> tuple[str, ...]:
        identifiers = corpus_identifiers(question)
        known = {
            identifier
            for identifier in identifiers
            if any(
                identifier in {chunk.chunk_id.casefold(), chunk.source_id.casefold()}
                or identifier in chunk.text.casefold()
                for chunk in self.chunks
            )
        }
        return tuple(sorted(identifiers - known))

    @staticmethod
    def _unknown_source_identifier_response(
        trace_id: str, identifiers: Sequence[str], limitations: Sequence[str]
    ) -> AskResponse:
        displayed = ", ".join(identifier.upper() for identifier in identifiers)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=(
                "FireLens could not find the requested source identifier "
                f"{displayed} in its approved reviewed-source collection."
            ),
            limitations=[
                *limitations,
                "No reviewed-source claim, evidence, or related link was published because "
                "the requested source identifier is not in the approved collection.",
            ],
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
        )

    def _explicit_corpus_request(self, question: str) -> bool:
        candidates = self._planning_candidates(question)
        identifiers = corpus_identifiers(question)
        if (
            _candidate_contains_identifier(question, candidates)
            or self._planning_identifier_present(question)
            or _candidate_source_reference_present(question, candidates)
            or any(
                identifier in {chunk.chunk_id.casefold(), chunk.source_id.casefold()}
                for identifier in identifiers
                for chunk in self.chunks
            )
        ):
            return True
        if not explicit_corpus_attribution(question):
            return False
        tokens = set(re.findall(r"[a-z0-9]+", question.casefold()))
        return any(
            token in tokens and token not in _SOURCE_IDENTITY_STOPWORDS and len(token) >= 5
            for candidate in candidates
            for field in ("source_id", "title", "publisher")
            for token in re.findall(r"[a-z0-9]+", candidate.get(field, "").casefold())
        ) or bool(re.search(r"\b(?:source|document|guide|checklist)\b", question, re.I))

    def _allows_general_background_fallback(
        self,
        request: QueryRequest,
        plan: QueryPlan,
        support: SupportDecision,
        *,
        explicit_corpus_request: bool,
    ) -> bool:
        question = publication_question(request)
        return bool(
            plan.route == QueryRoute.RELATED
            and source_requirement_for_question(question) == SourceRequirement.GENERAL_ALLOWED
            and support.status != SupportStatus.ANSWERABLE
            and classify_text(question) == RiskTier.C
            and not extract_snapshot(question).freshness_live
            and not is_personalized_conditional_request(question)
            and not skips_provider_planning(request)
            and not uses_selected_live_binding(request)
            and not explicit_corpus_request
        )

    def _unsupported_source_request_response(
        self,
        *,
        trace_id: str,
        packet: EvidencePacket | None,
        support: SupportDecision,
        limitations: Sequence[str],
    ) -> AskResponse:
        if packet is None:
            return _safe_abstention(
                trace_id,
                answer=support.explanation,
                reason_code=support.reason_code,
                limitations=limitations,
            )
        return self.grounded_answers.source_handoff(
            trace_id,
            packet,
            answer=(
                "FireLens found the requested reviewed source, but its selected wording does "
                "not directly support this question. Open the source below rather than relying "
                "on a general summary."
            ),
            reason_code=support.reason_code,
            extra_limitation=(
                "No general-knowledge claim was published because this request explicitly "
                "asked about a reviewed source."
            ),
        )

    async def _record_ask(
        self, request: QueryRequest, response: AskResponse, *, route: str, **details: object
    ) -> AskResponse:
        if not response.suggested_questions:
            suggestions = registered_suggestions(question=request.question, response=response)
            if suggestions:
                response = response.model_copy(update={"suggested_questions": suggestions})
        trace_details = project_ask_trace_details(details)
        operation = self._active_operations.pop(response.trace_id, None)
        if operation is not None:
            started, provider_models = operation
            visible_models = list(provider_models)
            stages: list[str] = []
            if self.config.embedding_model in provider_models:
                stages.append("query_embedding")
            if self.config.rerank_model in provider_models:
                stages.append("rerank")
            if details.get("model"):
                visible_models.append(str(details["model"]))
                stages.append(
                    "background_generation"
                    if response.response_mode == ResponseMode.BACKGROUND
                    else "grounded_generation"
                )
            if isinstance(details.get("repair_count"), int) and details["repair_count"]:
                stages.append("grounded_repair")
            usage = details.get("generation_usage")
            log_operation(
                trace_id=response.trace_id,
                route=route,
                response_mode=response.response_mode.value,
                status=response.status.value,
                latency_ms=(perf_counter() - started) * 1_000,
                provider_stages=stages,
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
                input_tokens=usage_tokens(usage, "prompt_tokens", "input_tokens"),
                output_tokens=usage_tokens(usage, "completion_tokens", "output_tokens"),
                cost_usd=usage_cost_usd(usage),
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
                **trace_details,
            },
        )
        return response

    async def _background_answer(
        self,
        request: QueryRequest,
        *,
        trace_id: str,
        route: str,
        limitations: Sequence[str],
        observer: ExecutionObserver | None,
        evidence_packet: EvidencePacket | None = None,
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
            response = (
                self.grounded_answers.source_handoff(
                    trace_id,
                    evidence_packet,
                    answer=(
                        "FireLens found reviewed sources related to this question, but the "
                        "language service is temporarily unavailable. Open the reviewed "
                        "sources below for more information."
                    ),
                    reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                    error_kind=exc.kind.value,
                    extra_limitation=(
                        "No generated general-knowledge claim was published while the "
                        "language service was unavailable."
                    ),
                )
                if evidence_packet is not None
                else _provider_abstention(
                    trace_id,
                    reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                    error_kind=exc.kind.value,
                    limitations=limitations,
                )
            )
            return await self._record_ask(request, response, route=route)
        elapsed = (perf_counter() - started) * 1_000
        if not isinstance(generated.draft, BackgroundDraft):
            if observer is not None:
                observer.generations.append(
                    GenerationObservation(
                        stage="background_generation",
                        model=generated.model,
                        usage=generated.usage,
                        attempts=generated.attempts,
                        latency_ms=elapsed,
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
                    latency_ms=elapsed,
                    validation=validation,
                )
            )
        if not validation.accepted:
            response = (
                self.grounded_answers.source_handoff(
                    trace_id,
                    evidence_packet,
                    answer=(
                        "FireLens found reviewed sources related to this question, but the "
                        "general-knowledge summary did not pass safety validation. Open the "
                        "reviewed sources below instead of relying on the rejected draft."
                    ),
                    reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                    validation=validation,
                    extra_limitation=(
                        "No generated general-knowledge claim was published from the rejected "
                        "draft."
                    ),
                )
                if evidence_packet is not None
                else _safe_abstention(
                    trace_id,
                    answer="The generated background answer did not pass FireLens validation.",
                    reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                    limitations=generated.draft.limitations,
                ).model_copy(update={"validation": validation})
            )
            return await self._record_ask(request, response, route=route)
        claims = [
            PublicClaim(
                claim_id=f"C{index}",
                text=claim.text,
                evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
                publication=background_authority(),
            )
            for index, claim in enumerate(generated.draft.claims, start=1)
        ]
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=ResponseMode.BACKGROUND,
            answer=render_claim_texts(claims),
            claims=claims,
            limitations=generated.draft.limitations,
            validation=validation,
        )
        return await self._record_ask(
            request,
            response,
            route=route,
            model=generated.model,
            generation_ms=elapsed,
            generation_usage=generated.usage,
            generation_attempts=generated.attempts,
        )
