"""Bounded transport and provider-response contracts re-exported by contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import Field, HttpUrl, field_validator

from firelens.contract_base import FrozenStrictModel

MAX_RELATED_LINKS = 4
RELATED_LINK_TITLE_MAX_CHARS = 120
RELATED_LINK_DESCRIPTION_MAX_CHARS = 240

_HISTORY_SECTION_LABELS = {
    "current_records": "Official current records",
    "reviewed_guidance": "Reviewed guidance",
    "conflicting_guidance": "Conflicting reviewed sources",
    "general_background": "General background (not corpus-verified)",
    "official_handoff": "Official source handoff",
    "uncertainty": "Uncertainty about what FireLens could establish",
}
_HISTORY_MODE_LABELS = {
    "grounded": "Reviewed guidance",
    "partial": "Reviewed guidance + uncertainty",
    "conflict": "Conflicting reviewed sources",
    "background": "General background (not corpus-verified)",
    "live": "Official current records",
    "mixed": "Mixed official and labelled non-live information",
    "capability": "FireLens capability information",
    "scope_redirect": "Official source handoff",
    "requires_input": "FireLens task-continuation request",
    "abstention": "FireLens abstention",
}
_SAFETY_HISTORY_PREFIXES = {
    "personalized_safety_decision": (
        "Safety boundary: FireLens cannot make a personal safety or evacuation decision."
    ),
    "personalized_medical_advice": (
        "Safety boundary: FireLens cannot provide personalized medical advice."
    ),
    "policy_manipulation": (
        "Safety boundary: FireLens did not bypass its evidence or safety rules."
    ),
}


def response_history_prefix(
    *, response_mode: str, reason_code: str | None, section_kinds: Sequence[str]
) -> str:
    """Return a deterministic, user-facing authority label for later turns."""

    safety_prefix = _SAFETY_HISTORY_PREFIXES.get(reason_code or "")
    if safety_prefix is not None:
        return safety_prefix
    if section_kinds:
        labels = list(dict.fromkeys(_HISTORY_SECTION_LABELS[kind] for kind in section_kinds))
        return "Authority: " + " + ".join(labels) + "."
    return "Authority: " + _HISTORY_MODE_LABELS[response_mode] + "."


class ValidationReport(FrozenStrictModel):
    accepted: bool
    schema_valid: bool = True
    citation_ids_valid: bool
    quotes_exact: bool
    claim_support_valid: bool = True
    policy_valid: bool
    errors: list[str] = Field(default_factory=list)


class RelatedLink(FrozenStrictModel):
    """An official destination for information FireLens does not ingest live."""

    title: str = Field(min_length=1, max_length=RELATED_LINK_TITLE_MAX_CHARS)
    url: HttpUrl
    description: str = Field(min_length=1, max_length=RELATED_LINK_DESCRIPTION_MAX_CHARS)


class HealthResponse(FrozenStrictModel):
    status: Literal["ready", "not_ready"]
    corpus_ready: bool
    index_ready: bool
    provider_configured: bool
    zdr_required: bool
    zdr_policy_state: Literal[
        "disabled",
        "stage_bound_unprobed",
        "required_stages_eligible",
        "failed",
    ]
    data_collection: Literal["deny"]
    allow_fallbacks: bool
    embedding_zdr: Literal["required", "optional"]
    reranking_zdr: Literal["required", "optional"]
    generation_zdr: Literal["required", "optional"]
    embedding_zdr_state: Literal[
        "not_required", "unprobed", "eligible", "zdr_optional", "failed"
    ]
    generation_zdr_state: Literal[
        "not_required", "unprobed", "eligible", "zdr_optional", "failed"
    ]
    reranking_zdr_state: Literal[
        "not_required",
        "unprobed",
        "eligible",
        "zdr_optional",
        "failed",
    ]
    provider_state: Literal[
        "not_configured",
        "configured_unprobed",
        "available",
        "degraded",
        "circuit_open",
    ]
    corpus_version: str | None = None
    chunk_count: int | None = None
    release_version: str
    build_commit: str | None = None
    deployment_id: str | None = None
    candidate_id: str | None = None
    candidate_sha256: str | None = None
    embedding_model: str | None = None
    rerank_model: str | None = None
    generation_model: str | None = None
    retrieval_text_strategy: str | None = None
    rate_limit_scope: Literal["instance_local"] = "instance_local"
    problems: list[str] = Field(default_factory=list)


class LivenessResponse(FrozenStrictModel):
    status: Literal["alive"] = "alive"


class ErrorEnvelope(FrozenStrictModel):
    trace_id: str
    error_kind: str
    message: str
    retryable: bool = False


FeedbackCategory = Literal[
    "helpful",
    "incorrect_or_unsupported",
    "missing_information",
    "stale_or_wrong_live_data",
    "confusing",
    "safety_concern",
    "accessibility_issue",
]


class FeedbackRequest(FrozenStrictModel):
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    category: FeedbackCategory


class FeedbackResponse(FrozenStrictModel):
    accepted: Literal[True] = True


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
