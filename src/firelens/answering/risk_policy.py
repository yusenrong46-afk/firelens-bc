"""Versioned risk-tier policy for FireLens public claims.

Tier A and Tier B critical fields are owned by typed records and
deterministic checks. A model may only propose low-risk connective wording.
"""

from __future__ import annotations

from enum import StrEnum

POLICY_VERSION = "firelens.claim_risk_policy.v1"


class RiskTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"


TIER_A_FIELDS = (
    "action",
    "action_polarity",
    "urgency",
    "modality",
    "status_stage",
    "conditions",
    "exceptions",
    "applies_to",
)

TIER_B_FIELDS = (
    "quantities",
    "canonical_units",
    "ranges",
    "comparator",
    "inclusive_exclusive",
    "authority",
    "jurisdiction",
    "official_source_updated_at",
    "firelens_retrieved_at",
    "freshness",
    "locations",
    "valid_from",
    "valid_to",
)

POLICY = {
    RiskTier.A: (
        "No unconstrained generated factual prose. Render from reviewed typed "
        "claims. Connective text may not change action fields."
    ),
    RiskTier.B: (
        "Render critical values from typed records. The LLM may not create or "
        "transform them except through explicitly validated conversions."
    ),
    RiskTier.C: (
        "Bounded generation allowed. Critical-field preservation and evidence "
        "support still required."
    ),
}


def policy_for(tier: RiskTier) -> str:
    return POLICY[tier]
