from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from firelens.evaluation.product_question_cases import build_v1_6_user_end_cases

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/evaluation/v1_6_user_end_questions_50.json"
MANIFEST = ROOT / "data/evaluation/v1_6_user_end_questions_50.manifest.json"


def _payload() -> dict[str, object]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_user_end_catalog_has_exactly_fifty_cases_and_unique_ids() -> None:
    payload = _payload()
    cases = payload["cases"]

    assert payload["schema_version"] == "firelens.v1_6_user_end_questions.v1"
    assert payload["status"] == "development_unsealed"
    assert payload["case_count"] == 50
    assert isinstance(cases, list)
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    assert all(isinstance(case["question"], str) and case["question"].strip() for case in cases)


def test_user_end_catalog_covers_easy_to_very_hard_and_misleading_surfaces() -> None:
    cases = _payload()["cases"]
    difficulties = Counter(case["difficulty"] for case in cases)

    assert difficulties == {"easy": 12, "medium": 13, "hard": 13, "very_hard": 12}
    assert sum(case["risk"] == "adversarial" for case in cases) >= 5
    assert sum("map" in case["ux_checks"] for case in cases) >= 15
    assert sum("proof_card" in case["ux_checks"] for case in cases) >= 15
    assert sum("privacy_boundary" in case["ux_checks"] for case in cases) >= 5
    assert sum("history" in case for case in cases) >= 4
    assert sum(case["location_expectation"] == "required" for case in cases) >= 8


def test_every_case_declares_a_route_and_visible_user_contract() -> None:
    cases = _payload()["cases"]
    allowed_modes = {
        "abstention",
        "background",
        "capability",
        "grounded",
        "live",
        "mixed",
        "partial",
        "requires_input",
        "scope_redirect",
    }
    allowed_location_expectations = {
        "none",
        "coarse_in_question",
        "required",
        "selected_result",
        "selected_or_required",
        "history_correction",
        "context_required",
    }

    for case in cases:
        assert set(case["expected_modes"]) <= allowed_modes
        assert case["expected_modes"]
        assert case["location_expectation"] in allowed_location_expectations
        assert case["ux_checks"]
        assert case["assertions"]
        assert case["forbidden_behaviors"]
        if "history" in case:
            assert case["history"]
            assert all(row["role"] in {"user", "assistant"} for row in case["history"])


def test_catalog_loads_into_the_existing_zero_cost_product_probe_contract() -> None:
    cases = build_v1_6_user_end_cases()

    assert len(cases) == 50
    assert len({case.id for case in cases}) == 50
    assert all(case.notes.startswith("Assertions:") for case in cases)
    assert sum(case.location_expectation == "required" for case in cases) >= 8
    assert sum(bool(case.required_live_kinds) for case in cases) >= 10


def test_manifest_binds_the_catalog_bytes_and_preserves_unsealed_status() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["catalog_id"] == "firelens_v1_6_user_end_questions_50"
    assert manifest["catalog_sha256"] == hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    assert manifest["case_count"] == 50
    assert manifest["status"] == "development_unsealed"
    assert manifest["qualification_role"] == "not_sealed_not_release_proof"
    assert manifest["provider_calls_in_catalog_build"] == 0
