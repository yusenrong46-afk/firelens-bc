"""Versioned publication kinds, authority, and identifier-only plans."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from firelens.contract_base import FrozenStrictModel, StrictModel


class PublicationKind(StrEnum):
    STRUCTURED_REVIEWED = "structured_reviewed"
    OFFICIAL_LIVE_TYPED = "official_live_typed"
    OFFICIAL_QUOTE_ONLY = "official_quote_only"
    SOURCE_LINKED_EXPLANATION = "source_linked_explanation"
    GENERAL_BACKGROUND = "general_background"
    UNSUPPORTED = "unsupported"


RENDERER_ID = "firelens.structured_renderer.v1"
LIVE_RENDERER_ID = "firelens.live_typed_renderer.v1"
QUOTE_RENDERER_ID = "firelens.quote_only_renderer.v1"


class PublicationAuthority(FrozenStrictModel):
    kind: PublicationKind
    typed_claim_id: str | None = Field(default=None, min_length=3, max_length=80)
    typed_live_fact_id: str | None = Field(default=None, min_length=1, max_length=200)
    review_status: str = Field(default="none", min_length=1, max_length=40)
    source_revision_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    source_span_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    renderer_id: str = Field(default="none", min_length=1, max_length=80)
    support_provenance: str = Field(default="none", min_length=1, max_length=80)
    risk_tier: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def require_authority_for_supported_kinds(self) -> PublicationAuthority:
        if self.kind == PublicationKind.STRUCTURED_REVIEWED:
            missing: list[str] = []
            if not self.typed_claim_id:
                missing.append("typed_claim_id")
            if self.review_status in {"none", "pending_review"}:
                missing.append("review_status")
            if not self.source_revision_sha256:
                missing.append("source_revision_sha256")
            if self.renderer_id == "none":
                missing.append("renderer_id")
            if self.support_provenance == "none":
                missing.append("support_provenance")
            if missing:
                raise ValueError(
                    "structured reviewed publication requires " + ", ".join(missing)
                )
        if self.kind == PublicationKind.OFFICIAL_LIVE_TYPED and not self.typed_live_fact_id:
            raise ValueError("official live typed publication requires typed_live_fact_id")
        return self


class StructuredReviewedClaimBlock(FrozenStrictModel):
    """Constructor for a compiled block. Does not accept model-supplied text."""

    public_claim_id: str = Field(pattern=r"^[CL][1-9][0-9]*$")
    typed_claim_id: str = Field(min_length=3, max_length=80)
    review_status: str = Field(min_length=1, max_length=40)
    source_revision_sha256: str = Field(min_length=64, max_length=64)
    renderer_id: str = Field(min_length=1, max_length=80)
    support_provenance: str = Field(min_length=1, max_length=80)


class HighRiskAnswerPlan(StrictModel):
    selected_typed_claim_ids: list[str] = Field(default_factory=list, max_length=12)
    selected_live_fact_ids: list[str] = Field(default_factory=list, max_length=12)
    selected_quote_only_ids: list[str] = Field(default_factory=list, max_length=12)
    unknown_aspects: list[str] = Field(default_factory=list, max_length=12)
    section_order: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    official_links: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> HighRiskAnswerPlan:
        for name in (
            "selected_typed_claim_ids",
            "selected_live_fact_ids",
            "selected_quote_only_ids",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
        return self

    def bind(
        self,
        *,
        typed_ids: set[str],
        live_ids: set[str],
        quote_ids: set[str],
    ) -> HighRiskAnswerPlan:
        unknown = [item for item in self.selected_typed_claim_ids if item not in typed_ids]
        unknown.extend(item for item in self.selected_live_fact_ids if item not in live_ids)
        unknown.extend(item for item in self.selected_quote_only_ids if item not in quote_ids)
        if unknown:
            raise ValueError("plan contains IDs outside the current evidence packet")
        return self
