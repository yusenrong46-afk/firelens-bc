"""Strict data contracts passed between FireLens RAG stages.

The public models deliberately make evidence provenance visible.  Internal model
drafts are separate types so a background answer cannot accidentally acquire a
corpus citation and a grounded answer cannot omit one.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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


class AuthorityClass(StrEnum):
    PROVINCIAL_GOVERNMENT = "provincial_government"
    PROVINCIAL_PUBLIC_HEALTH = "provincial_public_health"
    WILDFIRE_PREPAREDNESS = "recognized_wildfire_preparedness_program"


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


class LocationInput(FrozenStrictModel):
    """Coarse, opt-in location used only for the current live-data request."""

    label: str | None = Field(default=None, min_length=2, max_length=120)
    latitude: float | None = Field(default=None, ge=48.0, le=61.0)
    longitude: float | None = Field(default=None, ge=-140.0, le=-113.0)
    radius_km: float = Field(default=50.0, ge=1.0, le=200.0)

    @field_validator("label")
    @classmethod
    def reject_exact_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        lowered = normalized.casefold()
        street_terms = (" street", " st ", " avenue", " ave ", " road", " rd ", " boulevard")
        if any(character.isdigit() for character in normalized) or any(
            term in f" {lowered} " for term in street_terms
        ):
            raise ValueError("use a community or place label, not an exact address")
        return normalized

    @field_validator("latitude", "longitude")
    @classmethod
    def round_coordinates(cls, value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @model_validator(mode="after")
    def require_one_location_form(self) -> LocationInput:
        has_label = self.label is not None
        has_coordinates = self.latitude is not None or self.longitude is not None
        if has_label == has_coordinates:
            raise ValueError("provide either a place label or coordinates")
        if has_coordinates and (self.latitude is None or self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class QueryRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)
    location: LocationInput | None = None

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


class SupportDecision(FrozenStrictModel):
    status: SupportStatus
    reason_code: ReasonCode
    explanation: str
    supported_aspects: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)


class LiveResultKind(StrEnum):
    INCIDENT = "incident"
    PERIMETER = "perimeter"
    EVACUATION = "evacuation"


class GeometryRelation(StrEnum):
    INSIDE = "inside"
    NEARBY = "nearby"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class LiveResult(FrozenStrictModel):
    result_id: str = Field(min_length=1, max_length=200)
    kind: LiveResultKind
    authority: str = "BC Wildfire Service"
    source_url: HttpUrl
    source_updated_at: datetime
    retrieved_at: datetime
    freshness: Freshness
    status: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=300)
    incident_number: str | None = Field(default=None, max_length=100)
    size_hectares: float | None = Field(default=None, ge=0)
    issuer: str | None = Field(default=None, max_length=300)
    geometry_relation: GeometryRelation = GeometryRelation.UNKNOWN
    geometry: dict[str, Any]


class LiveMapResponse(FrozenStrictModel):
    generated_at: datetime
    results: list[LiveResult]
    unavailable_layers: list[LiveResultKind] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClaimSupport(FrozenStrictModel):
    evidence_id: str = Field(min_length=1)
    quote: Annotated[str, Field(min_length=1, max_length=500)]


class PublicClaim(FrozenStrictModel):
    claim_id: str = Field(pattern=r"^C[1-9][0-9]*$")
    text: str = Field(min_length=1, max_length=600)
    evidence_status: EvidenceStatus
    supports: list[ClaimSupport] = Field(default_factory=list, max_length=5)

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


class ValidationReport(FrozenStrictModel):
    accepted: bool
    schema_valid: bool = True
    citation_ids_valid: bool
    quotes_exact: bool
    claim_support_valid: bool = True
    policy_valid: bool
    errors: list[str] = Field(default_factory=list)


class PublicEvidence(FrozenStrictModel):
    evidence_id: str
    title: str
    publisher: str
    canonical_url: HttpUrl
    locator: str | None
    temporal_class: Literal[TemporalClass.STABLE_GUIDANCE]
    primary_text: str
    context_text: str


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
    answer: str | None = None
    claims: list[PublicClaim] = Field(default_factory=list)
    evidence: list[PublicEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    reason_code: ReasonCode | None = None
    validation: ValidationReport | None = None
    error_kind: str | None = None
    live_results: list[LiveResult] = Field(default_factory=list)
    unavailable_layers: list[LiveResultKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_public_state(self) -> AskResponse:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("public claim IDs must be unique")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("public evidence IDs must be unique")

        if self.response_mode in {
            ResponseMode.GROUNDED,
            ResponseMode.PARTIAL,
            ResponseMode.CONFLICT,
        }:
            if self.status != ResponseStatus.ANSWER or not self.claims or not self.evidence:
                raise ValueError("grounded responses require accepted claims")
            if any(
                claim.evidence_status != EvidenceStatus.VERIFIED_CORPUS for claim in self.claims
            ):
                raise ValueError("grounded responses contain only verified claims")
            supported_ids = {
                support.evidence_id for claim in self.claims for support in claim.supports
            }
            if supported_ids != set(evidence_ids):
                raise ValueError(
                    "grounded claim supports and public evidence must reference the same IDs"
                )
            if self.response_mode == ResponseMode.CONFLICT and (
                self.validation is None or not self.validation.accepted
            ):
                raise ValueError("conflict responses require deterministic validation")
        elif self.response_mode == ResponseMode.BACKGROUND:
            if self.status != ResponseStatus.ANSWER or not self.claims:
                raise ValueError("background responses require claims")
            if any(
                claim.evidence_status != EvidenceStatus.GENERAL_BACKGROUND
                for claim in self.claims
            ):
                raise ValueError("background responses contain only background claims")
            if self.evidence:
                raise ValueError("background responses cannot expose evidence")
            if BACKGROUND_LIMITATION not in self.limitations:
                raise ValueError("background response requires its visible limitation")
        elif self.response_mode == ResponseMode.LIVE:
            if self.status != ResponseStatus.ANSWER or not self.live_results or not self.answer:
                raise ValueError("live responses require current official results")
            if self.claims or self.evidence:
                raise ValueError("live responses cannot present static evidence claims")
        elif self.response_mode == ResponseMode.MIXED:
            if self.status != ResponseStatus.ANSWER or not self.live_results or not self.answer:
                raise ValueError("mixed responses require live results and an answer")
            if not self.claims or not self.evidence:
                raise ValueError("mixed responses require supported static claims")
            if any(
                claim.evidence_status != EvidenceStatus.VERIFIED_CORPUS for claim in self.claims
            ):
                raise ValueError("mixed responses contain only verified static claims")
            supported_ids = {
                support.evidence_id for claim in self.claims for support in claim.supports
            }
            if supported_ids != set(evidence_ids):
                raise ValueError(
                    "mixed claim supports and public evidence must reference the same IDs"
                )
            if self.validation is None or not self.validation.accepted:
                raise ValueError("mixed responses require accepted static validation")
        elif self.response_mode in {ResponseMode.CAPABILITY, ResponseMode.SCOPE_REDIRECT}:
            if self.status != ResponseStatus.ANSWER or self.claims or self.evidence:
                raise ValueError("local conversational responses cannot contain claims")
        else:
            if self.status not in {ResponseStatus.ABSTENTION, ResponseStatus.ERROR}:
                raise ValueError("answer status requires a non-abstention response mode")
            if self.claims or self.evidence or self.live_results:
                raise ValueError(
                    "abstention and error responses cannot contain evidence claims"
                )
        return self


class HealthResponse(FrozenStrictModel):
    status: Literal["ready", "not_ready"]
    corpus_ready: bool
    index_ready: bool
    provider_configured: bool
    corpus_version: str | None = None
    chunk_count: int | None = None
    release_version: str
    build_commit: str | None = None
    deployment_id: str | None = None
    rate_limit_scope: Literal["instance_local"] = "instance_local"
    problems: list[str] = Field(default_factory=list)


class LivenessResponse(FrozenStrictModel):
    status: Literal["alive"] = "alive"


class ErrorEnvelope(FrozenStrictModel):
    trace_id: str
    error_kind: str
    message: str
    retryable: bool = False


class EmbeddingResponse(FrozenStrictModel):
    model: str
    vectors: list[list[float]]
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)


class RerankResult(FrozenStrictModel):
    index: int = Field(ge=0)
    relevance_score: float


class RerankResponse(FrozenStrictModel):
    model: str
    results: list[RerankResult]
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)


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


class DocumentContextItem(FrozenStrictModel):
    chunk_id: str = Field(min_length=1)
    context: str = Field(min_length=20, max_length=800)

    @field_validator("context")
    @classmethod
    def bound_context_words(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not 20 <= len(normalized.split()) <= 120:
            raise ValueError("document context must contain 20 to 120 words")
        return normalized


class DocumentContextDraft(FrozenStrictModel):
    items: list[DocumentContextItem] = Field(min_length=1, max_length=12)


class DocumentContextResponse(FrozenStrictModel):
    model: str
    draft: DocumentContextDraft
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
