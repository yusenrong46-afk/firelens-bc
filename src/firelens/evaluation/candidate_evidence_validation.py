"""Validation rules for exact-run candidate evidence inputs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.candidate_evidence_common import (
    REQUIRED_COMMAND_POLICIES,
    file_record,
)


def validate_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("candidate evidence timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("candidate evidence timestamp requires a timezone")
    return value


def exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return value


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_checkout_state(value: Any, *, commit: str, tree: str) -> dict[str, Any]:
    state = exact_object(
        value,
        {"schema_version", "commit", "tree", "clean", "status_porcelain"},
        "checkout-state evidence",
    )
    if state["schema_version"] != "firelens.checkout_state.v1":
        raise ValueError("checkout-state evidence schema is invalid")
    if state["commit"] != commit or state["tree"] != tree:
        raise ValueError("checkout-state evidence does not match the candidate identity")
    if state["clean"] is not True or state["status_porcelain"] != "":
        raise ValueError("candidate evidence requires a captured clean starting state")
    return state


def validate_build_environment(value: Any) -> dict[str, Any]:
    environment = exact_object(
        value,
        {"schema_version", "python", "pip", "node", "npm", "runner_os"},
        "build-environment evidence",
    )
    if environment["schema_version"] != "firelens.build_environment.v1":
        raise ValueError("build-environment evidence schema is invalid")
    for field in ("python", "pip", "node", "npm", "runner_os"):
        nonempty_string(environment[field], f"build-environment {field}")
    return environment


def validate_command_outcomes(value: Any) -> dict[str, Any]:
    document = exact_object(value, {"schema_version", "commands"}, "command-outcome evidence")
    if document["schema_version"] != "firelens.command_outcomes.v1":
        raise ValueError("command-outcome evidence schema is invalid")
    commands = document["commands"]
    if not isinstance(commands, list):
        raise ValueError("command-outcome evidence has no command roster")
    observed: dict[str, dict[str, Any]] = {}
    for row in commands:
        item = exact_object(row, {"id", "command", "exit_code"}, "command outcome")
        command_id = nonempty_string(item["id"], "command outcome id")
        nonempty_string(item["command"], f"command outcome {command_id} command")
        exit_code = item["exit_code"]
        if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code < 0:
            raise ValueError(f"command outcome {command_id} exit code is invalid")
        if command_id in observed:
            raise ValueError(f"command outcome is duplicated: {command_id}")
        observed[command_id] = item
    if set(observed) != set(REQUIRED_COMMAND_POLICIES):
        raise ValueError(
            "command-outcome evidence does not contain the exact required commands"
        )
    failed = [
        command_id
        for command_id, allowed in REQUIRED_COMMAND_POLICIES.items()
        if observed[command_id]["exit_code"] not in allowed
    ]
    if failed:
        raise ValueError(f"candidate qualification command failed: {', '.join(sorted(failed))}")
    return document


def validate_workflow_identity(value: Any, *, commit: str, tree: str) -> dict[str, Any]:
    identity = exact_object(
        value,
        {
            "schema_version",
            "repository",
            "workflow",
            "event",
            "ref",
            "commit",
            "tree",
            "run_id",
            "run_attempt",
        },
        "workflow-identity evidence",
    )
    if identity["schema_version"] != "firelens.workflow_identity.v1":
        raise ValueError("workflow-identity evidence schema is invalid")
    if identity["commit"] != commit or identity["tree"] != tree:
        raise ValueError("workflow-identity evidence does not match the candidate identity")
    for field in ("repository", "workflow", "event", "ref", "run_id", "run_attempt"):
        nonempty_string(identity[field], f"workflow identity {field}")
    if identity["workflow"] != ".github/workflows/candidate.yml" or identity["event"] not in {
        "pull_request",
        "workflow_dispatch",
    }:
        raise ValueError("workflow-identity evidence names an unsupported workflow or event")
    return identity


def validate_credential_absence(value: Any) -> dict[str, Any]:
    document = exact_object(
        value,
        {
            "schema_version",
            "checked_names",
            "present_names",
            "provider_calls",
            "paid_cost_usd",
            "sealed_labels_accessed",
        },
        "credential-absence evidence",
    )
    if document["schema_version"] != "firelens.credential_absence.v1":
        raise ValueError("credential-absence evidence schema is invalid")
    checked = document["checked_names"]
    required = {
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "COHERE_API_KEY",
        "FIRELENS_RUN_OPENROUTER_SMOKE",
    }
    if (
        not isinstance(checked, list)
        or any(not isinstance(item, str) or not item for item in checked)
        or set(checked) != required
        or len(checked) != len(required)
    ):
        raise ValueError("credential-absence evidence did not check required credential names")
    if document["present_names"] != []:
        raise ValueError("candidate workflow had provider credentials present")
    provider_calls = document["provider_calls"]
    paid_cost = document["paid_cost_usd"]
    if (
        not isinstance(provider_calls, int)
        or isinstance(provider_calls, bool)
        or provider_calls != 0
        or not isinstance(paid_cost, (int, float))
        or isinstance(paid_cost, bool)
        or paid_cost != 0
    ):
        raise ValueError("candidate workflow must remain zero-call and zero-cost")
    if document["sealed_labels_accessed"] is not False:
        raise ValueError("candidate workflow must not access sealed labels")
    return document


def validate_structured_eval(value: Any, *, root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("structured-publication evidence must be an object")
    structural = value.get("structural_gates")
    architecture = value.get("architecture")
    if value.get("evidence_class") != "EXECUTED" or value.get("structural_pass") is not True:
        raise ValueError("structured-publication evidence did not pass")
    if (
        not isinstance(structural, dict)
        or not structural
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item != 0
            for item in structural.values()
        )
    ):
        raise ValueError("structured-publication structural leak counters are invalid")
    if (
        not isinstance(architecture, dict)
        or architecture.get("compiler_exclusivity_offenders") != []
        or architecture.get("serving_broad_exception") != []
    ):
        raise ValueError("structured-publication architecture evidence did not pass")
    hashes = value.get("hashes")
    expected_hashes = {
        "hard_probe": file_record(root, "data/evaluation/hard_probe.v1.yaml")["sha256"],
        "typed_inventory": file_record(root, "data/typed_claims/high_risk_v1.yaml")["sha256"],
    }
    if not isinstance(hashes, dict) or any(
        hashes.get(name) != expected for name, expected in expected_hashes.items()
    ):
        raise ValueError("structured-publication evidence artifact hashes are invalid")
    return value


def _hard_probe_passed_ids(value: Any, *, label: str) -> tuple[dict[str, Any], set[str]]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "firelens_hard_probe_report.v1"
    ):
        raise ValueError(f"{label} schema is invalid")
    results = value.get("results")
    if not isinstance(results, list) or len(results) != 105:
        raise ValueError(f"{label} must contain all 105 cases")
    ids: set[str] = set()
    passed: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            raise ValueError(f"{label} contains an invalid case")
        case_id = row.get("id")
        did_pass = row.get("passed")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError(f"{label} case identities are invalid")
        if not isinstance(did_pass, bool):
            raise ValueError(f"{label} case disposition is invalid")
        ids.add(case_id)
        if did_pass:
            passed.add(case_id)
    return value, passed


def validate_hard_probe(
    value: Any, baseline: Any, *, root: Path, commit: str
) -> tuple[dict[str, Any], dict[str, object]]:
    report, passed = _hard_probe_passed_ids(value, label="exact-run hard-probe evidence")
    _, baseline_passed = _hard_probe_passed_ids(baseline, label="hard-probe baseline")
    manifest = report.get("manifest")
    summary = report.get("summary")
    expected_hashes = {
        "dataset_sha256": file_record(root, "data/evaluation/hard_probe.v1.yaml")["sha256"],
        "corpus_sha256": file_record(
            root, "data/processed/firelens_static_corpus.chunks.jsonl"
        )["sha256"],
        "corpus_manifest_sha256": file_record(
            root, "data/processed/firelens_static_corpus.manifest.json"
        )["sha256"],
        "vector_matrix_sha256": file_record(root, "data/index/firelens_vectors.npy")["sha256"],
        "vector_manifest_sha256": file_record(
            root, "data/index/firelens_vectors.manifest.json"
        )["sha256"],
    }
    if (
        not isinstance(manifest, dict)
        or manifest.get("commit") != commit
        or manifest.get("mode") != "offline"
        or manifest.get("provider_boundary") != "offline_double"
        or any(manifest.get(name) != expected for name, expected in expected_hashes.items())
    ):
        raise ValueError("exact-run hard-probe identity or offline boundary is invalid")
    if (
        not isinstance(summary, dict)
        or summary.get("executed") != 105
        or summary.get("passed") != len(passed)
        or len(passed) < 86
        or summary.get("cost_usd") != 0
    ):
        raise ValueError("exact-run hard-probe did not meet the frozen 86/105 zero-cost floor")
    regressions = sorted(baseline_passed - passed)
    if regressions:
        raise ValueError(
            "exact-run hard-probe regressed previously passing cases: " + ", ".join(regressions)
        )
    return report, {
        "executed": 105,
        "passed": len(passed),
        "floor": 86,
        "paired_regressions": regressions,
        "provider_calls": 0,
        "cost_usd": 0,
    }


def validate_limitations(limitations: list[str]) -> list[str]:
    if not limitations or len(set(limitations)) != len(limitations):
        raise ValueError("candidate evidence requires unique explicit limitations")
    return [nonempty_string(item, "candidate limitation") for item in limitations]
