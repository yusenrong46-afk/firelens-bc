from __future__ import annotations

import pytest

from firelens.answering.claim_render import render_typed_claim
from firelens.answering.risk_policy import POLICY_VERSION, RiskTier
from firelens.answering.semantic_invariants import SEMANTIC_MODEL_CHECKER_ENABLED
from firelens.answering.typed_compare import typed_preservation_errors
from firelens.answering.typed_records import TypedClaimRecord, load_inventory


def test_reviewed_inventory_is_production_supported_subset() -> None:
    inventory = load_inventory()
    assert inventory.policy_version == POLICY_VERSION
    assert inventory.records
    supported = [record for record in inventory.records if record.production_supported()]
    pending = [
        record for record in inventory.records if record.human_review_state == "pending_review"
    ]
    supported_ids = {record.claim_id for record in supported}
    pending_ids = {record.claim_id for record in pending}
    assert supported
    assert "TC-EVAC-ALERT-001" in supported_ids
    assert "TC-SPRINKLER-001" in supported_ids
    assert "TC-EVAC-ALERT-001" not in pending_ids
    assert not pending_ids
    assert all(record.source_span_ids for record in inventory.records)
    assert {record.risk_tier for record in inventory.records} <= {RiskTier.A, RiskTier.B}


def test_unreviewed_typed_claim_cannot_be_rendered() -> None:
    record = TypedClaimRecord(
        claim_id="TC-PENDING-001",
        risk_tier=RiskTier.A,
        authority="PreparedBC",
        jurisdiction="british_columbia",
        subject="unreviewed extraction",
        source_span_ids=["pending-span"],
        source_revision="unreviewed",
        human_review_state="pending_review",
        canonical_text="Leave immediately when an evacuation order is issued.",
        source_span_text="Leave immediately when an evacuation order is issued.",
        freshness="stable_guidance",
    )
    assert record.production_supported() is False
    with pytest.raises(ValueError, match="not a production-supported"):
        render_typed_claim(record)


def test_reviewed_alert_and_sprinkler_surfaces_are_pinned() -> None:
    from firelens.publication.compiler import compile_structured_claim

    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ALERT-001",
        public_claim_id="C1",
    )
    approved_surface = (
        "If you are under an evacuation alert, be ready to leave on short notice."
    )
    assert compiled.claim.text == approved_surface
    assert (
        typed_preservation_errors(
            compiled.claim.text,
            [compiled.evidence[0].primary_text],
        )
        == []
    )
    sprinkler = compile_structured_claim(
        typed_claim_id="TC-SPRINKLER-001",
        public_claim_id="C1",
    )
    assert sprinkler.claim.text == (
        "If you have installed a structure protection sprinkler system on your property "
        "DO NOT activate your system as you are evacuating. Structure Protection "
        "Specialists will activate sprinkler systems when the time is right."
    )
    assert (
        typed_preservation_errors(
            sprinkler.claim.text,
            [sprinkler.evidence[0].primary_text],
        )
        == []
    )


def test_semantic_model_checker_remains_optional_rejection_only() -> None:
    assert SEMANTIC_MODEL_CHECKER_ENABLED is False
