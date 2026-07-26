"""Strict data contracts passed between FireLens RAG stages."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QueryRoute(StrEnum):
    STATIC = "static"
    LIVE = "live"
    PROHIBITED = "prohibited"


class SupportStatus(StrEnum):
    ANSWERABLE = "answerable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REQUIRES_LIVE_DATA = "requires_live_data"
    PROHIBITED = "prohibited"


class ResponseStatus(StrEnum):
    ANSWER = "answer"
    ABSTENTION = "abstention"
    ERROR = "error"


class ConversationTurn(FrozenStrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class QueryRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


class RetrievalRequest(FrozenStrictModel):
    query: str = Field(min_length=1, max_length=2_000)
    required_authority: str | None = None


class QueryPlan(FrozenStrictModel):
    original_question: str
    normalized_question: str
    route: QueryRoute
    retrieval_requests: list[RetrievalRequest] = Field(max_length=4)
    limitations: list[str] = Field(default_factory=list)


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
    temporal_class: str
    authority_class: str
    document_sha256: str
    chunk_index: int
    text: str
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
    complete: bool = True
    errors: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


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
    temporal_class: str
    authority_class: str
    document_sha256: str


class EvidenceQuoteCandidate(FrozenStrictModel):
    quote_id: str
    evidence_id: str
    text: Annotated[str, Field(min_length=1, max_length=500)]


class EvidencePacket(FrozenStrictModel):
    question: str
    corpus_version: str
    items: list[EvidenceSpan]
    quote_candidates: list[EvidenceQuoteCandidate] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SupportDecision(FrozenStrictModel):
    status: SupportStatus
    reason_code: str
    explanation: str


class DraftClaim(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)
    evidence_quotes: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=5
    )

    @field_validator("text")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be blank")
        return value

    @field_validator("evidence_quotes")
    @classmethod
    def reject_blank_quotes(cls, value: list[str]) -> list[str]:
        if any(not quote.strip() for quote in value):
            raise ValueError("evidence quotes cannot be blank")
        return value


class DraftProposalClaim(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    evidence_quote_ids: list[str] = Field(min_length=1, max_length=5)

    @field_validator("text")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be blank")
        return value


class DraftAnswer(StrictModel):
    answer_type: Literal["guidance", "abstention"]
    answer: str = Field(min_length=1, max_length=2_500)
    claims: list[DraftProposalClaim] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    requires_live_verification: bool = False

    @field_validator("answer")
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer cannot be blank")
        return value


class ValidationReport(FrozenStrictModel):
    accepted: bool
    schema_valid: bool = True
    citation_ids_valid: bool
    quotes_exact: bool
    policy_valid: bool
    errors: list[str] = Field(default_factory=list)


class PublicSource(FrozenStrictModel):
    evidence_id: str
    title: str
    publisher: str
    canonical_url: HttpUrl
    locator: str | None


class SearchResponse(StrictModel):
    trace_id: str
    plan: QueryPlan
    retrieval: RetrievalBundle
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    support: SupportDecision


class AskResponse(StrictModel):
    status: ResponseStatus
    trace_id: str
    answer: str | None = None
    claims: list[DraftClaim] = Field(default_factory=list)
    sources: list[PublicSource] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    validation: ValidationReport | None = None
    error_kind: str | None = None


class HealthResponse(FrozenStrictModel):
    status: Literal["ready", "not_ready"]
    corpus_ready: bool
    index_ready: bool
    provider_configured: bool
    corpus_version: str | None = None
    chunk_count: int | None = None
    problems: list[str] = Field(default_factory=list)


class EmbeddingResponse(FrozenStrictModel):
    model: str
    vectors: list[list[float]]
    usage: dict[str, Any] = Field(default_factory=dict)


class RerankResult(FrozenStrictModel):
    index: int = Field(ge=0)
    relevance_score: float


class RerankResponse(FrozenStrictModel):
    model: str
    results: list[RerankResult]
    usage: dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(FrozenStrictModel):
    model: str
    draft: DraftAnswer
    usage: dict[str, Any] = Field(default_factory=dict)
