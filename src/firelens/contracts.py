"""Strict evidence-visible contracts passed between FireLens RAG stages.

Internal model drafts stay separate from public grounded and background types.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, HttpUrl, field_validator, model_validator

from firelens import api_contracts as _api_contracts
from firelens import live_contracts as _live_contracts
from firelens.assistant_history import ASSISTANT_HISTORY_LIMIT as ASSISTANT_HISTORY_LIMIT
from firelens.assistant_history import bounded_assistant_history as bounded_assistant_history
from firelens.assistant_history import render_assistant_history as render_assistant_history
from firelens.claim_trust import ClaimTrust
from firelens.contract_base import FrozenStrictModel, StrictModel
from firelens.contract_composition import (
    BOUNDED_CONFLICT_TEXT as BOUNDED_CONFLICT_TEXT,
)
from firelens.contract_composition import (
    DETERMINISTIC_CONFLICT_TEXT as DETERMINISTIC_CONFLICT_TEXT,
)
from firelens.contract_composition import is_canonical_conflict_answer
from firelens.evidence_packet_identity import validate_evidence_packet_identity
from firelens.proof_presentation import AnswerStatusBanner, ProofCard, attach_proof_presentation
from firelens.publication_contracts import PublicationAuthority
from firelens.publication_response_binding import (
    ask_claim_publication_error,
    current_records_binding_error,
)

DocumentContextDraft = _api_contracts.DocumentContextDraft
DocumentContextItem = _api_contracts.DocumentContextItem
DocumentContextResponse = _api_contracts.DocumentContextResponse
EmbeddingResponse = _api_contracts.EmbeddingResponse
ErrorEnvelope = _api_contracts.ErrorEnvelope
FeedbackCategory = _api_contracts.FeedbackCategory
FeedbackRequest = _api_contracts.FeedbackRequest
FeedbackResponse = _api_contracts.FeedbackResponse
HealthResponse = _api_contracts.HealthResponse
LivenessResponse = _api_contracts.LivenessResponse
MAX_RELATED_LINKS = _api_contracts.MAX_RELATED_LINKS
RELATED_LINK_DESCRIPTION_MAX_CHARS = _api_contracts.RELATED_LINK_DESCRIPTION_MAX_CHARS
RELATED_LINK_TITLE_MAX_CHARS = _api_contracts.RELATED_LINK_TITLE_MAX_CHARS
RelatedLink = _api_contracts.RelatedLink
RerankResponse = _api_contracts.RerankResponse
RerankResult = _api_contracts.RerankResult
ValidationReport = _api_contracts.ValidationReport
response_history_prefix = _api_contracts.response_history_prefix

AggregateFreshness = _live_contracts.AggregateFreshness
CoarseResolvedLocation = _live_contracts.CoarseResolvedLocation
DistanceDerivation = _live_contracts.DistanceDerivation
Freshness = _live_contracts.Freshness
GeometryRelation = _live_contracts.GeometryRelation
LiveLayerStatus = _live_contracts.LiveLayerStatus
LiveMapResponse = _live_contracts.LiveMapResponse
LivePagination = _live_contracts.LivePagination
LiveResult = _live_contracts.LiveResult
LiveResultKind = _live_contracts.LiveResultKind
LocationInput = _live_contracts.LocationInput
MapViewport = _live_contracts.MapViewport
NearMeRequest = _live_contracts.NearMeRequest
NearMeResponse = _live_contracts.NearMeResponse
aggregate_live_freshness = _live_contracts.aggregate_live_freshness
bind_distance_derivation = _live_contracts.bind_distance_derivation
freshness_for_observation = _live_contracts.freshness_for_observation

PUBLIC_ANSWER_MAX_CHARS = ASSISTANT_HISTORY_LIMIT
MAX_GROUNDED_ANSWER_CHARS = 2_500
MAX_PUBLIC_CLAIMS = 12
MAX_BACKGROUND_CLAIMS = 3


class ClaimText(Protocol):
    """Structural type shared by draft and public claim renderers."""

    text: str


def render_claim_texts(claims: Iterable[ClaimText]) -> str:
    """Render claim text once so validation, publication, and composition agree."""

    return " ".join(claim.text.strip() for claim in claims)


class QueryRoute(StrEnum):
    CAPABILITY = "capability"
    RELATED = "related"
    # Source compatibility for Python callers.  Historic serialized "static"
    # values are accepted by _missing_ below, but new responses say "related".
    STATIC = "related"
    TANGENT = "tangent"
    LIVE = "live"
    PROHIBITED = "prohibited"

    @classmethod
    def _missing_(cls, value: object) -> QueryRoute | None:
        return cls.RELATED if value == "static" else None


class QueryRelation(StrEnum):
    GROUNDED_CANDIDATE = "grounded_candidate"
    ADJACENT = "adjacent"
    TANGENT = "tangent"


class EvidenceStatus(StrEnum):
    VERIFIED_CORPUS = "verified_corpus"
    GENERAL_BACKGROUND = "general_background"


class ResponseMode(StrEnum):
    GROUNDED = "grounded"
    BACKGROUND = "background"
    CAPABILITY = "capability"
    SCOPE_REDIRECT = "scope_redirect"
    ABSTENTION = "abstention"
    PARTIAL = "partial"
    LIVE = "live"
    MIXED = "mixed"
    CONFLICT = "conflict"
    REQUIRES_INPUT = "requires_input"


class AnswerSectionKind(StrEnum):
    """Authority-labelled parts composed by the application agent."""

    CURRENT_RECORDS = "current_records"
    REVIEWED_GUIDANCE = "reviewed_guidance"
    CONFLICTING_GUIDANCE = "conflicting_guidance"
    GENERAL_BACKGROUND = "general_background"
    OFFICIAL_HANDOFF = "official_handoff"
    UNCERTAINTY = "uncertainty"


class AuthorityClass(StrEnum):
    PROVINCIAL_GOVERNMENT = "provincial_government"
    PROVINCIAL_PUBLIC_HEALTH = "provincial_public_health"
    WILDFIRE_PREPAREDNESS = "recognized_wildfire_preparedness_program"
    LOCAL_AUTHORITY = "local_authority"


class TemporalClass(StrEnum):
    STABLE_GUIDANCE = "stable_guidance"


class RetrievalTextStrategy(StrEnum):
    ORIGINAL_V1 = "original_v1"
    METADATA_CONTEXT_V1 = "metadata_context_v1"
    DOCUMENT_CONTEXT_V2 = "document_context_v2"


class ReasonCode(StrEnum):
    CAPABILITY_OVERVIEW = "capability_overview"
    SCOPE_REDIRECT = "scope_redirect"
    PERSONALIZED_SAFETY_DECISION = "personalized_safety_decision"
    PERSONALIZED_MEDICAL_ADVICE = "personalized_medical_advice"
    POLICY_MANIPULATION = "policy_manipulation"
    LIVE_DATA_REQUIRED = "live_data_required"
    PLANNING_UNAVAILABLE = "planning_unavailable"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    RETRIEVAL_INCOMPLETE = "retrieval_incomplete"
    NO_APPROVED_EVIDENCE = "no_approved_evidence"
    WRONG_TEMPORAL_CLASS = "wrong_temporal_class"
    REQUIRED_AUTHORITY_MISSING = "required_authority_missing"
    APPROVED_STATIC_EVIDENCE = "approved_static_evidence"
    GENERATION_UNAVAILABLE = "generation_unavailable"
    DRAFT_VALIDATION_FAILED = "draft_validation_failed"
    MODEL_ABSTAINED = "model_abstained"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    HIGH_RISK_CLAIM_NOT_STRUCTURED = "high_risk_claim_not_structured"


class SupportStatus(StrEnum):
    ANSWERABLE = "answerable"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REQUIRES_LIVE_DATA = "requires_live_data"
    PROHIBITED = "prohibited"
    CONFLICT = "conflict"


class ResponseStatus(StrEnum):
    ANSWER = "answer"
    ABSTENTION = "abstention"
    ERROR = "error"


class RequiredInputKind(StrEnum):
    LOCATION = "location"


class MapContext(FrozenStrictModel):
    """Bounded, user-visible map state supplied with an agent request."""

    selected_live_result_id: str | None = Field(default=None, min_length=1, max_length=200)
    visible_live_result_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=100
    )
    viewport: MapViewport | None = None

    @field_validator("visible_live_result_ids")
    @classmethod
    def require_unique_result_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("visible map result IDs must be unique")
        return value


class RequiredInput(FrozenStrictModel):
    """One bounded input needed to resume the current agent task."""

    kind: RequiredInputKind
    prompt: str = Field(min_length=1, max_length=300)
    continuation_question: str = Field(min_length=1, max_length=2_000)


class ConversationTurn(FrozenStrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6_000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("conversation content cannot be blank")
        return normalized


class QueryRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)
    location: LocationInput | None = None
    context: MapContext = Field(default_factory=MapContext)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


class RetrievalRequest(FrozenStrictModel):
    query: str = Field(min_length=1, max_length=2_000)
    required_authorities: frozenset[AuthorityClass] = Field(default_factory=frozenset)
    purpose: str = Field(default="answer", min_length=1, max_length=80)


class PlanningDecision(FrozenStrictModel):
    relation: QueryRelation
    retrieval_queries: list[Annotated[str, Field(min_length=1, max_length=2_000)]] = Field(
        default_factory=list, max_length=3
    )
    explanation: str = Field(min_length=1, max_length=300)
    required_aspects: list[Annotated[str, Field(min_length=2, max_length=160)]] = Field(
        default_factory=list, max_length=6
    )

    @field_validator("retrieval_queries")
    @classmethod
    def normalize_and_deduplicate_queries(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            query = " ".join(value.split())
            if not query:
                raise ValueError("retrieval query cannot be blank")
            key = query.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(query)
        return normalized

    @model_validator(mode="after")
    def validate_relation_queries(self) -> PlanningDecision:
        if self.relation == QueryRelation.TANGENT and self.retrieval_queries:
            raise ValueError("tangent planning decisions cannot retrieve")
        if self.relation != QueryRelation.TANGENT and not self.retrieval_queries:
            raise ValueError("related planning decisions require a retrieval query")
        return self


class QueryPlan(FrozenStrictModel):
    original_question: str
    normalized_question: str
    route: QueryRoute
    boundary_reason: ReasonCode | None = None
    relation: QueryRelation | None = None
    retrieval_requests: list[RetrievalRequest] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)
    required_aspects: list[str] = Field(default_factory=list, max_length=6)


class RetrievalHit(FrozenStrictModel):
    chunk_id: str
    parent_record_id: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    page_number: int | None
    section_title: str | None
    locator: str | None
    temporal_class: TemporalClass
    authority_class: AuthorityClass
    document_sha256: str
    chunk_index: int
    text: str
    review_provenance: Literal["native_text", "human_verified_repair"] = "native_text"
    matched_queries: tuple[str, ...] = ()
    bm25_positions: tuple[int, ...] = ()
    vector_positions: tuple[int, ...] = ()
    bm25_rank: int | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    rrf_rank: int | None = None
    rrf_score: float | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None


class RetrievalBundle(StrictModel):
    bm25_hits: list[RetrievalHit] = Field(default_factory=list)
    vector_hits: list[RetrievalHit] = Field(default_factory=list)
    fused_hits: list[RetrievalHit] = Field(default_factory=list)
    reranked_hits: list[RetrievalHit] = Field(default_factory=list)
    rankings: dict[str, list[str]] = Field(default_factory=dict)
    complete: bool = True
    errors: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    provider_usage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    provider_attempts: dict[str, int] = Field(default_factory=dict)
    provider_models: dict[str, str] = Field(default_factory=dict)


class EvidenceSpan(FrozenStrictModel):
    evidence_id: str
    primary_chunk_ids: list[str] = Field(min_length=1)
    chunk_ids: list[str] = Field(min_length=1)
    primary_text: str
    context_text: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    page_number: int | None
    section_title: str | None
    locator: str | None
    temporal_class: TemporalClass
    authority_class: AuthorityClass
    document_sha256: str
    review_provenance: Literal["native_text", "human_verified_repair"] = "native_text"


class EvidenceQuoteCandidate(FrozenStrictModel):
    quote_id: str
    evidence_id: str
    text: Annotated[str, Field(min_length=1, max_length=500)]


class EvidenceConflict(FrozenStrictModel):
    conflict_id: str = Field(pattern=r"^X[1-9][0-9]*$")
    quote_ids: list[str] = Field(min_length=2, max_length=4)
    differing_terms: list[str] = Field(min_length=2, max_length=16)
    explanation: str = Field(min_length=1, max_length=300)


class EvidencePacket(FrozenStrictModel):
    question: str
    corpus_version: str
    items: list[EvidenceSpan]
    quote_candidates: list[EvidenceQuoteCandidate] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_packet_identity(self) -> EvidencePacket:
        validate_evidence_packet_identity(self)
        return self


class SupportDecision(FrozenStrictModel):
    status: SupportStatus
    reason_code: ReasonCode
    explanation: str
    supported_aspects: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)


class ClaimSupport(FrozenStrictModel):
    evidence_id: str = Field(min_length=1)
    quote: Annotated[str, Field(min_length=1, max_length=500)]


class PublicClaim(FrozenStrictModel):
    claim_id: str = Field(pattern=r"^[CL][1-9][0-9]*$")
    text: str = Field(min_length=1, max_length=600)
    evidence_status: EvidenceStatus
    supports: list[ClaimSupport] = Field(default_factory=list, max_length=5)
    trust: ClaimTrust | None = None
    publication: PublicationAuthority | None = None

    @field_validator("text")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_evidence_mode(self) -> PublicClaim:
        pairs = [(item.evidence_id, item.quote) for item in self.supports]
        if len(pairs) != len(set(pairs)):
            raise ValueError("claim support pairs must be unique")
        if self.evidence_status == EvidenceStatus.VERIFIED_CORPUS and self.publication is None:
            raise ValueError("verified corpus claims require publication")
        if self.evidence_status == EvidenceStatus.VERIFIED_CORPUS and not self.supports:
            raise ValueError("verified corpus claims require support")
        if self.evidence_status == EvidenceStatus.GENERAL_BACKGROUND and self.supports:
            raise ValueError("general background claims cannot cite corpus evidence")
        return self


class DraftProposalClaim(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    evidence_quote_ids: list[str] = Field(min_length=1, max_length=5)

    @field_validator("text")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be blank")
        return value


class GroundedDraft(StrictModel):
    answer_type: Literal["grounded"]
    claims: list[DraftProposalClaim] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    requires_live_verification: Literal[False] = False


BACKGROUND_LIMITATION = "General background — not verified against the FireLens corpus."


class BackgroundDraftClaim(StrictModel):
    text: str = Field(min_length=1, max_length=600)


class BackgroundDraft(StrictModel):
    answer_type: Literal["background"]
    claims: list[BackgroundDraftClaim] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=3)
    requires_live_verification: Literal[False] = False

    @model_validator(mode="after")
    def require_background_label(self) -> BackgroundDraft:
        if BACKGROUND_LIMITATION not in self.limitations:
            raise ValueError("background answer requires the exact background limitation")
        return self


class AbstentionDraft(StrictModel):
    """A bounded model proposal that cannot carry an answer claim."""

    answer_type: Literal["abstention"]
    explanation: str = Field(min_length=1, max_length=1_000)
    reason_code: ReasonCode
    claims: list[None] = Field(default_factory=list, max_length=0)


class PublicEvidence(FrozenStrictModel):
    evidence_id: str
    title: str
    publisher: str
    canonical_url: HttpUrl
    locator: str | None
    temporal_class: Literal[TemporalClass.STABLE_GUIDANCE]
    review_provenance: Literal["native_text", "human_verified_repair"] = "native_text"
    primary_text: str
    context_text: str


class AnswerSection(FrozenStrictModel):
    """A user-visible answer part whose authority is fixed by local code."""

    kind: AnswerSectionKind
    heading: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=PUBLIC_ANSWER_MAX_CHARS)


class SearchResponse(StrictModel):
    trace_id: str
    plan: QueryPlan
    retrieval: RetrievalBundle
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    support: SupportDecision


class AskResponse(StrictModel):
    status: ResponseStatus
    trace_id: str
    response_mode: ResponseMode = ResponseMode.ABSTENTION
    answer: str | None = Field(default=None, max_length=PUBLIC_ANSWER_MAX_CHARS)
    answer_sections: list[AnswerSection] = Field(default_factory=list, max_length=5)
    history_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=ASSISTANT_HISTORY_LIMIT,
    )
    claims: list[PublicClaim] = Field(default_factory=list, max_length=MAX_PUBLIC_CLAIMS)
    evidence: list[PublicEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    related_links: list[RelatedLink] = Field(default_factory=list, max_length=MAX_RELATED_LINKS)
    reason_code: ReasonCode | None = None
    validation: ValidationReport | None = None
    error_kind: str | None = None
    live_results: list[LiveResult] = Field(default_factory=list)
    aggregate_freshness: AggregateFreshness | None = None
    unavailable_layers: list[LiveResultKind] = Field(default_factory=list)
    required_input: RequiredInput | None = None
    selected_live_result_id: str | None = Field(default=None, min_length=1, max_length=200)
    resolved_location: CoarseResolvedLocation | None = None
    status_banner: AnswerStatusBanner | None = None
    supported_items: list[str] = Field(default_factory=list, max_length=12)
    unknown_items: list[str] = Field(default_factory=list, max_length=12)
    proof_cards: list[ProofCard] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_public_state(self) -> AskResponse:
        self._validate_history()
        evidence_ids = self._validate_unique_public_ids()
        self._validate_answer_sections()
        validators = {
            ResponseMode.GROUNDED: self._validate_grounded,
            ResponseMode.PARTIAL: self._validate_grounded,
            ResponseMode.CONFLICT: self._validate_grounded,
            ResponseMode.BACKGROUND: self._validate_background,
            ResponseMode.LIVE: self._validate_live,
            ResponseMode.MIXED: self._validate_mixed,
            ResponseMode.CAPABILITY: self._validate_conversational,
            ResponseMode.SCOPE_REDIRECT: self._validate_conversational,
            ResponseMode.REQUIRES_INPUT: self._validate_requires_input,
        }
        validators.get(self.response_mode, self._validate_abstention)(evidence_ids)
        if (
            self.response_mode != ResponseMode.REQUIRES_INPUT
            and self.required_input is not None
        ):
            raise ValueError("required input is only valid for resumable input responses")
        if not self.live_results and self.aggregate_freshness is not None:
            raise ValueError("aggregate freshness requires live results")
        error = ask_claim_publication_error(self)
        if error:
            raise ValueError(error)
        if self.response_mode in {ResponseMode.LIVE, ResponseMode.MIXED}:
            error = current_records_binding_error(
                self.answer, self.live_results, self.answer_sections
            )
            if error:
                raise ValueError(error)
        attach_proof_presentation(self)
        return self

    def _validate_answer_sections(self) -> None:
        if not self.answer_sections:
            return
        if self.answer is None:
            raise ValueError("answer sections require a public answer")
        kinds = [section.kind for section in self.answer_sections]
        if len(kinds) != len(set(kinds)):
            raise ValueError("answer section kinds must be unique")
        claim_statuses = {claim.evidence_status for claim in self.claims}
        requirements = {
            AnswerSectionKind.CURRENT_RECORDS: bool(self.live_results),
            AnswerSectionKind.REVIEWED_GUIDANCE: (
                EvidenceStatus.VERIFIED_CORPUS in claim_statuses and bool(self.evidence)
            ),
            AnswerSectionKind.CONFLICTING_GUIDANCE: (
                self.reason_code == ReasonCode.CONFLICTING_EVIDENCE
                and EvidenceStatus.VERIFIED_CORPUS in claim_statuses
                and bool(self.evidence)
                and self.validation is not None
                and self.validation.accepted
            ),
            AnswerSectionKind.GENERAL_BACKGROUND: (
                EvidenceStatus.GENERAL_BACKGROUND in claim_statuses
            ),
            AnswerSectionKind.OFFICIAL_HANDOFF: bool(self.related_links),
            AnswerSectionKind.UNCERTAINTY: bool(self.limitations),
        }
        unsupported = [kind.value for kind in kinds if not requirements[kind]]
        if unsupported:
            raise ValueError(
                "answer sections require matching typed response data: "
                + ", ".join(unsupported)
            )
        current_text = "\n".join(
            section.text
            for section in self.answer_sections
            if section.kind == AnswerSectionKind.CURRENT_RECORDS
        )
        if current_text and any(
            claim.text and claim.text in current_text for claim in self.claims
        ):
            raise ValueError("current record section cannot contain non-live public claim text")
        if (
            self.response_mode == ResponseMode.CONFLICT
            or AnswerSectionKind.CONFLICTING_GUIDANCE in kinds
        ):
            self._validate_conflict_rendering()
            return
        canonical_text = {
            AnswerSectionKind.REVIEWED_GUIDANCE: render_claim_texts(
                claim
                for claim in self.claims
                if claim.evidence_status == EvidenceStatus.VERIFIED_CORPUS
            ),
            AnswerSectionKind.GENERAL_BACKGROUND: render_claim_texts(
                claim
                for claim in self.claims
                if claim.evidence_status == EvidenceStatus.GENERAL_BACKGROUND
            ),
        }
        mismatched = [
            section.kind.value
            for section in self.answer_sections
            if section.kind in canonical_text and section.text != canonical_text[section.kind]
        ]
        if mismatched:
            raise ValueError(
                "answer section text must match its typed public claims: "
                + ", ".join(mismatched)
            )

    def _validate_history(self) -> None:
        if self.answer is None:
            if self.history_text is not None:
                raise ValueError("history text requires a public answer")
            return
        history_prefix = response_history_prefix(
            response_mode=self.response_mode.value,
            reason_code=(self.reason_code.value if self.reason_code is not None else None),
            section_kinds=[section.kind.value for section in self.answer_sections],
            aggregate_freshness=(
                self.aggregate_freshness.value if self.aggregate_freshness is not None else None
            ),
        )
        expected_history = render_assistant_history(
            authority_prefix=history_prefix,
            answer=self.answer,
            limitations=self.limitations,
        )
        if self.history_text is None:
            self.history_text = expected_history
        elif self.history_text != expected_history:
            raise ValueError("history text must be derived from the public answer")

    def _validate_unique_public_ids(self) -> list[str]:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("public claim IDs must be unique")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("public evidence IDs must be unique")
        return evidence_ids

    def _validate_grounded(self, evidence_ids: list[str]) -> None:
        if self.status != ResponseStatus.ANSWER or not self.claims or not self.evidence:
            raise ValueError("grounded responses require accepted claims")
        if any(
            claim.evidence_status != EvidenceStatus.VERIFIED_CORPUS for claim in self.claims
        ):
            raise ValueError("grounded responses contain only verified claims")
        self._validate_support_ids(evidence_ids, label="grounded")
        if self.response_mode == ResponseMode.CONFLICT:
            if self.validation is None or not self.validation.accepted:
                raise ValueError("conflict responses require deterministic validation")
            self._validate_conflict_rendering()
            return
        canonical_answer = render_claim_texts(self.claims)
        if len(canonical_answer) > MAX_GROUNDED_ANSWER_CHARS:
            raise ValueError("grounded public claim text exceeds its validated answer limit")
        if (
            self.response_mode == ResponseMode.GROUNDED or not self.answer_sections
        ) and self.answer != canonical_answer:
            raise ValueError("grounded answer must be rendered from its public claims")

    def _validate_conflict_rendering(self) -> None:
        sections = [(section.kind.value, section.text) for section in self.answer_sections]
        if not is_canonical_conflict_answer(self.answer, sections):
            raise ValueError("conflict response must use the deterministic conflict renderer")

    def _validate_background(self, _evidence_ids: list[str]) -> None:
        if self.status != ResponseStatus.ANSWER or not self.claims:
            raise ValueError("background responses require claims")
        if any(
            claim.evidence_status != EvidenceStatus.GENERAL_BACKGROUND for claim in self.claims
        ):
            raise ValueError("background responses contain only background claims")
        if self.evidence:
            raise ValueError("background responses cannot expose evidence")
        if BACKGROUND_LIMITATION not in self.limitations:
            raise ValueError("background response requires its visible limitation")
        if len(self.claims) > MAX_BACKGROUND_CLAIMS:
            raise ValueError("background responses exceed the public claim limit")
        canonical_answer = render_claim_texts(self.claims)
        if not self.answer_sections and self.answer != canonical_answer:
            raise ValueError("background answer must be rendered from its public claims")

    def _validate_live(self, _evidence_ids: list[str]) -> None:
        if self.status != ResponseStatus.ANSWER or not self.answer:
            raise ValueError("live responses require a public answer")
        if self.claims or self.evidence:
            raise ValueError("live responses cannot present static evidence claims")
        if not self.live_results and self.resolved_location is None:
            raise ValueError("empty live responses require a coarse map focus")
        if self.aggregate_freshness != aggregate_live_freshness(self.live_results):
            raise ValueError("live response requires matching aggregate freshness")

    def _validate_mixed(self, evidence_ids: list[str]) -> None:
        if self.status != ResponseStatus.ANSWER or not self.live_results or not self.answer:
            raise ValueError("mixed responses require live results and an answer")
        if not self.claims and not self.related_links:
            raise ValueError("mixed responses require a non-live answer or official handoff")
        if (
            any(
                claim.evidence_status == EvidenceStatus.GENERAL_BACKGROUND
                for claim in self.claims
            )
            and BACKGROUND_LIMITATION not in self.limitations
        ):
            raise ValueError("mixed background claims require their visible limitation")
        self._validate_support_ids(evidence_ids, label="mixed")
        if self.claims and (self.validation is None or not self.validation.accepted):
            raise ValueError("mixed response claims require accepted validation")
        if self.aggregate_freshness != aggregate_live_freshness(self.live_results):
            raise ValueError("mixed response requires matching aggregate freshness")

    def _validate_support_ids(self, evidence_ids: list[str], *, label: str) -> None:
        supported_ids = {
            support.evidence_id for claim in self.claims for support in claim.supports
        }
        if supported_ids != set(evidence_ids):
            raise ValueError(
                f"{label} claim supports and public evidence must reference the same IDs"
            )

    def _validate_conversational(self, _evidence_ids: list[str]) -> None:
        if self.status != ResponseStatus.ANSWER or self.claims or self.evidence:
            raise ValueError("local conversational responses cannot contain claims")

    def _validate_requires_input(self, _evidence_ids: list[str]) -> None:
        if (
            self.status != ResponseStatus.ANSWER
            or not self.answer
            or self.required_input is None
        ):
            raise ValueError("resumable input responses require a prompt and continuation")
        if self.claims or self.evidence or self.live_results:
            raise ValueError("resumable input responses cannot contain evidence results")

    def _validate_abstention(self, _evidence_ids: list[str]) -> None:
        if self.status not in {ResponseStatus.ABSTENTION, ResponseStatus.ERROR}:
            raise ValueError("answer status requires a non-abstention response mode")
        if self.claims or self.evidence or self.live_results:
            raise ValueError("abstention and error responses cannot contain evidence claims")


class PlanningResponse(FrozenStrictModel):
    model: str
    decision: PlanningDecision
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)


class GenerationResponse(FrozenStrictModel):
    model: str
    draft: GroundedDraft | BackgroundDraft
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
