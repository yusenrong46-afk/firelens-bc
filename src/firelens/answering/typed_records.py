"""Reviewed high-risk typed claims. Unreviewed extractions cannot be published as supported."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field

from firelens.answering.risk_policy import POLICY_VERSION, RiskTier
from firelens.contract_base import FrozenStrictModel

RECORDS_RELATIVE = "data/typed_claims/high_risk_v1.yaml"
ALLOWED_REVIEW_STATES = frozenset({"approved_static", "human_verified_repair"})
_REPO_ROOT = Path(__file__).resolve().parents[3]


class TypedClaimRecord(FrozenStrictModel):
    claim_id: str = Field(min_length=3, max_length=80)
    risk_tier: RiskTier
    authority: str = Field(min_length=2, max_length=160)
    jurisdiction: str = Field(min_length=2, max_length=80)
    subject: str = Field(min_length=2, max_length=200)
    action: str | None = Field(default=None, max_length=80)
    action_polarity: str | None = Field(default=None, max_length=40)
    object: str | None = Field(default=None, max_length=200)
    modality: str | None = Field(default=None, max_length=40)
    urgency: str | None = Field(default=None, max_length=40)
    status_stage: str | None = Field(default=None, max_length=80)
    quantities: list[str] = Field(default_factory=list, max_length=8)
    canonical_units: list[str] = Field(default_factory=list, max_length=8)
    ranges: list[str] = Field(default_factory=list, max_length=4)
    comparator: str | None = Field(default=None, max_length=40)
    inclusive_exclusive: str | None = Field(default=None, max_length=40)
    locations: list[str] = Field(default_factory=list, max_length=8)
    valid_from: str | None = Field(default=None, max_length=40)
    valid_to: str | None = Field(default=None, max_length=40)
    official_source_updated_at: str | None = Field(default=None, max_length=80)
    firelens_retrieved_at: str | None = Field(default=None, max_length=80)
    freshness: str = Field(default="stable_guidance", max_length=40)
    conditions: list[str] = Field(default_factory=list, max_length=8)
    exceptions: list[str] = Field(default_factory=list, max_length=8)
    applies_to: list[str] = Field(default_factory=list, max_length=8)
    source_span_ids: list[str] = Field(min_length=1, max_length=8)
    source_revision: str = Field(min_length=1, max_length=80)
    binding_kind: Literal["corpus_chunk", "internal_static"] = "corpus_chunk"
    source_document_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    source_span_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    approved_surface_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    human_review_state: str = Field(min_length=1, max_length=40)
    canonical_text: str = Field(min_length=8, max_length=600)
    source_span_text: str = Field(min_length=8, max_length=800)

    def production_supported(self) -> bool:
        return (
            self.risk_tier in {RiskTier.A, RiskTier.B}
            and self.human_review_state in ALLOWED_REVIEW_STATES
        )


class TypedClaimInventory(FrozenStrictModel):
    schema_version: str
    policy_version: str
    note: str | None = None
    records: list[TypedClaimRecord] = Field(min_length=1, max_length=64)


def inventory_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / RECORDS_RELATIVE


@lru_cache(maxsize=4)
def load_inventory(root: str | None = None) -> TypedClaimInventory:
    path = inventory_path(Path(root) if root else None)
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    inventory = TypedClaimInventory.model_validate(payload)
    if inventory.policy_version != POLICY_VERSION:
        raise ValueError("typed claim inventory policy_version does not match runtime policy")
    return inventory


def inventory_sha256(root: Path | None = None) -> str:
    return sha256(inventory_path(root).read_bytes()).hexdigest()


def records_for_span(span_id: str, *, root: Path | None = None) -> list[TypedClaimRecord]:
    inventory = load_inventory(str(root) if root else None)
    return [
        record
        for record in inventory.records
        if span_id in record.source_span_ids and record.production_supported()
    ]


def match_quote(quote: str, *, root: Path | None = None) -> list[TypedClaimRecord]:
    inventory = load_inventory(str(root) if root else None)
    lowered = " ".join(quote.split()).casefold()
    matched: list[TypedClaimRecord] = []
    for record in inventory.records:
        if not record.production_supported():
            continue
        span = " ".join(record.source_span_text.split()).casefold()
        if span and (span in lowered or lowered in span):
            matched.append(record)
    return matched
