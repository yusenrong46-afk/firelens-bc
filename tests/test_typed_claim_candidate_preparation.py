from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml

from firelens.answering.candidate_preparation import (
    PreparedCandidateArtifact,
    build_prepared_candidates,
    disposition_counts,
    normalized_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "data/typed_claims/prepared_candidates_v2.yaml"
MANIFEST = ROOT / "docs/reports/V1_6_TYPED_CLAIM_PREPARATION_MANIFEST.json"
REPAIR_SCOPE = ROOT / "data/typed_claims/source_repair_scope_template_v1.yaml"


def test_all_raw_candidates_receive_one_governed_disposition() -> None:
    artifact = build_prepared_candidates(ROOT)
    assert len(artifact.dispositions) == 36
    assert len({row.parent_candidate_id for row in artifact.dispositions}) == 36
    assert disposition_counts(artifact) == {
        "needs_source_repair": 9,
        "duplicate_existing": 3,
        "not_claim_bearing": 8,
        "review_ready": 16,
    }


def test_review_ready_candidates_are_bound_pending_and_batched() -> None:
    artifact = build_prepared_candidates(ROOT)
    assert len(artifact.prepared_candidates) == 20
    assert [len(batch.candidate_ids) for batch in artifact.batches] == [10, 10]
    batched = [
        candidate_id for batch in artifact.batches for candidate_id in batch.candidate_ids
    ]
    assert batched == [row.candidate_id for row in artifact.prepared_candidates]
    for row in artifact.prepared_candidates:
        assert row.review_status == "pending_review"
        assert row.reviewer is None
        assert row.reviewed_at is None
        assert row.source_span_sha256 == normalized_sha256(row.exact_source_quote)
        assert row.proposed_surface_sha256 == normalized_sha256(row.proposed_surface)
        assert row.source_document_sha256
        assert row.source_span_ids


def test_checked_in_prepared_artifact_and_manifest_are_reproducible() -> None:
    expected = build_prepared_candidates(ROOT)
    checked_in = PreparedCandidateArtifact.model_validate(
        yaml.safe_load(PREPARED.read_text(encoding="utf-8"))
    )
    assert checked_in == expected
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["raw_candidate_count"] == 36
    assert manifest["prepared_candidate_count"] == 20
    assert manifest["batch_sizes"] == [10, 10]
    assert manifest["contains_reviewer_identity"] is False
    assert manifest["review_state"] == "pending_review_only"


def test_source_repair_scope_template_is_complete_and_blank() -> None:
    artifact = build_prepared_candidates(ROOT)
    expected_ids = [
        row.parent_candidate_id
        for row in artifact.dispositions
        if row.disposition == "needs_source_repair"
    ]
    scope = yaml.safe_load(REPAIR_SCOPE.read_text(encoding="utf-8"))
    assert [row["parent_candidate_id"] for row in scope["decisions"]] == expected_ids
    assert len(scope["decisions"]) == 9
    assert all(row["owner_scope_decision"] is None for row in scope["decisions"])
    assert all(row["reviewer"] is None for row in scope["decisions"])
    assert all(row["decision_time"] is None for row in scope["decisions"])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["source_repair_scope_count"] == 9
    assert manifest["source_repair_scope_decisions_blank"] is True
    assert (
        manifest["source_repair_scope_template_sha256"]
        == sha256(REPAIR_SCOPE.read_bytes()).hexdigest()
    )
