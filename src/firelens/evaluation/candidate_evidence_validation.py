"""Validation rules for exact-run candidate evidence inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from firelens.evaluation.candidate_evidence_common import (
    HARD_PROBE_FROZEN_RC2_PROFILE_MANIFEST_PATH,
    HARD_PROBE_FROZEN_RC2_PROFILE_PATH,
    HARD_PROBE_MIGRATED_IDS,
    HARD_PROBE_MIXED_MIGRATED_IDS,
    HARD_PROBE_PROFILE,
    HARD_PROBE_PROFILE_MANIFEST_PATH,
    HARD_PROBE_PROFILE_PATH,
    HARD_PROBE_QUOTE_ONLY_MIGRATED_IDS,
    HARD_PROBE_RC2_MIGRATED_IDS,
    REQUIRED_COMMAND_POLICIES,
    file_record,
    load_json,
    strict_file,
    validate_handoff_migration,
    validate_mixed_migration,
    validate_quote_only_migration,
    validate_report_semantic_checks,
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


_PROFILE_FIELDS = {
    "schema_version",
    "profile",
    "base_dataset_sha256",
    "minimum_passed",
    "migrations",
}
_PROFILE_MANIFEST_FIELDS = {
    "schema_version",
    "profile",
    "expectations_sha256",
    "base_dataset_sha256",
    "migration_count",
    "migration_ids",
    "minimum_passed",
}
_MIGRATION_FIELDS = {
    "id",
    "add_allowed_modes",
    "required_publication_kinds",
    "require_validation_accepted",
    "require_exact_quote_support",
    "require_zero_generation",
    "require_zero_claims",
    "require_zero_evidence",
    "require_official_handoff",
    "required_reason_code",
    "rationale",
}


def _profile_case_inputs(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset_path = strict_file(root, "data/evaluation/hard_probe.v1.yaml")
    try:
        dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("hard-probe base dataset must be valid UTF-8 YAML") from exc
    if not isinstance(dataset, dict) or not isinstance(dataset.get("cases"), list):
        raise ValueError("hard-probe base dataset has no case roster")
    cases = dataset["cases"]
    if len(cases) != 105:
        raise ValueError("hard-probe base dataset must contain all 105 cases")
    seen: set[str] = set()
    normalized_cases: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("hard-probe base dataset contains an invalid case")
        case_id = case.get("id")
        allowed_modes = case.get("allowed_modes")
        if (
            not isinstance(case_id, str)
            or not case_id
            or case_id in seen
            or not isinstance(allowed_modes, list)
            or not allowed_modes
            or any(not isinstance(mode, str) or not mode for mode in allowed_modes)
            or len(set(allowed_modes)) != len(allowed_modes)
        ):
            raise ValueError("hard-probe base expectations are invalid")
        seen.add(case_id)
        normalized_cases.append({"id": case_id, "allowed_modes": allowed_modes})

    base_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    base_manifest = load_json(
        strict_file(root, "data/evaluation/hard_probe.v1.manifest.json"),
        "hard-probe base manifest",
    )
    if (
        not isinstance(base_manifest, dict)
        or base_manifest.get("dataset_sha256") != base_hash
        or base_manifest.get("case_count") != 105
    ):
        raise ValueError("hard-probe base dataset does not match its manifest")
    return normalized_cases, {"dataset_sha256": base_hash}


def _validate_migration(value: Any) -> dict[str, Any]:
    migration = exact_object(value, _MIGRATION_FIELDS, "hard-probe profile migration")
    case_id = nonempty_string(migration["id"], "hard-probe profile migration id")
    nonempty_string(migration["rationale"], f"hard-probe profile migration {case_id} rationale")
    if case_id in HARD_PROBE_QUOTE_ONLY_MIGRATED_IDS:
        expected = {
            "add_allowed_modes": ["partial"],
            "required_publication_kinds": ["official_quote_only"],
            "require_validation_accepted": True,
            "require_exact_quote_support": True,
            "require_zero_generation": True,
            "require_zero_claims": False,
            "require_zero_evidence": False,
            "require_official_handoff": False,
            "required_reason_code": None,
            "rationale": (
                "Accept the deterministic official-quote-only downgrade required by "
                "structured publication."
            ),
        }
    elif case_id == "J01":
        expected = {
            "add_allowed_modes": ["scope_redirect"],
            "required_publication_kinds": [],
            "require_validation_accepted": False,
            "require_exact_quote_support": False,
            "require_zero_generation": True,
            "require_zero_claims": True,
            "require_zero_evidence": True,
            "require_official_handoff": True,
            "required_reason_code": "high_risk_claim_not_structured",
            "rationale": (
                "Accept the deterministic official issuing-authority handoff when no "
                "reviewed structured claim is available."
            ),
        }
    elif case_id in HARD_PROBE_MIXED_MIGRATED_IDS:
        expected = {
            "add_allowed_modes": ["partial"],
            "required_publication_kinds": [
                "structured_reviewed",
                "official_quote_only",
            ],
            "require_validation_accepted": True,
            "require_exact_quote_support": True,
            "require_zero_generation": True,
            "require_zero_claims": False,
            "require_zero_evidence": False,
            "require_official_handoff": False,
            "required_reason_code": "high_risk_claim_not_structured",
            "rationale": (
                "Accept the deterministic mixed reviewed-claim and exact-official-quote "
                "response for the requested grab-and-go contents."
            ),
        }
    else:
        raise ValueError(f"hard-probe profile contains an undeclared migration: {case_id}")
    if any(migration[field] != expected_value for field, expected_value in expected.items()):
        raise ValueError(f"hard-probe profile migration is invalid: {case_id}")
    return migration


def _load_named_profile(
    root: Path,
    *,
    base_hash: str,
    profile_name: str,
    profile_relative_path: str,
    manifest_relative_path: str,
    expected_migration_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str]:
    profile_path = strict_file(root, profile_relative_path)
    try:
        profile_value = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("hard-probe expectation profile must be valid UTF-8 YAML") from exc
    profile = exact_object(profile_value, _PROFILE_FIELDS, "hard-probe expectation profile")
    if (
        profile["schema_version"] != "firelens.hard_probe_expectations.v1"
        or profile["profile"] != profile_name
        or profile["base_dataset_sha256"] != base_hash
        or profile["minimum_passed"] != 86
        or not isinstance(profile["migrations"], list)
    ):
        raise ValueError("hard-probe expectation profile identity or floor is invalid")
    migrations = [_validate_migration(item) for item in profile["migrations"]]
    migration_ids = [item["id"] for item in migrations]
    if migration_ids != list(expected_migration_ids):
        raise ValueError("hard-probe expectation profile migration roster is invalid")

    profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    manifest = load_json(
        strict_file(root, manifest_relative_path),
        "hard-probe expectation profile manifest",
    )
    manifest = exact_object(
        manifest,
        _PROFILE_MANIFEST_FIELDS,
        "hard-probe expectation profile manifest",
    )
    if manifest != {
        "schema_version": "firelens.hard_probe_expectations_manifest.v1",
        "profile": profile_name,
        "expectations_sha256": profile_hash,
        "base_dataset_sha256": base_hash,
        "migration_count": len(expected_migration_ids),
        "migration_ids": sorted(expected_migration_ids),
        "minimum_passed": 86,
    }:
        raise ValueError("hard-probe expectation profile does not match its manifest")
    return migrations, profile_hash


def _load_hard_probe_profile(root: Path) -> dict[str, Any]:
    cases, base_identity = _profile_case_inputs(root)
    base_hash = base_identity["dataset_sha256"]
    _load_named_profile(
        root,
        base_hash=base_hash,
        profile_name="rc2",
        profile_relative_path=HARD_PROBE_FROZEN_RC2_PROFILE_PATH,
        manifest_relative_path=HARD_PROBE_FROZEN_RC2_PROFILE_MANIFEST_PATH,
        expected_migration_ids=HARD_PROBE_RC2_MIGRATED_IDS,
    )
    migrations, profile_hash = _load_named_profile(
        root,
        base_hash=base_hash,
        profile_name=HARD_PROBE_PROFILE,
        profile_relative_path=HARD_PROBE_PROFILE_PATH,
        manifest_relative_path=HARD_PROBE_PROFILE_MANIFEST_PATH,
        expected_migration_ids=HARD_PROBE_MIGRATED_IDS,
    )
    migration_ids = [item["id"] for item in migrations]
    case_ids = {case["id"] for case in cases}
    if not set(migration_ids).issubset(case_ids):
        raise ValueError("hard-probe expectation profile references a missing base case")

    migration_by_id = {item["id"]: item for item in migrations}
    effective_cases = []
    for case in cases:
        migration = migration_by_id.get(case["id"])
        additions = [] if migration is None else migration["add_allowed_modes"]
        allowed_modes = [*case["allowed_modes"]]
        allowed_modes.extend(mode for mode in additions if mode not in allowed_modes)
        effective_cases.append(
            {
                "id": case["id"],
                "allowed_modes": allowed_modes,
                "migration": migration,
            }
        )
    effective = {
        "schema_version": "firelens.hard_probe_effective_expectations.v1",
        "profile": HARD_PROBE_PROFILE,
        "base_dataset_sha256": base_hash,
        "minimum_passed": 86,
        "cases": effective_cases,
    }
    effective_bytes = json.dumps(
        effective,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return {
        "base_dataset_sha256": base_hash,
        "case_ids": [case["id"] for case in cases],
        "effective_allowed_modes": {
            case["id"]: case["allowed_modes"] for case in effective_cases
        },
        "migrations": migration_by_id,
        "expectation_overlay_sha256": profile_hash,
        "effective_expectations_sha256": hashlib.sha256(effective_bytes).hexdigest(),
        "minimum_passed": 86,
    }


def _hard_probe_passed_ids(
    value: Any,
    *,
    label: str,
    schema_version: str,
    expected_ids: set[str],
) -> tuple[dict[str, Any], set[str], dict[str, dict[str, Any]]]:
    if not isinstance(value, dict) or value.get("schema_version") != schema_version:
        raise ValueError(f"{label} schema is invalid")
    results = value.get("results")
    if not isinstance(results, list) or len(results) != 105:
        raise ValueError(f"{label} must contain all 105 cases")
    ids: set[str] = set()
    passed: set[str] = set()
    rows: dict[str, dict[str, Any]] = {}
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
        rows[case_id] = row
        if did_pass:
            passed.add(case_id)
    if ids != expected_ids:
        raise ValueError(f"{label} case roster does not match the base dataset")
    return value, passed, rows


def validate_hard_probe(
    value: Any, baseline: Any, *, root: Path, commit: str, tree: str
) -> tuple[dict[str, Any], dict[str, object]]:
    profile = _load_hard_probe_profile(root)
    expected_ids = set(profile["case_ids"])
    report, passed, rows = _hard_probe_passed_ids(
        value,
        label="exact-run hard-probe evidence",
        schema_version="firelens_hard_probe_report.v2",
        expected_ids=expected_ids,
    )
    _, baseline_passed, _ = _hard_probe_passed_ids(
        baseline,
        label="hard-probe baseline",
        schema_version="firelens_hard_probe_report.v1",
        expected_ids=expected_ids,
    )
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
        or manifest.get("tree") != tree
        or manifest.get("mode") != "offline"
        or manifest.get("provider_boundary") != "offline_double"
        or manifest.get("expectation_profile") != HARD_PROBE_PROFILE
        or manifest.get("expectation_overlay_sha256") != profile["expectation_overlay_sha256"]
        or manifest.get("effective_expectations_sha256")
        != profile["effective_expectations_sha256"]
        or any(manifest.get(name) != expected for name, expected in expected_hashes.items())
    ):
        raise ValueError("exact-run hard-probe identity or offline boundary is invalid")
    if (
        not isinstance(summary, dict)
        or summary.get("executed") != 105
        or summary.get("passed") != len(passed)
        or summary.get("failed") != 105 - len(passed)
        or summary.get("minimum_passed") != profile["minimum_passed"]
        or summary.get("minimum_passed_met") is not True
        or len(passed) < profile["minimum_passed"]
        or not isinstance(summary.get("cost_usd"), (int, float))
        or isinstance(summary.get("cost_usd"), bool)
        or summary.get("cost_usd") != 0
        or any(
            not isinstance(row.get("cost_usd"), (int, float))
            or isinstance(row.get("cost_usd"), bool)
            or row.get("cost_usd") != 0
            for row in rows.values()
        )
    ):
        raise ValueError("exact-run hard-probe did not meet the frozen 86/105 zero-cost floor")
    migrations = profile["migrations"]
    for case_id, row in rows.items():
        if row.get("applied_migration") != migrations.get(case_id):
            raise ValueError(
                f"exact-run hard-probe contains an unbound expectation change: {case_id}"
            )
        if row.get("effective_allowed_modes") != profile["effective_allowed_modes"][case_id]:
            raise ValueError(
                f"exact-run hard-probe effective expectations are invalid: {case_id}"
            )
        validate_report_semantic_checks(row, case_id=case_id)
    for case_id in sorted(HARD_PROBE_QUOTE_ONLY_MIGRATED_IDS):
        validate_quote_only_migration(rows[case_id], case_id=case_id)
    for case_id in sorted(HARD_PROBE_MIXED_MIGRATED_IDS):
        validate_mixed_migration(rows[case_id], case_id=case_id)
    validate_handoff_migration(rows["J01"])

    regressions = sorted(baseline_passed - passed - set(HARD_PROBE_MIGRATED_IDS))
    if regressions:
        raise ValueError(
            "exact-run hard-probe regressed previously passing cases: " + ", ".join(regressions)
        )
    return report, {
        "executed": 105,
        "passed": len(passed),
        "floor": profile["minimum_passed"],
        "expectation_profile": HARD_PROBE_PROFILE,
        "migrated_case_ids": sorted(HARD_PROBE_MIGRATED_IDS),
        "paired_regressions": regressions,
        "provider_calls": 0,
        "cost_usd": 0,
    }


def validate_limitations(limitations: list[str]) -> list[str]:
    if not limitations or len(set(limitations)) != len(limitations):
        raise ValueError("candidate evidence requires unique explicit limitations")
    return [nonempty_string(item, "candidate limitation") for item in limitations]
