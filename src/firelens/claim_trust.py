"""Additive claim-trust states. Existing evidence_status remains compatible."""

from __future__ import annotations

from typing import Literal

from firelens.contract_base import FrozenStrictModel

GROUNDED_PUBLIC_WORDING = (
    "Grounded in reviewed official sources with exact supporting quotations "
    "and automated critical-field checks."
)

SourceProvenance = Literal["approved_static_corpus", "official_live_record", "none"]
HumanReviewState = Literal["approved_static", "human_verified_repair", "pending_review", "none"]
ExtractionState = Literal["native_text", "human_verified_repair", "unknown"]
CriticalFieldState = Literal["preserved", "not_applicable", "failed"]
SemanticSupportState = Literal["exact_quote", "insufficient", "background", "none"]
ConflictState = Literal["none", "conflict_shown", "superseded"]
FreshnessState = Literal["stable_guidance", "fresh", "stale", "mixed", "unknown"]


class ClaimTrust(FrozenStrictModel):
    source_provenance: SourceProvenance
    source_authority: str
    jurisdiction: str = "british_columbia"
    human_review_state: HumanReviewState
    extraction_repair_state: ExtractionState
    critical_field_preservation: CriticalFieldState
    semantic_support_state: SemanticSupportState
    conflict_or_supersession: ConflictState = "none"
    freshness: FreshnessState = "stable_guidance"


def corpus_claim_trust(
    *,
    authority: str,
    review_provenance: str,
    conflicts: bool = False,
    critical_fields_preserved: bool = True,
) -> ClaimTrust:
    return ClaimTrust(
        source_provenance="approved_static_corpus",
        source_authority=authority,
        human_review_state=(
            "human_verified_repair"
            if review_provenance == "human_verified_repair"
            else "approved_static"
        ),
        extraction_repair_state=(
            "human_verified_repair"
            if review_provenance == "human_verified_repair"
            else "native_text"
        ),
        critical_field_preservation="preserved" if critical_fields_preserved else "failed",
        semantic_support_state="exact_quote",
        conflict_or_supersession="conflict_shown" if conflicts else "none",
        freshness="stable_guidance",
    )
