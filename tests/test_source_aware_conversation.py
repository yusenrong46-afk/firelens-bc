from __future__ import annotations

import json
from copy import deepcopy

import pytest

from firelens.evaluation.source_aware_conversation import (
    build_report,
    load_dataset,
    score_observation,
    validate_manifest_binding,
    validate_registry_binding,
)


def test_dataset_and_guided_registry_are_bound() -> None:
    dataset = load_dataset()
    binding = validate_registry_binding(dataset)
    assert len(dataset["canonical_cases"]) == 24
    assert all(len(case["paraphrases"]) >= 3 for case in dataset["canonical_cases"])
    assert binding["guided_question_count"] == 24


def test_closed_predicates_reject_mutated_runtime_observations() -> None:
    case = {
        "expected_mode": "live",
        "source_lane": "official_live",
        "require_nonempty_answer": True,
    }
    observed = {
        "request_valid": True,
        "response_mode": "live",
        "observed_source_lane": "official_live",
        "has_answer": True,
        "tier_a_b_generation_calls": 0,
        "live_result_count": 1,
        "tool_traces": ["list_official_fires"],
        "publication_kinds": [],
    }
    assert all(score_observation(case, observed).values())
    for field, value in (
        ("request_valid", False),
        ("response_mode", "background"),
        ("observed_source_lane", "reviewed_guidance"),
        ("has_answer", False),
        ("live_result_count", 0),
        ("tier_a_b_generation_calls", 1),
    ):
        mutated = deepcopy(observed)
        mutated[field] = value
        assert not all(score_observation(case, mutated).values())


def test_paraphrases_may_downgrade_between_reviewed_and_quote_only_lanes() -> None:
    case = {
        "expected_mode": "grounded",
        "expected_source_lane": "reviewed_guidance",
        "strict_source_lane": False,
    }
    observed = {
        "request_valid": True,
        "response_mode": "partial",
        "observed_source_lane": "official_quote",
        "publication_kinds": ["official_quote_only"],
        "evidence_count": 1,
        "claim_count": 1,
        "has_answer": True,
        "tier_a_b_generation_calls": 0,
    }
    assert all(score_observation(case, observed).values())
    assert not all(score_observation({**case, "strict_source_lane": True}, observed).values())


@pytest.mark.parametrize(
    ("case", "observation", "predicate"),
    [
        (
            {"expected_mode": "grounded", "expected_source_lane": "reviewed_guidance"},
            {
                "response_mode": "background",
                "observed_source_lane": "reviewed_guidance",
                "evidence_count": 1,
                "claim_count": 1,
                "has_answer": True,
            },
            "expected_mode",
        ),
        (
            {"expected_mode": "grounded", "expected_source_lane": "reviewed_guidance"},
            {
                "response_mode": "grounded",
                "observed_source_lane": "official_live",
                "evidence_count": 1,
                "claim_count": 1,
                "has_answer": True,
            },
            "source_lane",
        ),
        (
            {"expected_mode": "grounded", "expected_source_lane": "reviewed_guidance"},
            {
                "response_mode": "grounded",
                "observed_source_lane": "reviewed_guidance",
                "evidence_count": 0,
                "claim_count": 1,
                "has_answer": True,
            },
            "reviewed_compliance",
        ),
        (
            {"expected_mode": "grounded", "expected_source_lane": "official_quote"},
            {
                "response_mode": "grounded",
                "observed_source_lane": "official_quote",
                "publication_kinds": ["structured_reviewed"],
                "evidence_count": 1,
                "claim_count": 1,
                "has_answer": True,
            },
            "quote_only",
        ),
        (
            {"expected_mode": "mixed", "expected_source_lane": "mixed"},
            {
                "response_mode": "mixed",
                "observed_source_lane": "reviewed_guidance",
                "has_answer": True,
            },
            "mixed_lane",
        ),
        (
            {"expected_mode": "background", "require_no_source_implication": True},
            {
                "response_mode": "background",
                "observed_source_lane": "official_quote",
                "live_result_count": 0,
                "has_answer": True,
            },
            "no_source_implication",
        ),
        (
            {"expected_mode": "background", "require_no_map": True},
            {
                "response_mode": "background",
                "observed_source_lane": "general",
                "tool_traces": ["map_results"],
                "has_answer": True,
            },
            "no_map_tool",
        ),
        (
            {"expected_mode": "abstention", "require_safety_handoff": True},
            {"response_mode": "background", "route": "related", "has_answer": True},
            "safety_handoff",
        ),
        (
            {"expected_mode": "abstention", "require_no_status_claim": True},
            {
                "response_mode": "abstention",
                "status": "answer",
                "claim_count": 0,
                "has_answer": True,
            },
            "no_status_claim",
        ),
        (
            {"expected_mode": "grounded", "expected_source_lane": "reviewed_guidance"},
            {
                "response_mode": "background",
                "observed_source_lane": "reviewed_guidance",
                "has_answer": True,
            },
            "no_unnecessary_handoff",
        ),
        (
            {"expected_mode": "grounded", "expected_source_lane": "reviewed_guidance"},
            {
                "response_mode": "grounded",
                "observed_source_lane": "reviewed_guidance",
                "publication_kinds": ["official_live_typed"],
                "has_answer": True,
            },
            "no_authority_escalation",
        ),
    ],
)
def test_each_closed_predicate_has_a_failing_mutation(case, observation, predicate) -> None:
    checks = score_observation(case, observation)
    assert checks[predicate] is False


def test_manifest_tamper_fails_closed(tmp_path) -> None:
    dataset = tmp_path / "dataset.yaml"
    manifest = tmp_path / "manifest.json"
    dataset.write_text("tampered\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "firelens.source_aware_conversation.manifest.v1",
                "dataset_sha256": "0" * 64,
                "canonical_case_count": 24,
                "paraphrase_count": 72,
                "total_case_count": 106,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dataset hash"):
        validate_manifest_binding(dataset, manifest)


def test_registry_mismatch_fails_closed() -> None:
    dataset = load_dataset()
    mutated = deepcopy(dataset)
    mutated["canonical_cases"][0]["source_lane"] = "reviewed_guidance"
    with pytest.raises(ValueError, match="source lane"):
        validate_registry_binding(mutated)


def test_offline_report_is_execution_backed_and_exposes_failures() -> None:
    report = build_report()
    assert report["execution"] == {
        "mode": "offline_deterministic_executed",
        "provider_boundary": "fake_provider_only",
        "external_network_calls": 0,
        "external_model_calls": 0,
        "local_fake_provider_calls": report["execution"]["local_fake_provider_calls"],
        "local_fake_provider_cost_usd": 0.0,
    }
    assert report["case_counts"]["total"] == 106
    assert report["metrics"]["tier_a_b_generation_calls"] == sum(
        item["tier_a_b_generation_calls"] for item in report["results"]
    )
    assert all("route" in item and "provider_calls" in item for item in report["results"])
    assert report["execution"]["local_fake_provider_calls"] > 0
    assert report["execution"]["external_model_calls"] == 0
    assert set(report["artifact_identity"]) >= {
        "dataset_sha256",
        "dataset_manifest_sha256",
        "runner_sha256",
        "guided_registry_sha256",
        "capability_registry_sha256",
        "corpus_sha256",
        "corpus_manifest_sha256",
        "vector_matrix_sha256",
        "vector_manifest_sha256",
        "typed_inventory_sha256",
        "commit",
        "tree",
    }
