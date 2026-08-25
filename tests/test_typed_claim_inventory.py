from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

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


def test_structured_evidence_and_proof_card_use_exact_bound_source_url() -> None:
    from firelens.publication.compiler import compile_structured_claim
    from firelens.publication.records import get_versioned

    record = get_versioned("TC-EVAC-ORDER-001")
    span_ids = set(record.source_span_ids)
    corpus_path = (
        Path(__file__).resolve().parents[1]
        / "data/processed/firelens_static_corpus.chunks.jsonl"
    )
    bound_urls = {
        row["canonical_url"]
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))["chunk_id"] in span_ids
    }
    assert len(bound_urls) == 1

    compiled = compile_structured_claim(
        typed_claim_id=record.claim_id,
        public_claim_id="C2",
    )
    expected = bound_urls.pop().rstrip("/")
    assert str(compiled.evidence[0].canonical_url).rstrip("/") == expected
    assert str(compiled.card.official_url).rstrip("/") == expected


def test_structured_support_rejects_inconsistent_bound_source_urls(
    tmp_path: Path,
) -> None:
    from firelens.publication.records import get_versioned

    source_root = Path(__file__).resolve().parents[1]
    inventory_path = tmp_path / "data/typed_claims/high_risk_v1.yaml"
    corpus_path = tmp_path / "data/processed/firelens_static_corpus.chunks.jsonl"
    inventory_path.parent.mkdir(parents=True)
    corpus_path.parent.mkdir(parents=True)
    shutil.copyfile(source_root / "data/typed_claims/high_risk_v1.yaml", inventory_path)
    shutil.copyfile(
        source_root / "data/processed/firelens_static_corpus.chunks.jsonl",
        corpus_path,
    )

    rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
    order_id = "preparedbc_wildfire_guide:page:11:chunk:2"
    order = next(row for row in rows if row["chunk_id"] == order_id)
    second = next(
        row
        for row in rows
        if row["document_sha256"] == order["document_sha256"] and row["chunk_id"] != order_id
    )
    second["canonical_url"] = "https://example.test/conflicting-source"
    corpus_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    record = next(row for row in inventory["records"] if row["claim_id"] == "TC-EVAC-ORDER-001")
    record["source_span_ids"].append(second["chunk_id"])
    inventory_path.write_text(
        yaml.safe_dump(inventory, sort_keys=False),
        encoding="utf-8",
    )

    assert (
        get_versioned("TC-EVAC-ORDER-001", root=str(tmp_path)).available_for_structured_support
        is False
    )


def test_semantic_model_checker_remains_optional_rejection_only() -> None:
    assert SEMANTIC_MODEL_CHECKER_ENABLED is False
