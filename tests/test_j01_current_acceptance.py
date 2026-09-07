"""Current J01 oracle controls; frozen legacy acceptance remains a failure."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from firelens.evaluation.hard_probe_cli import _run_case
from firelens.evaluation.hard_probe_expectations import (
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    load_dataset,
    load_expectation_profile,
)
from firelens.evaluation.j01_current_acceptance import (
    ROOT,
    current_source_explanation_supported,
    legacy_j01_result,
    validate_current_j01,
)
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent


def response():
    return json.loads(
        (Path(__file__).parent / "fixtures/j01_current_response.json").read_text()
    )


def packaged():
    payload = response()
    legacy = legacy_j01_result(payload, [])
    return dict(
        passed=True,
        response=payload,
        question=legacy["question"],
        request_history=legacy["history"],
        provider_stages=[],
        legacy_profile_result=legacy,
    )


def test_only_j01_changes_and_floor_is_frozen():
    dataset = load_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)
    old = load_expectation_profile("rc2.2", dataset, dataset_path=DEFAULT_DATASET)
    new = load_expectation_profile("rc2.3", dataset, dataset_path=DEFAULT_DATASET)
    assert new.minimum_passed == old.minimum_passed == 86
    assert len(dataset.cases) == 105
    assert old.migrations.keys() == new.migrations.keys()
    assert [key for key in old.migrations if old.migrations[key] != new.migrations[key]] == [
        "J01"
    ]
    validate_current_j01(packaged(), root=ROOT)
    assert not legacy_j01_result(response(), [])["passed"]


def test_real_fixture_execution_emits_both_results(tmp_path):
    async def run():
        agent, _, _ = await fixture_agent(tmp_path)
        dataset = load_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)
        case = next(case for case in dataset.cases if case.id == "J01")
        migration = load_expectation_profile(
            "rc2.3", dataset, dataset_path=DEFAULT_DATASET
        ).migrations["J01"]
        async with httpx.AsyncClient() as client:
            row = await _run_case(
                case, migration, SimpleNamespace(service=agent.static_service), client, tmp_path
            )
        validate_current_j01(row, root=ROOT)
        assert row["passed"] and not row["legacy_profile_result"]["passed"]
        assert all(item["passed"] for item in row["semantic_checks"]["migration_invariants"])

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "retired_hash",
        "wrong_url",
        "missing_evidence",
        "invented_quote",
        "invented_answer",
        "rejected",
        "personal_decision",
    ],
)
def test_rejects_unsupported_response(mutation):
    payload = response()
    if mutation == "retired_hash":
        for item in payload["evidence"]:
            item["document_sha256"] = (
                "f82166e0c05cb3f46a42aa4023da7cdd71e3c3fdae64965c8f436426f5702ea3"
            )
    elif mutation == "wrong_url":
        for item in payload["evidence"]:
            item["canonical_url"] = "https://example.org/unrelated"
    elif mutation == "missing_evidence":
        payload["evidence"] = []
    elif mutation == "invented_quote":
        claim = payload["claims"][0]
        claim["text"] = claim["supports"][0]["quote"] = payload["answer"] = (
            "You will not be caught off guard."
        )
    elif mutation == "invented_answer":
        payload["answer"] += " This guarantees your safety."
    elif mutation == "rejected":
        payload["validation"]["accepted"] = False
    else:
        payload["answer"] += " You should evacuate now."
    payload["history_text"] = None
    assert not current_source_explanation_supported(payload)


def test_checklist_requires_explicit_missing_explanation():
    payload = response()
    quote = "Do you have pets?"
    payload["claims"][0]["text"] = payload["claims"][0]["supports"][0]["quote"] = quote
    payload["answer"] = quote
    payload["limitations"] = []
    payload["history_text"] = None
    assert not current_source_explanation_supported(payload)
    payload["limitations"] = ["The selected evidence does not explain why this matters."]
    assert current_source_explanation_supported(payload)


@pytest.mark.parametrize("mutation", ["history", "question", "legacy", "generation", "cost"])
def test_package_rejects_antecedent_or_generation_drift(mutation):
    row = deepcopy(packaged())
    if mutation == "history":
        row["request_history"] = []
    elif mutation == "question":
        row["question"] = "Should I leave?"
    elif mutation == "legacy":
        row["legacy_profile_result"]["passed"] = True
    else:
        row["provider_stages"] = [
            dict(
                stage="generation",
                attempts=1 if mutation == "generation" else 0,
                cost_usd=0.1 if mutation == "cost" else 0.0,
            )
        ]
    with pytest.raises(ValueError):
        validate_current_j01(row, root=ROOT)
