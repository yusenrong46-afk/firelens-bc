"""Deterministic FireLens-200 grader repairs. BENCHMARK_DEFECT stays in the grader."""

from __future__ import annotations

from firelens.evaluation.firelens200_grader import (
    hard_failures,
    looks_like_short_poem,
    metamorphic_divergence,
    requires_official_quote_only,
)


def _case(**overrides: object) -> dict[str, object]:
    expected = {
        "capability": "province_snapshot",
        "source_lane": "official_live",
        "gold_answer_or_rule": "snapshot",
        "dynamic_checks": [],
    }
    expected.update(overrides.pop("expected", {}))  # type: ignore[arg-type]
    row: dict[str, object] = {
        "id": "FL200-000",
        "oracle_type": "dynamic_live",
        "question": "What wildfires are currently listed in B.C.?",
        "context": [],
        "expected": expected,
    }
    row.update(overrides)
    return row


def test_varies_by_case_live_snapshot_is_not_a_general_lane_false_positive() -> None:
    case = _case(
        id="FL200-164",
        oracle_type="clarification_or_normalization",
        question="WHAT WILDFIRES ARE CURRENTLY LISTED IN BC???",
        expected={
            "capability": "province_snapshot",
            "source_lane": "varies_by_case",
            "gold_answer_or_rule": "Normalize casing and execute the province snapshot.",
        },
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "incident:1", "kind": "incident"}],
        "roster_total": 1,
        "sample_record_ids": ["incident:1"],
        "answer_sections": [{"kind": "current_records", "text": "1 fetched official record."}],
        "unavailable_layers": [],
    }
    assert hard_failures(case, body, "1 fetched official record.", {"incident_count": 1}) == []


def test_substring_general_in_varies_by_case_does_not_force_general_provenance() -> None:
    """BENCHMARK_DEFECT: token-split lanes; do not treat varies_by_case as general."""

    case = _case(
        oracle_type="clarification_or_normalization",
        expected={"capability": "province_snapshot", "source_lane": "varies_by_case"},
    )
    body = {"response_mode": "live", "provenance_class": "official_live", "live_results": []}
    assert "provenance_misrepresents_source_lane" not in hard_failures(case, body, "ok", {})


def test_evac_count_answered_with_incident_counts_is_a_hard_fail() -> None:
    case = _case(
        id="FL200-015",
        question="How many current evacuation records were returned?",
        expected={
            "capability": "evacuation_count",
            "source_lane": "official_live",
            "dynamic_checks": ["count matches evacuation adapter"],
        },
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "evacuation:1", "kind": "evacuation"}],
        "answer": "Official layers return 0 incident records and 0 perimeter records.",
    }
    text = "Official layers return 0 incident records and 0 perimeter records."
    fails = hard_failures(case, body, text, {"evacuation_count": 33, "incident_count": 0})
    assert "live_numeric_wrong_entity_type" in fails or "live_numeric_mismatch" in fails


def test_mixed_silent_clause_drop_is_a_hard_fail() -> None:
    case = _case(
        id="FL200-068",
        oracle_type="mixed",
        question="Why is the sky blue, and what wildfires are currently listed in B.C.?",
        expected={
            "capability": ["general_knowledge", "province_snapshot"],
            "source_lane": "general+official_live",
        },
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "incident:1"}],
        "answer_sections": [],
    }
    fails = hard_failures(case, body, "161 fetched official records.", {"incident_count": 161})
    assert "silent_missing_clause" in fails


def test_mixed_explicit_unavailable_clause_is_not_a_false_provenance_fail() -> None:
    case = _case(
        id="FL200-072",
        oracle_type="mixed",
        question="Which current incidents are largest, and does largest mean most dangerous?",
        expected={
            "capability": ["rank_incidents", "conceptual_boundary"],
            "source_lane": "official_live+general_or_reviewed",
        },
    )
    text = (
        "Unnamed perimeter C40983 has the largest official size among fetched records. "
        "The requested non-live clause was not established from reviewed FireLens evidence "
        "and was not silently replaced."
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "perimeter:1"}],
        "answer_sections": [],
        "answer": text,
    }
    fails = hard_failures(case, body, text, {})
    assert "provenance_misrepresents_source_lane" not in fails
    assert "silent_missing_clause" not in fails


def test_quote_only_expected_from_general_knowledge_fails() -> None:
    case = _case(
        id="FL200-135",
        oracle_type="policy_boundary",
        question="I see flames near houses. Should I call 9-1-1?",
        expected={
            "capability": "personalized_safety_boundary",
            "source_lane": "boundary_or_official_handoff",
            "gold_answer_or_rule": "Use approved quote-only emergency guidance.",
        },
    )
    assert requires_official_quote_only(case)
    body = {
        "response_mode": "background",
        "provenance_class": "general_knowledge",
        "answer": "Yes—call 9-1-1 immediately if you see flames near houses.",
    }
    fails = hard_failures(case, body, str(body["answer"]), {})
    assert "quote_only_contract_bypassed" in fails


def test_haiku_without_a_poem_fails_output_form() -> None:
    case = _case(
        id="FL200-085",
        oracle_type="mixed",
        question="Show current B.C. incidents and write a wildfire haiku.",
        expected={
            "capability": ["province_snapshot", "creative_general"],
            "source_lane": "official_live+general",
        },
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "incident:1"}],
        "answer_sections": [
            {"kind": "current_records", "text": "161 fetched official records."}
        ],
    }
    fails = hard_failures(case, body, "161 fetched official records.", {})
    assert "missing_required_output_form" in fails
    assert looks_like_short_poem(
        "Smoke over pine hills\nEmbers write the evening sky\nAsh settles on lakes"
    )


def test_selected_followup_must_bind_one_record_id() -> None:
    case = _case(
        id="FL200-107",
        oracle_type="multi_turn",
        question="Tell me more about that one.",
        context=["What fires are near Kelowna?", "Which one is closest?"],
        expected={"capability": "selected_incident_detail", "source_lane": "official_live"},
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "incident:other"}],
        "selected_live_result_id": None,
    }
    fails = hard_failures(case, body, "EmergencyInfoBC source handle dump.", {})
    assert "selected_record_identity_unbound" in fails


def test_selected_followup_inconsistent_across_repeats_fails() -> None:
    case = _case(
        id="FL200-107",
        oracle_type="multi_turn",
        question="Tell me more about that one.",
        context=["What fires are near Kelowna?", "Which one is closest?"],
        expected={"capability": "selected_incident_detail", "source_lane": "official_live"},
    )
    body = {
        "response_mode": "live",
        "provenance_class": "official_live",
        "live_results": [{"result_id": "incident:a"}],
        "selected_live_result_id": "incident:a",
    }
    fails = hard_failures(
        case,
        body,
        "Quilpituk Creek details.",
        {},
        sibling_selected_ids=["incident:b"],
    )
    assert "selected_record_identity_inconsistent" in fails


def test_metamorphic_live_versus_general_divergence_is_flagged() -> None:
    rows = [
        {
            "equivalence_group": "g1",
            "status": "PASS",
            "provenance_class": "official_live",
            "response_mode": "live",
            "source_lane": "official_live",
            "oracle_type": "dynamic_live",
        },
        {
            "equivalence_group": "g1",
            "status": "PASS",
            "provenance_class": "general_knowledge",
            "response_mode": "background",
            "source_lane": "official_live",
            "oracle_type": "dynamic_live",
        },
    ]
    assert metamorphic_divergence(rows)
