"""Versioned J01 source/explanation oracle and paired frozen-profile observation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from firelens.evaluation.hard_probe_semantics import (
    current_source_explanation_supported as current_source_explanation_supported,
)


def legacy_j01_result(response: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-evaluate the SAME response under the unchanged rc2.2 J01 contract."""
    from firelens.evaluation.hard_probe_expectations import (
        DEFAULT_DATASET,
        DEFAULT_MANIFEST,
        _migration_invariant_checks,
        effective_allowed_modes,
        load_dataset,
        load_expectation_profile,
    )
    from firelens.evaluation.hard_probe_semantics import _semantic_checks

    dataset = load_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)
    case = next(case for case in dataset.cases if case.id == "J01")
    migration = load_expectation_profile(
        "rc2.2", dataset, dataset_path=DEFAULT_DATASET
    ).migrations["J01"]
    effective = case.model_copy(
        update={"allowed_modes": effective_allowed_modes(case, migration)}
    )
    issues = _semantic_checks(effective, response)
    invariants = _migration_invariant_checks(migration, response, stages)
    return {
        "profile": "rc2.2",
        "passed": not issues and all(c["passed"] for c in invariants),
        "question": case.question,
        "history": [turn.model_dump(mode="json") for turn in case.history],
        "base_issues": issues,
        "migration_invariants": invariants,
    }


def validate_current_j01(row: dict[str, Any], *, root: Path) -> None:
    from firelens.evaluation.candidate_evidence_common import validate_zero_generation

    validate_zero_generation(row, case_id="J01")
    if row.get("passed") is not True or not current_source_explanation_supported(
        row.get("response", {}), root=root
    ):
        raise ValueError("J01 current source/explanation contract failed")
    legacy = legacy_j01_result(row["response"], row.get("provider_stages", []))
    if row.get("legacy_profile_result") != legacy or legacy["passed"] is not False:
        raise ValueError("J01 must retain its recomputed legacy failure")
    if (
        row.get("question") != legacy["question"]
        or row.get("request_history") != legacy["history"]
    ):
        raise ValueError("J01 original question/history changed")
