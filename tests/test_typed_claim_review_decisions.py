from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml

from firelens.answering.candidate_preparation import (
    build_prepared_candidates,
    normalized_sha256,
)
from firelens.answering.typed_compare import typed_preservation_errors

ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "data/typed_claims/prepared_candidates_v2.yaml"


def test_recorded_human_approvals_bind_every_prepared_candidate() -> None:
    artifact = build_prepared_candidates(ROOT)
    candidates = {row.candidate_id: row for row in artifact.prepared_candidates}
    prepared_sha256 = sha256(PREPARED.read_bytes()).hexdigest()

    for batch in artifact.batches:
        journal = (
            ROOT / f"docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_{batch.batch}_DECISIONS.yaml"
        )
        payload = yaml.safe_load(journal.read_text(encoding="utf-8"))
        decisions = payload["decisions"]

        assert payload["batch"] == batch.batch
        assert payload["reviewer"] == "Thomas"
        assert payload["prepared_candidate_artifact_sha256"] == prepared_sha256
        assert [row["candidate_id"] for row in decisions] == batch.candidate_ids
        assert len(decisions) == len(set(row["candidate_id"] for row in decisions))
        for decision in decisions:
            candidate = candidates[decision["candidate_id"]]
            assert decision["decision"] == "approve"
            assert decision["production_supported"] is False
            assert decision["reviewer"] == "Thomas"
            assert decision["decision_time"]
            assert decision["source_revision"] == candidate.source_revision
            assert decision["source_document_sha256"] == candidate.source_document_sha256
            assert decision["source_span_sha256"] == candidate.source_span_sha256
            assert decision["approved_surface_sha256"] == candidate.proposed_surface_sha256
            assert decision["approved_surface"] == candidate.proposed_surface


def test_sprinkler_final_approval_preserves_the_complete_bound_source() -> None:
    inventory = yaml.safe_load(
        (ROOT / "data/typed_claims/high_risk_v1.yaml").read_text(encoding="utf-8")
    )
    sprinkler = next(
        row for row in inventory["records"] if row["claim_id"] == "TC-SPRINKLER-001"
    )
    journal = yaml.safe_load(
        (ROOT / "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_1_DECISIONS.yaml").read_text(
            encoding="utf-8"
        )
    )
    final = [row for row in journal["decisions"] if row["candidate_id"] == "TC-SPRINKLER-001"][
        -1
    ]

    assert final["decision"] == "approve_after_edits"
    assert final["reviewer"] == "Thomas"
    assert final["production_supported"] is False
    assert final["approved_surface"] == sprinkler["source_span_text"].strip()
    assert final["approved_surface_sha256"] == normalized_sha256(final["approved_surface"])
    assert (
        typed_preservation_errors(final["approved_surface"], [sprinkler["source_span_text"]])
        == []
    )


def test_all_source_repairs_have_explicit_v1_6_deferrals() -> None:
    template = yaml.safe_load(
        (ROOT / "data/typed_claims/source_repair_scope_template_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    journal = yaml.safe_load(
        (ROOT / "docs/reports/V1_6_SOURCE_REPAIR_SCOPE_DECISIONS.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert journal["reviewer"] == "Thomas"
    assert (
        journal["source_template_sha256"]
        == sha256(
            (ROOT / "data/typed_claims/source_repair_scope_template_v1.yaml").read_bytes()
        ).hexdigest()
    )
    assert [row["parent_candidate_id"] for row in journal["decisions"]] == [
        row["parent_candidate_id"] for row in template["decisions"]
    ]
    assert len(journal["decisions"]) == 9
    assert all(
        row["owner_scope_decision"] == "defer_out_of_scope" for row in journal["decisions"]
    )


def test_h8_acceptance_is_bound_to_the_measured_report() -> None:
    performance_path = ROOT / "docs/reports/V1_6_PRE_RELEASE_PERFORMANCE.json"
    performance = json.loads(performance_path.read_text(encoding="utf-8"))
    decision = yaml.safe_load(
        (ROOT / "docs/reports/V1_6_H8_TRADEOFF_DECISION.yaml").read_text(encoding="utf-8")
    )

    assert decision["reviewer"] == "Thomas"
    assert decision["decision"] == "accept_measured_tradeoff"
    assert (
        decision["performance_report_sha256"]
        == sha256(performance_path.read_bytes()).hexdigest()
    )
    assert decision["evaluated_identity"] == performance["identity"]
    assert [row["route_id"] for row in decision["accepted_routes"]] == performance["h8_review"][
        "regressed_routes_over_10pct"
    ]
    for accepted in decision["accepted_routes"]:
        measured = performance["current_routes"][accepted["route_id"]]
        assert accepted["p95_ms"] == measured["p95_ms"]
        assert accepted["failures"] == measured["failures"]


def test_rc1_h8_acceptance_is_bound_to_the_exact_candidate_report() -> None:
    performance_path = ROOT / "docs/reports/V1_6_RC1_PERFORMANCE.json"
    performance = json.loads(performance_path.read_text(encoding="utf-8"))
    decision = yaml.safe_load(
        (ROOT / "docs/reports/V1_6_RC1_H8_TRADEOFF_DECISION.yaml").read_text(encoding="utf-8")
    )

    assert decision["reviewer"] == "Thomas"
    assert decision["decision"] == "accept_measured_tradeoff"
    assert (
        decision["performance_report_sha256"]
        == sha256(performance_path.read_bytes()).hexdigest()
    )
    assert decision["evaluated_identity"] == performance["identity"]
    assert [row["route_id"] for row in decision["accepted_routes"]] == performance["h8_review"][
        "regressed_routes_over_10pct"
    ]
    assert (
        decision["representative_generation_call_reduction"]
        == performance["compare"]["generative_call_reduction"]
    )
    assert decision["pure_static_generation_calls"] == performance["pure_static_generate_calls"]
    for accepted in decision["accepted_routes"]:
        measured = performance["current_routes"][accepted["route_id"]]
        assert accepted["p95_ms"] == measured["p95_ms"]
        assert accepted["failures"] == measured["failures"] == 0
