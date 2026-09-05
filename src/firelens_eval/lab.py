"""Thin, fail-closed adapters over the existing FireLens evaluation systems.

EvalLab deliberately does not replace suite-owned oracles. It executes the
current zero-cost runners, retains their raw reports, verifies the important
identity and accounting fields, and emits one normalized evidence envelope.
Provider, live, browser, and mutating historical runners are inventory-only.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml

import firelens
from firelens.evaluation import hard_probe_cli, productbench_v2
from firelens.evaluation.claimbench_v2 import (
    CLAIMBENCH_V2_RELATIVE,
    MANIFEST_V2_RELATIVE,
    catalog_v2_identity,
    evaluate_v2_catalog,
    load_claimbench_v2,
)
from firelens.evaluation.common import ROOT, file_sha256
from firelens.evaluation.hard_probe_expectations import (
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    DEFAULT_RC2_2_EXPECTATIONS,
    DEFAULT_RC2_2_EXPECTATIONS_MANIFEST,
    canonical_json_sha256,
    effective_expectations_payload,
    load_dataset,
    load_expectation_profile,
)
from firelens.evaluation.source_aware_conversation import run as run_source_aware
from firelens_eval import local_adapters

Status = Literal["PASS", "FAIL", "BLOCKED", "NOT_RUN"]
LifecycleStatus = Literal["confirmed_fail", "review", "fixed", "cannot_reproduce"]
DivergenceConfidence = Literal["confirmed", "suspected", "unknown"]

SUITES = ("core", "rag", "metamorphic", "trajectory", "fault", "ui", "performance")
REGISTRY_RELATIVE = Path("data/evaluation/eval_lab_registry.v1.yaml")
POLICY_RELATIVE = Path("data/evaluation/eval_lab_policy.v1.yaml")
DEFAULT_ARTIFACT_ROOT = ROOT / "output/eval_lab"
RUN_SCHEMA_VERSION = "firelens.eval_lab.run.v1"
FAILURE_SCHEMA_VERSION = "firelens.eval_lab.failure.v1"
PIPELINE_STAGES = (
    "understanding",
    "binding",
    "authority",
    "planning",
    "retrieval",
    "reranking",
    "evidence",
    "generation",
    "validation",
    "composition",
    "frontend",
)
EVAL_LAB_SOURCE_RELATIVES = (
    Path("src/firelens_eval/__init__.py"),
    Path("src/firelens_eval/__main__.py"),
    Path("src/firelens_eval/cli.py"),
    Path("src/firelens_eval/lab.py"),
    Path("src/firelens_eval/local_adapters.py"),
    Path("src/firelens_eval/semantic_oracles.py"),
    Path("src/firelens_eval/pytest_reporter.py"),
)
EVALUATION_SCRIPT_RELATIVES = (
    Path("scripts/claimbench_v2.py"),
    Path("scripts/run_hard_probe.py"),
    Path("scripts/run_productbench.py"),
    Path("scripts/run_source_aware_conversation.py"),
    Path("scripts/v1_6_round2_performance.py"),
)
FAILURE_SCHEMA_RELATIVE = Path("evals/eval_lab/schema/failure_record.schema.json")
FAILURE_DATASET_RELATIVES: dict[str, Path] = {
    "productbench_offline": Path("data/evaluation/productbench_journeys_50.json"),
    "claimbench_v2": Path("data/evaluation/claimbench_v1_6_2.yaml"),
    "hard_probe_rc2_2": Path("data/evaluation/hard_probe.v1.yaml"),
    "source_aware_conversation": Path("data/evaluation/source_aware_conversation.v1.yaml"),
}
FAILURE_EVALUATOR_RELATIVES: dict[str, Path] = {
    "productbench_offline": Path("src/firelens/evaluation/productbench_v2.py"),
    "claimbench_v2": Path("src/firelens/evaluation/claimbench_v2.py"),
    "hard_probe_rc2_2": Path("src/firelens/evaluation/hard_probe_cli.py"),
    "source_aware_conversation": Path("src/firelens/evaluation/source_aware_conversation.py"),
}


@dataclass(frozen=True)
class RunContext:
    root: Path
    run_dir: Path
    run_id: str
    started_at: str
    identity: dict[str, Any]
    registry: dict[str, Any]
    policy: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    if path.suffix in {".yaml", ".yml"}:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return cast(dict[str, Any], value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def eval_lab_source_identity(root: Path = ROOT) -> dict[str, Any]:
    files = {str(path): file_sha256(root / path) for path in EVAL_LAB_SOURCE_RELATIVES}
    return {"files": files, "sha256": _canonical_sha256(files)}


def evaluation_source_identity(root: Path = ROOT) -> dict[str, Any]:
    """Bind all evaluator-owned Python plus the invoked core entry scripts."""

    evaluation_root = root / "src/firelens/evaluation"
    relatives = [
        path.relative_to(root) for path in evaluation_root.rglob("*.py") if path.is_file()
    ]
    relatives.extend(EVALUATION_SCRIPT_RELATIVES)
    files = {
        str(path): file_sha256(root / path)
        for path in sorted(set(relatives), key=lambda item: str(item))
    }
    if not files:
        raise ValueError("evaluation source inventory is empty")
    return {"files": files, "sha256": _canonical_sha256(files)}


def _git_value(root: Path, *arguments: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _git_bytes(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"git {' '.join(arguments)} failed")
    return completed.stdout


def _working_tree_sha256(root: Path, status: bytes) -> str:
    """Bind tracked diffs and untracked bytes, not merely dirty path names."""

    tracked_diff = _git_bytes(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    untracked = _git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z")
    digest = hashlib.sha256()
    for label, payload in ((b"status", status), (b"tracked-diff", tracked_diff)):
        digest.update(label + b"\0" + len(payload).to_bytes(8, "big") + payload)
    for raw_relative in sorted(filter(None, untracked.split(b"\0"))):
        relative = os.fsdecode(raw_relative)
        path = root / relative
        digest.update(b"untracked\0" + raw_relative + b"\0")
        try:
            payload = (
                os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
            )
        except OSError as exc:
            payload = f"UNREADABLE:{type(exc).__name__}:{exc}".encode()
        digest.update(len(payload).to_bytes(8, "big") + payload)
    return digest.hexdigest()


def source_identity(root: Path = ROOT) -> dict[str, Any]:
    status_bytes = _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    status_sha256 = hashlib.sha256(status_bytes).hexdigest()
    working_tree_sha256 = _working_tree_sha256(root, status_bytes)
    commit = _git_value(root, "rev-parse", "HEAD")
    tree = _git_value(root, "rev-parse", "HEAD^{tree}")
    dirty = bool(status_bytes)
    application_sha = (
        _canonical_sha256(
            {
                "commit": commit,
                "tree": tree,
                "working_tree_sha256": working_tree_sha256,
            }
        )
        if dirty
        else commit
    )
    return {
        "commit": commit,
        "tree": tree,
        "branch": _git_value(root, "branch", "--show-current"),
        "dirty": dirty,
        "application_sha": application_sha,
        "working_tree_status_sha256": status_sha256,
        "working_tree_sha256": working_tree_sha256,
        "imported_firelens_path": str(Path(firelens.__file__).resolve()),
        "python_executable": str(Path(sys.executable).resolve()),
    }


def load_registry(root: Path = ROOT) -> dict[str, Any]:
    registry = _load_mapping(root / REGISTRY_RELATIVE)
    if registry.get("schema_version") != "firelens.eval_lab.registry.v1":
        raise ValueError("unsupported EvalLab registry schema")
    suites = registry.get("suites")
    if not isinstance(suites, dict) or set(suites) != set(SUITES):
        raise ValueError("EvalLab registry must define every canonical suite exactly once")
    for suite_name, raw_suite in suites.items():
        if not isinstance(raw_suite, dict):
            raise ValueError(f"suite {suite_name} must be an object")
        adapters = raw_suite.get("adapters")
        if not isinstance(adapters, list) or not adapters:
            raise ValueError(f"suite {suite_name} must declare at least one adapter")
    return registry


def load_policy(root: Path = ROOT) -> dict[str, Any]:
    policy = _load_mapping(root / POLICY_RELATIVE)
    if policy.get("schema_version") != "firelens.eval_lab.policy.v1":
        raise ValueError("unsupported EvalLab policy schema")
    if policy.get("network_allowed") is not False:
        raise ValueError("EvalLab v1 policy must forbid network access")
    if policy.get("provider_calls_allowed") is not False:
        raise ValueError("EvalLab v1 policy must forbid provider calls")
    core = policy.get("core")
    if not isinstance(core, dict):
        raise ValueError("EvalLab core policy is missing")
    expected = {
        "productbench_offline",
        "claimbench_v2",
        "hard_probe_rc2_2",
        "source_aware_conversation",
    }
    if set(core.get("required_adapters") or []) != expected:
        raise ValueError("EvalLab core adapter policy is incomplete")
    required_values: dict[str, dict[str, Any]] = {
        "productbench_offline": {
            "expected_tier": "offline_fake",
            "expected_cases": 31,
            "maximum_failed": 0,
            "maximum_cost_usd": 0.0,
        },
        "claimbench_v2": {
            "expected_cases": 332,
            "expected_faithful": 86,
            "expected_mutations": 246,
            "maximum_unsafe_false_accept_rate": 0.0,
            "maximum_faithful_false_reject_rate": 0.0,
            "require_not_always_abstain": True,
        },
        "hard_probe_rc2_2": {
            "expected_profile": "rc2.2",
            "expected_cases": 105,
            "minimum_passed": 86,
            "fail_on_failed_priority": "CRITICAL",
            "maximum_cost_usd": 0.0,
        },
        "source_aware_conversation": {
            "expected_cases": 106,
            "maximum_external_network_calls": 0,
            "maximum_external_model_calls": 0,
            "maximum_tier_a_b_generation_calls": 0,
            "maximum_tier_a_b_generation_cost_usd": 0.0,
        },
    }
    for adapter_id, required in required_values.items():
        observed = core.get(adapter_id)
        if not isinstance(observed, dict):
            raise ValueError(f"EvalLab policy for {adapter_id} is missing")
        for key, value in required.items():
            if observed.get(key) != value:
                raise ValueError(
                    f"EvalLab policy may not weaken {adapter_id}.{key}; expected {value!r}"
                )
    return policy


def inventory(root: Path = ROOT) -> dict[str, Any]:
    registry = load_registry(root)
    policy = load_policy(root)
    suites_out: dict[str, Any] = {}
    raw_suites = cast(dict[str, Any], registry["suites"])
    for suite_name in SUITES:
        raw_suite = cast(dict[str, Any], raw_suites[suite_name])
        adapters_out: list[dict[str, Any]] = []
        for raw_adapter in cast(list[Any], raw_suite["adapters"]):
            adapter = cast(dict[str, Any], raw_adapter)
            materials = [str(item) for item in cast(list[Any], adapter.get("materials") or [])]
            presence = {
                item: (root / item).is_file() or (root / item).is_dir() for item in materials
            }
            effective_status = str(adapter.get("status"))
            if effective_status == "executable" and not all(presence.values()):
                effective_status = "BLOCKED"
            adapters_out.append(
                {
                    **adapter,
                    "effective_status": effective_status,
                    "material_presence": presence,
                }
            )
        suites_out[suite_name] = {**raw_suite, "adapters": adapters_out}
    return {
        "schema_version": "firelens.eval_lab.inventory.v1",
        "registry": {
            "path": str(REGISTRY_RELATIVE),
            "sha256": file_sha256(root / REGISTRY_RELATIVE),
            "registry_id": registry["registry_id"],
        },
        "policy": {
            "path": str(POLICY_RELATIVE),
            "sha256": file_sha256(root / POLICY_RELATIVE),
            "policy_id": policy["policy_id"],
            "qualification_role": policy["qualification_role"],
            "network_allowed": policy["network_allowed"],
            "provider_calls_allowed": policy["provider_calls_allowed"],
        },
        "runner": eval_lab_source_identity(root),
        "failure_record_schema": {
            "path": str(FAILURE_SCHEMA_RELATIVE),
            "sha256": file_sha256(root / FAILURE_SCHEMA_RELATIVE),
        },
        "suites": suites_out,
    }


def _new_failure(
    context: RunContext,
    *,
    suite: str,
    adapter_id: str,
    case_id: str | None,
    status: Literal["FAIL", "BLOCKED", "NOT_RUN"],
    failure_class: str,
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    oracle: str,
    summary: str,
    expected: Any,
    observed: Any,
    evidence: list[str],
    first_divergent_layer: str | None,
    reproduction: list[str],
    input_record: dict[str, Any] | None = None,
    lifecycle_status: LifecycleStatus | None = None,
    first_divergence_owner: str | None = None,
    first_divergence_confidence: DivergenceConfidence | None = None,
    fixed_in_sha: str | None = None,
) -> dict[str, Any]:
    raw_input = input_record or {}
    normalized_input = {
        "question": raw_input.get("question"),
        "history": raw_input.get("history"),
        "location_context": raw_input.get("location_context"),
    }
    effective_lifecycle_status: LifecycleStatus = lifecycle_status or (
        "confirmed_fail" if status == "FAIL" else "review"
    )
    if (
        effective_lifecycle_status == "fixed"
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fixed_in_sha or "") is None
    ):
        raise ValueError(
            "fixed FailureRecords require an exact 40-character candidate SHA "
            "or 64-character working-tree digest"
        )
    dataset_path = FAILURE_DATASET_RELATIVES.get(adapter_id)
    evaluator_path = FAILURE_EVALUATOR_RELATIVES.get(adapter_id)
    dataset_sha = (
        file_sha256(context.root / dataset_path)
        if dataset_path is not None and (context.root / dataset_path).is_file()
        else None
    )
    evaluator_sha = (
        file_sha256(context.root / evaluator_path)
        if evaluator_path is not None and (context.root / evaluator_path).is_file()
        else eval_lab_source_identity(context.root)["sha256"]
        if adapter_id == "eval_lab_identity"
        else None
    )
    first_divergence = {
        "layer": first_divergent_layer,
        "owner": first_divergence_owner or adapter_id,
        "confidence": first_divergence_confidence
        or ("confirmed" if status == "FAIL" else "unknown"),
    }
    core = {
        "run_id": context.run_id,
        "suite": suite,
        "adapter_id": adapter_id,
        "case_id": case_id,
        "status": effective_lifecycle_status,
        "run_status": status,
        "fixed_in_sha": fixed_in_sha,
        "failure_class": failure_class,
        "family": failure_class,
        "summary": summary,
        "input": normalized_input,
        "expected": {"invariants": expected},
        "observed": {"structured_state": observed},
    }
    return {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "failure_id": "ELF-" + _canonical_sha256(core)[:16],
        **core,
        "severity": severity,
        "oracle": oracle,
        "evidence": evidence,
        "first_divergent_layer": first_divergent_layer,
        "first_divergence": first_divergence,
        "pipeline": {stage: None for stage in PIPELINE_STAGES},
        "judge_model": None,
        "judge_prompt": None,
        "judge_prompt_sha256": None,
        "sampling_settings": {},
        "rubric_version": None,
        "application_sha": context.identity.get("application_sha"),
        "reproduction": reproduction,
        "identity": {
            "commit": context.identity.get("commit"),
            "tree": context.identity.get("tree"),
            "dirty": context.identity.get("dirty", True),
            "application_sha": context.identity.get("application_sha"),
            "dataset_sha": dataset_sha,
            "evaluator_sha": evaluator_sha,
            "provider_model": None,
            "embedding_model": None,
            "rerank_model": None,
            "judge_model": None,
            "judge_prompt_sha": None,
        },
        "created_at": _utc_now(),
    }


def validate_failure_record(
    record: dict[str, Any], *, repository_root: Path = ROOT
) -> list[str]:
    """Validate the strict subset of JSON Schema used by FailureRecord v1."""

    schema = _load_mapping(repository_root / FAILURE_SCHEMA_RELATIVE)
    required = {str(item) for item in cast(list[Any], schema["required"])}
    properties = cast(dict[str, Any], schema["properties"])
    issues: list[str] = []
    missing = sorted(required - set(record))
    extra = sorted(set(record) - set(properties))
    if missing:
        issues.append("missing required fields: " + ", ".join(missing))
    if extra:
        issues.append("unexpected fields: " + ", ".join(extra))
    if record.get("schema_version") != FAILURE_SCHEMA_VERSION:
        issues.append("schema_version is not FailureRecord v1")
    if re.fullmatch(r"ELF-[0-9a-f]{16}", str(record.get("failure_id") or "")) is None:
        issues.append("failure_id is malformed")
    for field in ("suite", "status", "run_status", "severity", "oracle"):
        allowed = cast(list[Any], cast(dict[str, Any], properties[field])["enum"])
        if record.get(field) not in allowed:
            issues.append(f"{field} is outside the schema enum")
    fixed_in_sha = record.get("fixed_in_sha")
    if (
        fixed_in_sha is not None
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(fixed_in_sha)) is None
    ):
        issues.append("fixed_in_sha is malformed")
    if record.get("status") == "fixed" and fixed_in_sha is None:
        issues.append("fixed records require fixed_in_sha")
    if record.get("status") != "fixed" and fixed_in_sha is not None:
        issues.append("only fixed records may set fixed_in_sha")
    application_sha = record.get("application_sha")
    if (
        application_sha is not None
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(application_sha)) is None
    ):
        issues.append("application_sha is malformed")
    exact_nested = {
        "input": {"question", "history", "location_context"},
        "expected": {"invariants"},
        "observed": {"structured_state"},
        "pipeline": set(PIPELINE_STAGES),
        "first_divergence": {"layer", "owner", "confidence"},
    }
    for field, expected_keys in exact_nested.items():
        value = record.get(field)
        if not isinstance(value, dict) or set(value) != expected_keys:
            issues.append(f"{field} does not contain its exact required fields")
    divergence = record.get("first_divergence")
    if isinstance(divergence, dict) and divergence.get("confidence") not in {
        "confirmed",
        "suspected",
        "unknown",
    }:
        issues.append("first_divergence.confidence is outside the schema enum")
    if isinstance(divergence, dict) and record.get("first_divergent_layer") != divergence.get(
        "layer"
    ):
        issues.append("first-divergence layer fields disagree")
    identity = record.get("identity")
    identity_required = set(
        cast(list[Any], cast(dict[str, Any], properties["identity"])["required"])
    )
    if not isinstance(identity, dict):
        issues.append("identity is not an object")
    else:
        missing_identity = sorted(identity_required - set(identity))
        extra_identity = sorted(set(identity) - identity_required)
        if missing_identity:
            issues.append("identity is missing: " + ", ".join(missing_identity))
        if extra_identity:
            issues.append("identity has unexpected fields: " + ", ".join(extra_identity))
        if not isinstance(identity.get("dirty"), bool):
            issues.append("identity.dirty is not boolean")
        identity_patterns = {
            "commit": r"[0-9a-f]{40}",
            "tree": r"[0-9a-f]{40}",
            "application_sha": r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
            "dataset_sha": r"[0-9a-f]{64}",
            "evaluator_sha": r"[0-9a-f]{64}",
            "judge_prompt_sha": r"[0-9a-f]{64}",
        }
        for field, pattern in identity_patterns.items():
            value = identity.get(field)
            if value is not None and re.fullmatch(pattern, str(value)) is None:
                issues.append(f"identity.{field} is malformed")
        if record.get("application_sha") != identity.get("application_sha"):
            issues.append("application_sha fields disagree")
        if record.get("judge_model") != identity.get("judge_model"):
            issues.append("judge_model fields disagree")
        if record.get("judge_prompt_sha256") != identity.get("judge_prompt_sha"):
            issues.append("judge prompt SHA fields disagree")
    judge_prompt = record.get("judge_prompt")
    judge_prompt_sha = record.get("judge_prompt_sha256")
    if judge_prompt is None and judge_prompt_sha is not None:
        issues.append("judge prompt SHA requires a judge prompt")
    if isinstance(judge_prompt, str):
        expected_prompt_sha = hashlib.sha256(judge_prompt.encode()).hexdigest()
        if judge_prompt_sha != expected_prompt_sha:
            issues.append("judge prompt SHA does not match the prompt")
    if record.get("oracle") == "calibrated_ai_shadow" and (
        not record.get("judge_model") or not judge_prompt
    ):
        issues.append("AI-judge records require judge model and prompt identity")
    if record.get("status") == "confirmed_fail":
        if record.get("run_status") != "FAIL":
            issues.append("confirmed failures require run_status FAIL")
        if not isinstance(divergence, dict) or divergence.get("confidence") != "confirmed":
            issues.append("confirmed failures require a confirmed first divergence")
    for field in ("evidence", "reproduction"):
        value = record.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            issues.append(f"{field} is not a string array")
    created_at = record.get("created_at")
    try:
        parsed_at = datetime.fromisoformat(str(created_at))
    except ValueError:
        issues.append("created_at is not an ISO date-time")
    else:
        if parsed_at.tzinfo is None:
            issues.append("created_at has no timezone")
    return issues


def _adapter_definition(context: RunContext, adapter_id: str) -> dict[str, Any]:
    suites = cast(dict[str, Any], context.registry["suites"])
    for suite in suites.values():
        suite_mapping = cast(dict[str, Any], suite)
        for raw in cast(list[Any], suite_mapping["adapters"]):
            adapter = cast(dict[str, Any], raw)
            if adapter.get("id") == adapter_id:
                return adapter
    raise ValueError(f"unknown EvalLab adapter: {adapter_id}")


def _adapter_result(
    context: RunContext,
    adapter_id: str,
    *,
    status: Status,
    command: str,
    raw_artifact: str | None,
    case_counts: dict[str, int],
    metrics: dict[str, Any],
    materials: dict[str, Any],
    failures: list[dict[str, Any]],
    limitations: list[str],
    started_at: str,
) -> dict[str, Any]:
    definition = _adapter_definition(context, adapter_id)
    raw_path = context.run_dir / raw_artifact if raw_artifact is not None else None
    return {
        "adapter_id": adapter_id,
        "status": status,
        "classification": definition["classification"],
        "oracle": definition["oracle"],
        "command": command,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "raw_artifact": raw_artifact,
        "raw_artifact_sha256": (
            file_sha256(raw_path) if raw_path is not None and raw_path.is_file() else None
        ),
        "evaluator": evaluation_source_identity(context.root),
        "case_counts": case_counts,
        "metrics": metrics,
        "materials": materials,
        "failure_ids": [str(item["failure_id"]) for item in failures],
        "limitations": limitations,
    }


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def validate_productbench_report(
    report: dict[str, Any], *, repository_root: Path = ROOT
) -> list[str]:
    issues: list[str] = []
    manifest = _load_mapping(repository_root / "data/evaluation/productbench_v2.manifest.json")
    expected_ids = cast(list[Any], cast(dict[str, Any], manifest["tiers"])["offline_fake"])
    results = report.get("results")
    if report.get("schema_version") != "firelens.productbench_report.v2":
        issues.append("schema_version must be firelens.productbench_report.v2")
    if not isinstance(results, list):
        issues.append("results must be a list")
        results = []
    rows = [cast(dict[str, Any], row) for row in results if isinstance(row, dict)]
    observed_ids = [row.get("id") for row in rows]
    if observed_ids != expected_ids:
        issues.append("offline case IDs do not exactly match the manifest tier")
    if report.get("case_count") != len(expected_ids) or len(rows) != len(expected_ids):
        issues.append("offline case count is incomplete")
    recomputed_failed = sum(not bool(row.get("passed")) for row in rows)
    recomputed_passed = len(rows) - recomputed_failed
    if any(
        row.get("passed") is not (not bool(cast(list[Any], row.get("issues") or [])))
        for row in rows
    ):
        issues.append("ProductBench row pass fields do not match their issues")
    if report.get("failed") != recomputed_failed or report.get("passed") != recomputed_passed:
        issues.append("reported pass/fail counts do not match raw rows")
    if report.get("execution_complete") is not True:
        issues.append("execution_complete is not true")
    identity = report.get("identity")
    expected_identity = source_identity(repository_root)
    if not isinstance(identity, dict):
        issues.append("identity is missing")
    else:
        if identity.get("tier") != "offline_fake":
            issues.append("identity tier is not offline_fake")
        if identity.get("raw_catalog_sha256") != file_sha256(
            repository_root / "data/evaluation/productbench_journeys_50.json"
        ):
            issues.append("raw catalog hash mismatch")
        if identity.get("manifest_sha256") != file_sha256(
            repository_root / "data/evaluation/productbench_v2.manifest.json"
        ):
            issues.append("manifest hash mismatch")
        if identity.get("commit") != expected_identity["commit"]:
            issues.append("ProductBench commit does not match the evaluated source")
        if identity.get("tree") != expected_identity["tree"]:
            issues.append("ProductBench tree does not match the evaluated source")
    cost = report.get("cost")
    if not isinstance(cost, dict):
        issues.append("cost evidence is missing")
    else:
        if _number(cost.get("max_cost_usd")) != 0.0:
            issues.append("offline maximum cost is not zero")
        if _number(cost.get("reported_cost_usd")) != 0.0:
            issues.append("offline reported cost is not zero")
        if cost.get("ceiling_exceeded") is not False:
            issues.append("offline cost ceiling is not satisfied")
    if report.get("provider_boundary") != "offline_fake":
        issues.append("provider boundary is not offline_fake")
    if recomputed_failed:
        issues.append(f"{recomputed_failed} ProductBench cases failed")
    return issues


def validate_claimbench_report(
    report: dict[str, Any], *, repository_root: Path = ROOT
) -> list[str]:
    """Validate ClaimBench from raw rows, not submitted summary claims."""

    issues: list[str] = []
    manifest = _load_mapping(repository_root / MANIFEST_V2_RELATIVE)
    expected_identity = source_identity(repository_root)
    identity = report.get("identity")
    if report.get("schema_version") != "firelens.claimbench_v2_report.v1":
        issues.append("ClaimBench report schema mismatch")
    if not isinstance(identity, dict):
        issues.append("ClaimBench report identity is missing")
    else:
        catalog_identity = identity.get("catalog")
        manifest_identity = identity.get("manifest")
        if not isinstance(catalog_identity, dict) or catalog_identity.get(
            "sha256"
        ) != file_sha256(repository_root / CLAIMBENCH_V2_RELATIVE):
            issues.append("ClaimBench report catalog identity mismatch")
        if not isinstance(manifest_identity, dict) or manifest_identity.get(
            "sha256"
        ) != file_sha256(repository_root / MANIFEST_V2_RELATIVE):
            issues.append("ClaimBench report manifest identity mismatch")
        if identity.get("commit") != expected_identity["commit"]:
            issues.append("ClaimBench commit does not match the evaluated source")
        if identity.get("tree") != expected_identity["tree"]:
            issues.append("ClaimBench tree does not match the evaluated source")
    rows_value = report.get("rows")
    if not isinstance(rows_value, list):
        return ["rows are required to recompute ClaimBench outcomes"]
    rows = [cast(dict[str, Any], row) for row in rows_value if isinstance(row, dict)]
    if len(rows) != len(rows_value):
        issues.append("every ClaimBench row must be an object")
    canonical_report = evaluate_v2_catalog(load_claimbench_v2(repository_root))
    canonical_rows = cast(list[dict[str, Any]], canonical_report["rows"])
    if rows != canonical_rows:
        issues.append("ClaimBench raw rows differ from deterministic recomputation")
    expected_total = _integer(manifest.get("case_count"))
    expected_faithful = _integer(manifest.get("faithful"))
    expected_mutations = _integer(manifest.get("mutations"))
    faithful = [row for row in rows if row.get("kind") == "faithful"]
    mutations = [row for row in rows if row.get("kind") == "mutation"]
    derived_correct = [
        row.get("accepted") == row.get("expected_accept")
        if isinstance(row.get("accepted"), bool)
        and isinstance(row.get("expected_accept"), bool)
        else False
        for row in rows
    ]
    if any(
        row.get("correct") is not expected
        for row, expected in zip(rows, derived_correct, strict=True)
    ):
        issues.append("ClaimBench row correctness fields do not match acceptance decisions")
    correct = sum(derived_correct)
    unsafe = sum(row.get("accepted") is True for row in mutations)
    faithful_rejects = sum(row.get("accepted") is not True for row in faithful)
    if manifest.get("sha256") != file_sha256(repository_root / CLAIMBENCH_V2_RELATIVE):
        issues.append("ClaimBench catalog hash does not match its manifest")
    if expected_total != 332 or len(rows) != expected_total:
        issues.append("ClaimBench must contain exactly 332 executed rows")
    if expected_faithful != 86 or len(faithful) != expected_faithful:
        issues.append("ClaimBench faithful count must be exactly 86")
    if expected_mutations != 246 or len(mutations) != expected_mutations:
        issues.append("ClaimBench mutation count must be exactly 246")
    if report.get("total") != len(rows):
        issues.append("reported total does not match raw rows")
    if report.get("correct") != correct or correct != len(rows):
        issues.append("ClaimBench correctness is not complete")
    expected_unsafe_rate = unsafe / len(mutations) if mutations else 1.0
    expected_reject_rate = faithful_rejects / len(faithful) if faithful else 1.0
    if _number(report.get("unsafe_false_accept_rate")) != expected_unsafe_rate:
        issues.append("unsafe false-accept rate does not match raw rows")
    if expected_unsafe_rate != 0.0:
        issues.append("unsafe false-accept rate exceeds zero")
    if _number(report.get("faithful_false_reject_rate")) != expected_reject_rate:
        issues.append("faithful false-reject rate does not match raw rows")
    if expected_reject_rate != 0.0:
        issues.append("faithful false-reject rate exceeds zero")
    if report.get("always_abstain") is not False:
        issues.append("ClaimBench must not pass through mass abstention")
    incorrect_ids = [
        row.get("id")
        for row, is_correct in zip(rows, derived_correct, strict=True)
        if not is_correct
    ]
    if report.get("incorrect_ids") != incorrect_ids:
        issues.append("incorrect_ids do not match raw rows")
    return issues


def validate_hard_probe_report(
    report: dict[str, Any], *, repository_root: Path = ROOT
) -> list[str]:
    """Require the exact rc2.2 overlay and recompute the declared floor."""

    issues: list[str] = []
    if report.get("schema_version") != "firelens_hard_probe_report.v2":
        issues.append("hard-probe report schema mismatch")
    dataset = load_dataset(
        repository_root / DEFAULT_DATASET.relative_to(ROOT),
        repository_root / DEFAULT_MANIFEST.relative_to(ROOT),
    )
    profile = load_expectation_profile(
        "rc2.2",
        dataset,
        dataset_path=repository_root / DEFAULT_DATASET.relative_to(ROOT),
    )
    expected_effective_sha = canonical_json_sha256(
        effective_expectations_payload(dataset, profile)
    )
    expected_identity = source_identity(repository_root)
    manifest = report.get("manifest")
    summary = report.get("summary")
    results_value = report.get("results")
    if not isinstance(manifest, dict):
        issues.append("hard-probe manifest is missing")
        manifest = {}
    if manifest.get("commit") != expected_identity["commit"]:
        issues.append("hard-probe commit does not match the evaluated source")
    if manifest.get("tree") != expected_identity["tree"]:
        issues.append("hard-probe tree does not match the evaluated source")
    if not isinstance(summary, dict):
        issues.append("hard-probe summary is missing")
        summary = {}
    if not isinstance(results_value, list):
        issues.append("hard-probe results are missing")
        results_value = []
    results = [cast(dict[str, Any], row) for row in results_value if isinstance(row, dict)]
    expected_ids = [case.id for case in dataset.cases]
    expected_priorities = {case.id: case.priority for case in dataset.cases}
    if manifest.get("expectation_profile") != "rc2.2":
        issues.append("hard-probe expectation profile must be rc2.2")
    if manifest.get("expectation_overlay_sha256") != file_sha256(
        repository_root / DEFAULT_RC2_2_EXPECTATIONS.relative_to(ROOT)
    ):
        issues.append("rc2.2 expectation overlay hash mismatch")
    if manifest.get("effective_expectations_sha256") != expected_effective_sha:
        issues.append("effective rc2.2 expectation hash mismatch")
    profile_manifest = _load_mapping(
        repository_root / DEFAULT_RC2_2_EXPECTATIONS_MANIFEST.relative_to(ROOT)
    )
    if profile_manifest.get("profile") != "rc2.2":
        issues.append("rc2.2 expectation manifest profile mismatch")
    if manifest.get("dataset_sha256") != file_sha256(
        repository_root / DEFAULT_DATASET.relative_to(ROOT)
    ):
        issues.append("hard-probe dataset hash mismatch")
    if (
        manifest.get("mode") != "offline"
        or manifest.get("provider_boundary") != "offline_double"
    ):
        issues.append("hard probe did not use the zero-cost offline boundary")
    if [row.get("id") for row in results] != expected_ids:
        issues.append("hard probe did not execute all 105 cases in canonical order")
    if any(
        row.get("priority") != expected_priorities.get(str(row.get("id"))) for row in results
    ):
        issues.append("hard-probe priorities do not match the canonical dataset")
    if any(
        row.get("passed") is not (row.get("failure_reason") in {None, ""}) for row in results
    ):
        issues.append("hard-probe row pass fields do not match failure reasons")
    passed = sum(row.get("passed") is True for row in results)
    failed = len(results) - passed
    critical_failures = [
        str(row.get("id"))
        for row in results
        if row.get("passed") is not True
        and expected_priorities.get(str(row.get("id"))) == "CRITICAL"
    ]
    if summary.get("executed") != 105 or len(results) != 105:
        issues.append("hard-probe executed count must be exactly 105")
    if summary.get("passed") != passed or summary.get("failed") != failed:
        issues.append("hard-probe summary does not match raw rows")
    minimum_passed = _integer(profile_manifest.get("minimum_passed"))
    if summary.get("minimum_passed") != minimum_passed or passed < (minimum_passed or 106):
        issues.append("hard-probe rc2.2 minimum pass floor was not met")
    if summary.get("minimum_passed_met") is not True:
        issues.append("hard-probe minimum_passed_met is not true")
    if critical_failures:
        issues.append(
            "hard-probe contains failed CRITICAL cases: " + ", ".join(critical_failures)
        )
    if _number(summary.get("cost_usd")) != 0.0:
        issues.append("offline hard-probe cost must be zero")
    return issues


def validate_source_aware_report(
    report: dict[str, Any], *, repository_root: Path = ROOT
) -> list[str]:
    issues: list[str] = []
    manifest = _load_mapping(
        repository_root / "data/evaluation/source_aware_conversation.v1.manifest.json"
    )
    expected_identity = source_identity(repository_root)
    results_value = report.get("results")
    results = (
        [cast(dict[str, Any], row) for row in results_value if isinstance(row, dict)]
        if isinstance(results_value, list)
        else []
    )
    metrics = report.get("metrics")
    execution = report.get("execution")
    identity = report.get("artifact_identity")
    if report.get("schema_version") != "firelens.source_aware_conversation.report.v1":
        issues.append("source-aware report schema mismatch")
    if len(results) != manifest.get("total_case_count"):
        issues.append("source-aware case count is incomplete")
    if any(
        row.get("passed")
        is not all(
            value is True for value in cast(dict[str, Any], row.get("checks") or {}).values()
        )
        for row in results
    ):
        issues.append("source-aware row pass fields do not match deterministic checks")
    if report.get("passed") is not True:
        issues.append("source-aware acceptance thresholds were not met")
    if not isinstance(metrics, dict):
        issues.append("source-aware metrics are missing")
    else:
        if metrics.get("failed") != sum(row.get("passed") is not True for row in results):
            issues.append("source-aware failure count does not match raw rows")
        if _integer(metrics.get("tier_a_b_generation_calls")) != 0:
            issues.append("source-aware Tier A/B generation calls exceed zero")
        if _number(metrics.get("tier_a_b_generation_cost_usd")) != 0.0:
            issues.append("source-aware Tier A/B generation cost exceeds zero")
    if not isinstance(execution, dict):
        issues.append("source-aware execution evidence is missing")
    else:
        if _integer(execution.get("external_network_calls")) != 0:
            issues.append("source-aware external network calls exceed zero")
        if _integer(execution.get("external_model_calls")) != 0:
            issues.append("source-aware external model calls exceed zero")
        if execution.get("provider_boundary") != "fake_provider_only":
            issues.append("source-aware provider boundary is not fake_provider_only")
    if not isinstance(identity, dict):
        issues.append("source-aware artifact identity is missing")
    else:
        if identity.get("dataset_sha256") != file_sha256(
            repository_root / "data/evaluation/source_aware_conversation.v1.yaml"
        ):
            issues.append("source-aware dataset hash mismatch")
        if identity.get("dataset_manifest_sha256") != file_sha256(
            repository_root / "data/evaluation/source_aware_conversation.v1.manifest.json"
        ):
            issues.append("source-aware manifest hash mismatch")
        if identity.get("commit") != expected_identity["commit"]:
            issues.append("source-aware commit does not match the evaluated source")
        if identity.get("tree") != expected_identity["tree"]:
            issues.append("source-aware tree does not match the evaluated source")
    return issues


_CORE_COMMAND_ARGUMENTS: dict[str, list[str]] = {
    "productbench_offline": [
        "scripts/run_productbench.py",
        "--mode",
        "offline",
        "--output",
        "OUTPUT",
    ],
    "claimbench_v2": ["scripts/claimbench_v2.py", "evaluate"],
    "hard_probe_rc2_2": [
        "scripts/run_hard_probe.py",
        "--mode",
        "offline",
        "--expectation-profile",
        "rc2.2",
        "--output",
        "OUTPUT",
    ],
    "source_aware_conversation": [
        "scripts/run_source_aware_conversation.py",
        "--output",
        "OUTPUT",
    ],
}
_CORE_MATERIAL_RELATIVES: dict[str, list[str]] = {
    "productbench_offline": [
        "data/evaluation/productbench_journeys_50.json",
        "data/evaluation/productbench_v2.manifest.json",
    ],
    "claimbench_v2": [
        "data/evaluation/claimbench_v1_6_2.yaml",
        "data/evaluation/claimbench_v1_6_2.manifest.json",
    ],
    "hard_probe_rc2_2": [
        "data/evaluation/hard_probe.v1.yaml",
        "data/evaluation/hard_probe.v1.manifest.json",
        "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml",
        "data/evaluation/hard_probe_rc2_2_expectations.v1.manifest.json",
    ],
    "source_aware_conversation": [
        "data/evaluation/source_aware_conversation.v1.yaml",
        "data/evaluation/source_aware_conversation.v1.manifest.json",
    ],
}


def _registered_core_command_is_canonical(command: Any, *, adapter_id: str) -> bool:
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    expected = _CORE_COMMAND_ARGUMENTS.get(adapter_id)
    return bool(
        tokens
        and expected is not None
        and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(tokens[0]).name)
        and tokens[1:] == expected
    )


def _command_matches_core_contract(
    command: Any,
    *,
    adapter_id: str,
    raw_path: Path | None,
    repository_root: Path,
) -> bool:
    """Accept the registered Python command with only its output path expanded."""

    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    expected = _CORE_COMMAND_ARGUMENTS.get(adapter_id)
    if expected is None or not tokens:
        return False
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(tokens[0]).name) is None:
        return False
    observed_arguments = tokens[1:]
    if "OUTPUT" not in expected:
        return observed_arguments == expected
    if raw_path is None or len(observed_arguments) != len(expected):
        return False
    output_index = expected.index("OUTPUT")
    if observed_arguments[:output_index] != expected[:output_index]:
        return False
    if observed_arguments[output_index + 1 :] != expected[output_index + 1 :]:
        return False
    observed_output = Path(observed_arguments[output_index])
    if not observed_output.is_absolute():
        observed_output = repository_root / observed_output
    return observed_output.resolve() == raw_path.resolve()


def _core_report_evidence(
    adapter_id: str,
    report: dict[str, Any],
    *,
    repository_root: Path,
) -> tuple[
    list[str],
    dict[str, int],
    dict[str, Any],
    dict[str, Any] | None,
    list[str],
    str,
]:
    """Recompute normalized adapter evidence from a canonical raw report."""

    expected_cases = {
        "productbench_offline": 31,
        "claimbench_v2": 332,
        "hard_probe_rc2_2": 105,
        "source_aware_conversation": 106,
    }[adapter_id]
    if adapter_id == "productbench_offline":
        validation_issues = validate_productbench_report(
            report, repository_root=repository_root
        )
        rows_value = report.get("results")
        rows = (
            [cast(dict[str, Any], row) for row in rows_value if isinstance(row, dict)]
            if isinstance(rows_value, list)
            else []
        )
        passed = sum(row.get("passed") is True for row in rows)
        failed_case_ids = [str(row.get("id")) for row in rows if row.get("passed") is not True]
        metrics = {
            "execution_complete": report.get("execution_complete"),
            "cost": report.get("cost"),
        }
        materials = _core_report_materials(adapter_id, report)
        failure_class = "product_contract_failure"
    elif adapter_id == "claimbench_v2":
        validation_issues = validate_claimbench_report(report, repository_root=repository_root)
        rows_value = report.get("rows")
        rows = (
            [cast(dict[str, Any], row) for row in rows_value if isinstance(row, dict)]
            if isinstance(rows_value, list)
            else []
        )
        passed = sum(row.get("correct") is True for row in rows)
        failed_case_ids = [str(row.get("id")) for row in rows if row.get("correct") is not True]
        metrics = {
            key: report.get(key)
            for key in (
                "unsafe_false_accept_rate",
                "faithful_false_reject_rate",
                "critical_field_preservation",
                "always_abstain",
            )
        }
        materials = _core_report_materials(adapter_id, report)
        failure_class = "claim_preservation_failure"
    elif adapter_id == "hard_probe_rc2_2":
        validation_issues = validate_hard_probe_report(report, repository_root=repository_root)
        rows_value = report.get("results")
        rows = (
            [cast(dict[str, Any], row) for row in rows_value if isinstance(row, dict)]
            if isinstance(rows_value, list)
            else []
        )
        passed = sum(row.get("passed") is True for row in rows)
        failed_case_ids = [str(row.get("id")) for row in rows if row.get("passed") is not True]
        summary = report.get("summary")
        raw_summary = cast(dict[str, Any], summary) if isinstance(summary, dict) else {}
        metrics = {
            "minimum_passed": raw_summary.get("minimum_passed"),
            "minimum_passed_met": raw_summary.get("minimum_passed_met"),
            "cost_usd": raw_summary.get("cost_usd"),
        }
        materials = _core_report_materials(adapter_id, report)
        failure_class = "hard_probe_case_failure_within_profile"
    else:
        validation_issues = validate_source_aware_report(
            report, repository_root=repository_root
        )
        rows_value = report.get("results")
        rows = (
            [cast(dict[str, Any], row) for row in rows_value if isinstance(row, dict)]
            if isinstance(rows_value, list)
            else []
        )
        passed = sum(row.get("passed") is True for row in rows)
        failed_case_ids = [str(row.get("id")) for row in rows if row.get("passed") is not True]
        raw_metrics = report.get("metrics")
        metrics = cast(dict[str, Any], raw_metrics) if isinstance(raw_metrics, dict) else {}
        materials = _core_report_materials(adapter_id, report)
        failure_class = "source_aware_contract_failure"
    executed = len(rows)
    counts = {
        "expected": expected_cases,
        "executed": executed,
        "passed": passed,
        "failed": executed - passed,
        "not_run": max(0, expected_cases - executed),
    }
    return (
        validation_issues,
        counts,
        metrics,
        materials,
        failed_case_ids,
        failure_class,
    )


def _core_report_materials(adapter_id: str, report: dict[str, Any]) -> dict[str, Any] | None:
    identity_field = {
        "productbench_offline": "identity",
        "claimbench_v2": "identity",
        "hard_probe_rc2_2": "manifest",
        "source_aware_conversation": "artifact_identity",
    }[adapter_id]
    raw_materials = report.get(identity_field)
    if not isinstance(raw_materials, dict):
        return None
    materials = dict(raw_materials)
    if adapter_id == "source_aware_conversation":
        # The offline fixture creates its vector manifest with a wall-clock
        # timestamp and deletes that temporary file after execution.  Its file
        # hash therefore cannot be replayed or independently verified.  Do not
        # present it as a durable material binding; the deterministic matrix,
        # corpus, dataset, manifests, registry and runner hashes remain bound.
        materials.pop("vector_manifest_sha256", None)
    return materials


def _semantic_report_projection(adapter_id: str, value: Any) -> Any:
    """Remove only run-volatile values before deterministic replay comparison."""

    volatile_value_keys = {
        "generated_at",
        "latency_ms",
        "trace_id",
        "elapsed_seconds",
    }
    if isinstance(value, dict):
        projected = {
            str(key): f"<RUN_VOLATILE:{key}>"
            if str(key) in volatile_value_keys
            else _semantic_report_projection(adapter_id, item)
            for key, item in value.items()
            if not (adapter_id == "productbench_offline" and str(key) == "response_sha256")
        }
        if adapter_id == "source_aware_conversation" and "artifact_identity" in projected:
            identity = projected["artifact_identity"]
            if isinstance(identity, dict) and "vector_manifest_sha256" in identity:
                identity["vector_manifest_sha256"] = "<RUN_VOLATILE:vector_manifest_sha256>"
        return projected
    if isinstance(value, list):
        return [_semantic_report_projection(adapter_id, item) for item in value]
    if adapter_id == "hard_probe_rc2_2" and isinstance(value, str):
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            value,
        ):
            return "<RUN_TIMESTAMP>"
        return re.sub(r"\b\d{1,2}:\d{2} [ap]\.m\. [A-Z]{3}\b", "<RUN_TIME>", value)
    return value


@functools.lru_cache(maxsize=16)
def _replay_core_report(
    adapter_id: str,
    repository_root_string: str,
    working_tree_sha256: str,
) -> dict[str, Any]:
    """Execute a zero-cost deterministic adapter for semantic attestation."""

    del working_tree_sha256  # It is the cache key binding the replay to source bytes.
    repository_root = Path(repository_root_string).resolve()
    with tempfile.TemporaryDirectory(prefix="firelens-eval-replay-") as temporary:
        output = Path(temporary) / f"{adapter_id}.json"
        if repository_root != ROOT.resolve():
            python_path = os.pathsep.join((str(repository_root / "src"), str(repository_root)))
            environment = {**os.environ, "PYTHONPATH": python_path}
            if adapter_id == "productbench_offline":
                command = [
                    sys.executable,
                    "scripts/run_productbench.py",
                    "--mode",
                    "offline",
                    "--output",
                    str(output),
                ]
            elif adapter_id == "hard_probe_rc2_2":
                command = [
                    sys.executable,
                    "scripts/run_hard_probe.py",
                    "--mode",
                    "offline",
                    "--expectation-profile",
                    "rc2.2",
                    "--output",
                    str(output),
                ]
            elif adapter_id == "source_aware_conversation":
                command = [
                    sys.executable,
                    "scripts/run_source_aware_conversation.py",
                    "--output",
                    str(output),
                ]
            elif adapter_id == "claimbench_v2":
                program = """
import json
import subprocess
from pathlib import Path
from firelens.evaluation.claimbench_v2 import (
    CLAIMBENCH_V2_RELATIVE,
    MANIFEST_V2_RELATIVE,
    evaluate_v2_catalog,
    load_claimbench_v2,
)
from firelens.evaluation.common import file_sha256

root = Path.cwd()
report = evaluate_v2_catalog(load_claimbench_v2(root))
report["schema_version"] = "firelens.claimbench_v2_report.v1"
report["identity"] = {
    "catalog": {
        "path": CLAIMBENCH_V2_RELATIVE,
        "sha256": file_sha256(root / CLAIMBENCH_V2_RELATIVE),
    },
    "manifest": {
        "path": MANIFEST_V2_RELATIVE,
        "sha256": file_sha256(root / MANIFEST_V2_RELATIVE),
    },
    "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip(),
    "tree": subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True
    ).strip(),
}
Path(__import__("sys").argv[1]).write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
)
"""
                command = [sys.executable, "-c", program, str(output)]
            else:
                raise ValueError(f"adapter {adapter_id} has no semantic replay")
            completed = subprocess.run(
                command,
                cwd=repository_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            if not output.is_file():
                detail = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(f"historical replay exited {completed.returncode}: {detail}")
            return _load_mapping(output)
        console = io.StringIO()
        if adapter_id == "productbench_offline":
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                productbench_v2.main(["--mode", "offline", "--output", str(output)])
        elif adapter_id == "hard_probe_rc2_2":
            args = hard_probe_cli.parse_args(
                [
                    "--mode",
                    "offline",
                    "--expectation-profile",
                    "rc2.2",
                    "--dataset",
                    str(repository_root / DEFAULT_DATASET.relative_to(ROOT)),
                    "--manifest",
                    str(repository_root / DEFAULT_MANIFEST.relative_to(ROOT)),
                    "--output",
                    str(output),
                ]
            )
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                asyncio.run(hard_probe_cli.run(args))
        elif adapter_id == "source_aware_conversation":
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                run_source_aware(output, root=repository_root)
        elif adapter_id == "claimbench_v2":
            report = evaluate_v2_catalog(load_claimbench_v2(repository_root))
            report["schema_version"] = "firelens.claimbench_v2_report.v1"
            report["identity"] = {
                "catalog": catalog_v2_identity(repository_root),
                "manifest": {
                    "path": MANIFEST_V2_RELATIVE,
                    "sha256": file_sha256(repository_root / MANIFEST_V2_RELATIVE),
                },
                "commit": _git_value(repository_root, "rev-parse", "HEAD"),
                "tree": _git_value(repository_root, "rev-parse", "HEAD^{tree}"),
            }
            _write_json(output, report)
        else:
            raise ValueError(f"adapter {adapter_id} has no semantic replay")
        return _load_mapping(output)


def _validation_failures(
    context: RunContext,
    *,
    adapter_id: str,
    oracle: str,
    command: str,
    issues: list[str],
) -> list[dict[str, Any]]:
    return [
        _new_failure(
            context,
            suite="core",
            adapter_id=adapter_id,
            case_id=None,
            status="FAIL",
            failure_class="report_contract_violation",
            severity="HIGH",
            oracle=oracle,
            summary=issue,
            expected="complete identity-bound report satisfying the registered oracle",
            observed=issue,
            evidence=[],
            first_divergent_layer="evaluation_gate"
            if adapter_id == "hard_probe_rc2_2"
            else "evaluation_adapter",
            reproduction=[command],
        )
        for issue in issues
    ]


def _blocked_adapter(
    context: RunContext,
    *,
    suite: str,
    definition: dict[str, Any],
    exception: Exception | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter_id = str(definition["id"])
    declared = str(definition.get("status"))
    status: Literal["BLOCKED", "NOT_RUN"] = "NOT_RUN" if declared == "NOT_RUN" else "BLOCKED"
    reason = str(definition.get("reason") or exception or "adapter was not executed")
    if exception is not None:
        status = "BLOCKED"
        reason = f"{type(exception).__name__}: {exception}"
    command = str(definition.get("command") or "")
    failure = _new_failure(
        context,
        suite=suite,
        adapter_id=adapter_id,
        case_id=None,
        status=status,
        failure_class="runner_unavailable"
        if exception is not None
        else "evidence_not_executed",
        severity="HIGH" if status == "BLOCKED" else "MEDIUM",
        oracle=str(definition["oracle"]),
        summary=reason,
        expected="an explicitly authorized, identity-bound executable adapter",
        observed=status,
        evidence=[str(item) for item in cast(list[Any], definition.get("materials") or [])],
        first_divergent_layer="evaluation_availability",
        reproduction=[command] if command else [],
    )
    adapter = _adapter_result(
        context,
        adapter_id,
        status=status,
        command=command,
        raw_artifact=None,
        case_counts={"expected": 0, "executed": 0, "passed": 0, "failed": 0, "not_run": 1},
        metrics={},
        materials={
            item: file_sha256(context.root / item)
            for item in cast(list[str], definition.get("materials") or [])
            if (context.root / item).is_file()
        },
        failures=[failure],
        limitations=[reason],
        started_at=context.started_at,
    )
    return adapter, [failure]


def _run_productbench(context: RunContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter_id = "productbench_offline"
    started = _utc_now()
    raw = context.run_dir / "raw/productbench_offline.json"
    command = f"{sys.executable} scripts/run_productbench.py --mode offline --output {raw}"
    try:
        console = io.StringIO()
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
            exit_code = productbench_v2.main(["--mode", "offline", "--output", str(raw)])
        (context.run_dir / "raw/productbench_offline.stdout.log").write_text(
            console.getvalue(), encoding="utf-8"
        )
        report = _load_mapping(raw)
        for row in cast(list[Any], report.get("results") or []):
            if not isinstance(row, dict):
                continue
            trace = row.get("trace")
            if isinstance(trace, dict):
                # This digest includes a random trace ID in its unavailable
                # preimage, so it cannot be independently replayed.  Do not
                # retain a hash-looking value that EvalLab cannot authenticate.
                trace.pop("response_sha256", None)
        _write_json(raw, report)
        issues = validate_productbench_report(report, repository_root=context.root)
        if exit_code != 0 and not issues:
            issues.append(f"runner exited {exit_code} without a reported contract failure")
        failures = _validation_failures(
            context,
            adapter_id=adapter_id,
            oracle="deterministic_executable",
            command=command,
            issues=issues,
        )
        for row in cast(list[Any], report.get("results") or []):
            if not isinstance(row, dict) or row.get("passed") is True:
                continue
            failures.append(
                _new_failure(
                    context,
                    suite="core",
                    adapter_id=adapter_id,
                    case_id=str(row.get("id")),
                    status="FAIL",
                    failure_class="product_contract_failure",
                    severity="HIGH",
                    oracle="deterministic_executable",
                    summary="; ".join(
                        str(item) for item in cast(list[Any], row.get("issues") or [])
                    )
                    or "case failed",
                    expected=row.get("contract"),
                    observed={"issues": row.get("issues"), "trace": row.get("trace")},
                    evidence=[str(raw)],
                    first_divergent_layer="product_contract",
                    reproduction=[command],
                )
            )
        status: Status = "PASS" if not issues and exit_code == 0 else "FAIL"
        adapter = _adapter_result(
            context,
            adapter_id,
            status=status,
            command=command,
            raw_artifact=str(raw.relative_to(context.run_dir)),
            case_counts={
                "expected": 31,
                "executed": int(report.get("case_count") or 0),
                "passed": int(report.get("passed") or 0),
                "failed": int(report.get("failed") or 0),
                "not_run": max(0, 31 - int(report.get("case_count") or 0)),
            },
            metrics={
                "execution_complete": report.get("execution_complete"),
                "cost": report.get("cost"),
            },
            materials=cast(dict[str, Any], report.get("identity") or {}),
            failures=failures,
            limitations=["Development-unsealed; not independent semantic or release evidence."],
            started_at=started,
        )
        return adapter, failures
    except Exception as exc:  # noqa: BLE001
        return _blocked_adapter(
            context,
            suite="core",
            definition=_adapter_definition(context, adapter_id),
            exception=exc,
        )


def _run_claimbench(context: RunContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter_id = "claimbench_v2"
    started = _utc_now()
    raw = context.run_dir / "raw/claimbench_v2.json"
    command = f"{sys.executable} scripts/claimbench_v2.py evaluate"
    try:
        catalog = load_claimbench_v2(context.root)
        report = evaluate_v2_catalog(catalog)
        report["schema_version"] = "firelens.claimbench_v2_report.v1"
        report["identity"] = {
            "catalog": catalog_v2_identity(context.root),
            "manifest": {
                "path": MANIFEST_V2_RELATIVE,
                "sha256": file_sha256(context.root / MANIFEST_V2_RELATIVE),
            },
            "commit": context.identity.get("commit"),
            "tree": context.identity.get("tree"),
        }
        _write_json(raw, report)
        issues = validate_claimbench_report(report, repository_root=context.root)
        failures = _validation_failures(
            context,
            adapter_id=adapter_id,
            oracle="deterministic_executable",
            command=command,
            issues=issues,
        )
        for row in cast(list[Any], report["rows"]):
            if not isinstance(row, dict) or row.get("correct") is True:
                continue
            failures.append(
                _new_failure(
                    context,
                    suite="core",
                    adapter_id=adapter_id,
                    case_id=str(row.get("id")),
                    status="FAIL",
                    failure_class="claim_preservation_failure",
                    severity="CRITICAL"
                    if row.get("kind") == "mutation" and row.get("accepted")
                    else "HIGH",
                    oracle="deterministic_executable",
                    summary="ClaimBench expected acceptance decision was not preserved.",
                    expected={"accepted": row.get("expected_accept")},
                    observed={"accepted": row.get("accepted"), "errors": row.get("errors")},
                    evidence=[str(raw)],
                    first_divergent_layer="semantic_invariants",
                    reproduction=[command],
                )
            )
        status: Status = "PASS" if not issues else "FAIL"
        adapter = _adapter_result(
            context,
            adapter_id,
            status=status,
            command=command,
            raw_artifact=str(raw.relative_to(context.run_dir)),
            case_counts={
                "expected": 332,
                "executed": int(report["total"]),
                "passed": int(report["correct"]),
                "failed": int(report["total"]) - int(report["correct"]),
                "not_run": max(0, 332 - int(report["total"])),
            },
            metrics={
                key: report[key]
                for key in (
                    "unsafe_false_accept_rate",
                    "faithful_false_reject_rate",
                    "critical_field_preservation",
                    "always_abstain",
                )
            },
            materials=cast(dict[str, Any], report["identity"]),
            failures=failures,
            limitations=[
                "Deterministic checker evidence; independent examiner cases remain required."
            ],
            started_at=started,
        )
        return adapter, failures
    except Exception as exc:  # noqa: BLE001
        return _blocked_adapter(
            context,
            suite="core",
            definition=_adapter_definition(context, adapter_id),
            exception=exc,
        )


def _run_hard_probe(context: RunContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter_id = "hard_probe_rc2_2"
    started = _utc_now()
    raw = context.run_dir / "raw/hard_probe_rc2_2.json"
    command = (
        f"{sys.executable} scripts/run_hard_probe.py --mode offline "
        f"--expectation-profile rc2.2 --output {raw}"
    )
    try:
        args = hard_probe_cli.parse_args(
            [
                "--mode",
                "offline",
                "--expectation-profile",
                "rc2.2",
                "--output",
                str(raw),
            ]
        )
        console = io.StringIO()
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
            exit_code = asyncio.run(hard_probe_cli.run(args))
        (context.run_dir / "raw/hard_probe_rc2_2.stdout.log").write_text(
            console.getvalue(), encoding="utf-8"
        )
        report = _load_mapping(raw)
        issues = validate_hard_probe_report(report, repository_root=context.root)
        if exit_code != 0 and not issues:
            issues.append(f"runner exited {exit_code} without a reported contract failure")
        failures = _validation_failures(
            context,
            adapter_id=adapter_id,
            oracle="deterministic_executable",
            command=command,
            issues=issues,
        )
        for row in cast(list[Any], report.get("results") or []):
            if not isinstance(row, dict) or row.get("passed") is True:
                continue
            priority = str(row.get("priority") or "HIGH")
            severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = (
                "CRITICAL"
                if priority == "CRITICAL"
                else "HIGH"
                if priority == "HIGH"
                else "MEDIUM"
            )
            failures.append(
                _new_failure(
                    context,
                    suite="core",
                    adapter_id=adapter_id,
                    case_id=str(row.get("id")),
                    status="FAIL",
                    failure_class="hard_probe_case_failure_within_profile",
                    severity=severity,
                    oracle="deterministic_executable",
                    summary=str(row.get("failure_reason") or "hard-probe case failed"),
                    expected={
                        "text": row.get("expected"),
                        "allowed_modes": row.get("effective_allowed_modes"),
                    },
                    observed={
                        "response_mode": row.get("response_mode"),
                        "status": row.get("status"),
                        "semantic_checks": row.get("semantic_checks"),
                    },
                    evidence=[str(raw)],
                    first_divergent_layer="evaluation_contract",
                    reproduction=[command],
                    input_record={
                        "question": row.get("question"),
                        "history": row.get("history"),
                        "location_context": row.get("location") or row.get("context"),
                    },
                    lifecycle_status="review",
                    first_divergence_owner=(
                        "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml"
                    ),
                    first_divergence_confidence="suspected",
                )
            )
        status: Status = "PASS" if not issues and exit_code == 0 else "FAIL"
        summary = cast(dict[str, Any], report.get("summary") or {})
        adapter = _adapter_result(
            context,
            adapter_id,
            status=status,
            command=command,
            raw_artifact=str(raw.relative_to(context.run_dir)),
            case_counts={
                "expected": 105,
                "executed": int(summary.get("executed") or 0),
                "passed": int(summary.get("passed") or 0),
                "failed": int(summary.get("failed") or 0),
                "not_run": max(0, 105 - int(summary.get("executed") or 0)),
            },
            metrics={
                "minimum_passed": summary.get("minimum_passed"),
                "minimum_passed_met": summary.get("minimum_passed_met"),
                "cost_usd": summary.get("cost_usd"),
            },
            materials=cast(dict[str, Any], report.get("manifest") or {}),
            failures=failures,
            limitations=[
                "Profile pass uses its declared 86/105 floor; individual failures remain explicit.",
                "Referenced browser and fixture cases are not executed by this runner.",
            ],
            started_at=started,
        )
        return adapter, failures
    except Exception as exc:  # noqa: BLE001
        return _blocked_adapter(
            context,
            suite="core",
            definition=_adapter_definition(context, adapter_id),
            exception=exc,
        )


def _run_source_aware(context: RunContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter_id = "source_aware_conversation"
    started = _utc_now()
    raw = context.run_dir / "raw/source_aware_conversation.json"
    command = f"{sys.executable} scripts/run_source_aware_conversation.py --output {raw}"
    try:
        exit_code = run_source_aware(raw, root=context.root)
        report = _load_mapping(raw)
        issues = validate_source_aware_report(report, repository_root=context.root)
        if exit_code != 0 and not issues:
            issues.append(f"runner exited {exit_code} without a reported contract failure")
        failures = _validation_failures(
            context,
            adapter_id=adapter_id,
            oracle="deterministic_executable",
            command=command,
            issues=issues,
        )
        for row in cast(list[Any], report.get("results") or []):
            if not isinstance(row, dict) or row.get("passed") is True:
                continue
            checks = cast(dict[str, Any], row.get("checks") or {})
            failed_checks = sorted(key for key, passed in checks.items() if passed is not True)
            failures.append(
                _new_failure(
                    context,
                    suite="core",
                    adapter_id=adapter_id,
                    case_id=str(row.get("id")),
                    status="FAIL",
                    failure_class="source_aware_contract_failure",
                    severity="HIGH",
                    oracle="deterministic_executable",
                    summary="failed checks: " + ", ".join(failed_checks),
                    expected={
                        "mode": row.get("expected_mode"),
                        "source_lane": row.get("expected_source_lane"),
                    },
                    observed={
                        "mode": row.get("response_mode"),
                        "source_lane": row.get("source_lane"),
                        "checks": checks,
                    },
                    evidence=[str(raw)],
                    first_divergent_layer="source_aware_contract",
                    reproduction=[command],
                    input_record={
                        "question": row.get("question"),
                        "history": row.get("history"),
                        "location_context": row.get("location") or row.get("context"),
                    },
                )
            )
        status: Status = "PASS" if not issues and exit_code == 0 else "FAIL"
        metrics = cast(dict[str, Any], report.get("metrics") or {})
        case_counts = cast(dict[str, Any], report.get("case_counts") or {})
        adapter = _adapter_result(
            context,
            adapter_id,
            status=status,
            command=command,
            raw_artifact=str(raw.relative_to(context.run_dir)),
            case_counts={
                "expected": 106,
                "executed": int(case_counts.get("total") or 0),
                "passed": int(metrics.get("passed") or 0),
                "failed": int(metrics.get("failed") or 0),
                "not_run": max(0, 106 - int(case_counts.get("total") or 0)),
            },
            metrics=metrics,
            materials=_core_report_materials(adapter_id, report) or {},
            failures=failures,
            limitations=[
                "Development-unsealed with pending owner review.",
                "This is not general multi-turn trajectory or deployed-provider qualification.",
            ],
            started_at=started,
        )
        return adapter, failures
    except Exception as exc:  # noqa: BLE001
        return _blocked_adapter(
            context,
            suite="core",
            definition=_adapter_definition(context, adapter_id),
            exception=exc,
        )


def _status_from(adapters: list[dict[str, Any]], failures: list[dict[str, Any]]) -> Status:
    statuses = {str(adapter.get("status")) for adapter in adapters}
    run_blockers = {
        str(failure.get("run_status"))
        for failure in failures
        if failure.get("adapter_id") == "eval_lab_identity"
    }
    # A source-identity blocker invalidates the authority of every adapter
    # result.  Preserve the rows as evidence, but never let an adapter FAIL
    # make the overall run look like a valid evaluation of a stable source.
    if "BLOCKED" in run_blockers:
        return "BLOCKED"
    statuses.update(run_blockers)
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "NOT_RUN" in statuses:
        return "NOT_RUN"
    if statuses == {"PASS"}:
        return "PASS"
    return "BLOCKED"


def validate_run_envelope(
    envelope: dict[str, Any],
    *,
    envelope_path: Path | None = None,
    repository_root: Path = ROOT,
    historical_source: bool = False,
) -> list[str]:
    """Reject incomplete, incoherent, stale-bound, or tampered EvalLab evidence."""

    issues: list[str] = []
    required = {
        "schema_version",
        "run_id",
        "suite",
        "status",
        "qualification_role",
        "started_at",
        "finished_at",
        "identity",
        "bindings",
        "execution",
        "adapters",
        "summary",
        "failures",
        "limitations",
    }
    missing = sorted(required - set(envelope))
    if missing:
        issues.append("envelope is missing: " + ", ".join(missing))
    if envelope.get("schema_version") != RUN_SCHEMA_VERSION:
        issues.append("run schema_version is invalid")
    suite = envelope.get("suite")
    if suite not in SUITES:
        issues.append("suite is outside the EvalLab registry")
        return issues
    if envelope.get("status") not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}:
        issues.append("run status is outside the schema enum")
    run_identity_value = envelope.get("identity")
    source_changed = (
        isinstance(run_identity_value, dict)
        and run_identity_value.get("changed_during_run") is True
    )
    registry = load_registry(repository_root)
    suite_definition = cast(dict[str, Any], cast(dict[str, Any], registry["suites"])[suite])
    if envelope.get("qualification_role") != suite_definition.get("qualification_role"):
        issues.append("run qualification role disagrees with registry")
    policy = load_policy(repository_root)
    expected_execution = {
        "network_allowed": policy["network_allowed"],
        "provider_calls_allowed": policy["provider_calls_allowed"],
        "cost_ceiling_usd": 0.0,
    }
    if envelope.get("execution") != expected_execution:
        issues.append("run execution boundary disagrees with zero-cost policy")
    adapter_definitions = cast(list[dict[str, Any]], suite_definition["adapters"])
    expected_adapter_ids = [str(item["id"]) for item in adapter_definitions]
    definitions_by_id = {str(item["id"]): item for item in adapter_definitions}
    adapters_value = envelope.get("adapters")
    adapters = (
        [cast(dict[str, Any], item) for item in adapters_value if isinstance(item, dict)]
        if isinstance(adapters_value, list)
        else []
    )
    if not isinstance(adapters_value, list) or len(adapters) != len(adapters_value):
        issues.append("adapters is not an object array")
    adapter_ids = [str(item.get("adapter_id")) for item in adapters]
    if adapter_ids != expected_adapter_ids:
        issues.append("adapter IDs do not exactly match the registered suite")

    expected_evaluator = evaluation_source_identity(repository_root)
    current_source_identity = source_identity(repository_root)
    failures_value = envelope.get("failures")
    failures = (
        [cast(dict[str, Any], item) for item in failures_value if isinstance(item, dict)]
        if isinstance(failures_value, list)
        else []
    )
    if not isinstance(failures_value, list) or len(failures) != len(failures_value):
        issues.append("failures is not an object array")
    failure_ids = [str(item.get("failure_id")) for item in failures]
    if len(failure_ids) != len(set(failure_ids)):
        issues.append("failure IDs are not unique")
    for failure in failures:
        failure_core = {
            key: failure.get(key)
            for key in (
                "run_id",
                "suite",
                "adapter_id",
                "case_id",
                "status",
                "run_status",
                "fixed_in_sha",
                "failure_class",
                "family",
                "summary",
                "input",
                "expected",
                "observed",
            )
        }
        if failure.get("failure_id") != "ELF-" + _canonical_sha256(failure_core)[:16]:
            issues.append(f"failure {failure.get('failure_id')} content hash is invalid")
        issues.extend(
            f"failure {failure.get('failure_id')}: {item}"
            for item in validate_failure_record(failure, repository_root=repository_root)
        )
        if failure.get("run_id") != envelope.get("run_id"):
            issues.append(f"failure {failure.get('failure_id')} belongs to another run")
        if failure.get("suite") != suite:
            issues.append(f"failure {failure.get('failure_id')} belongs to another suite")
        run_identity = envelope.get("identity")
        failure_identity = failure.get("identity")
        if isinstance(run_identity, dict) and isinstance(failure_identity, dict):
            for field in ("commit", "tree", "dirty", "application_sha"):
                if failure_identity.get(field) != run_identity.get(field):
                    issues.append(
                        f"failure {failure.get('failure_id')} {field} disagrees with run identity"
                    )
        if isinstance(run_identity, dict) and failure.get(
            "application_sha"
        ) != run_identity.get("application_sha"):
            issues.append(
                f"failure {failure.get('failure_id')} application SHA disagrees with run identity"
            )

    run_dir = envelope_path.resolve().parent if envelope_path is not None else None
    for adapter in adapters:
        adapter_id = str(adapter.get("adapter_id"))
        definition = definitions_by_id.get(adapter_id)
        adapter_required = {
            "adapter_id",
            "status",
            "classification",
            "oracle",
            "command",
            "started_at",
            "finished_at",
            "raw_artifact",
            "raw_artifact_sha256",
            "evaluator",
            "case_counts",
            "metrics",
            "materials",
            "failure_ids",
            "limitations",
        }
        missing_adapter = sorted(adapter_required - set(adapter))
        if missing_adapter:
            issues.append(f"adapter {adapter_id} is missing: " + ", ".join(missing_adapter))
        status = adapter.get("status")
        if status not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}:
            issues.append(f"adapter {adapter_id} has an invalid status")
        if definition is not None:
            if adapter.get("classification") != definition.get("classification"):
                issues.append(f"adapter {adapter_id} classification disagrees with registry")
            if adapter.get("oracle") != definition.get("oracle"):
                issues.append(f"adapter {adapter_id} oracle disagrees with registry")
            if suite == "core" and (
                definition.get("classification") != "ACTIVE"
                or definition.get("oracle") != "deterministic_executable"
            ):
                issues.append(f"adapter {adapter_id} core registry authority is invalid")
            if suite == "core" and not _registered_core_command_is_canonical(
                definition.get("command"), adapter_id=adapter_id
            ):
                issues.append(f"adapter {adapter_id} registered command is not canonical")
            if suite == "core" and definition.get("materials") != _CORE_MATERIAL_RELATIVES.get(
                adapter_id
            ):
                issues.append(f"adapter {adapter_id} registered materials are not canonical")
        counts = adapter.get("case_counts")
        expected_count_keys = {"expected", "executed", "passed", "failed", "not_run"}
        if not isinstance(counts, dict) or set(counts) != expected_count_keys:
            issues.append(f"adapter {adapter_id} has invalid case counts")
            counts = {}
        elif any(
            not isinstance(counts[key], int) or isinstance(counts[key], bool) or counts[key] < 0
            for key in expected_count_keys
        ):
            issues.append(f"adapter {adapter_id} has non-integer or negative case counts")
        else:
            if counts["executed"] != counts["passed"] + counts["failed"]:
                issues.append(f"adapter {adapter_id} executed count is incoherent")
            if status in {"PASS", "FAIL"} and (
                counts["expected"] != counts["executed"] + counts["not_run"]
            ):
                issues.append(f"adapter {adapter_id} expected count is incoherent")
            pass_may_retain_case_failures = suite == "core" and adapter_id == "hard_probe_rc2_2"
            if status == "PASS" and (
                counts["not_run"] or (counts["failed"] and not pass_may_retain_case_failures)
            ):
                issues.append(f"adapter {adapter_id} claims PASS with incomplete/failing cases")
        adapter_failure_ids = adapter.get("failure_ids")
        expected_failure_ids = [
            str(item["failure_id"]) for item in failures if item.get("adapter_id") == adapter_id
        ]
        if adapter_failure_ids != expected_failure_ids:
            issues.append(f"adapter {adapter_id} failure IDs disagree with run failures")
        if status == "PASS" and expected_failure_ids and suite != "core":
            issues.append(f"adapter {adapter_id} claims PASS with failure records")
        if status in {"FAIL", "BLOCKED", "NOT_RUN"} and not expected_failure_ids:
            issues.append(f"adapter {adapter_id} has no failure record for {status}")
        if source_changed:
            evaluator = adapter.get("evaluator")
            if (
                not isinstance(evaluator, dict)
                or re.fullmatch(r"[0-9a-f]{64}", str(evaluator.get("sha256") or "")) is None
                or not isinstance(evaluator.get("files"), dict)
            ):
                issues.append(f"adapter {adapter_id} evaluator binding is malformed")
        elif adapter.get("evaluator") != expected_evaluator:
            issues.append(f"adapter {adapter_id} evaluator binding is stale or missing")
        if not isinstance(adapter.get("materials"), dict):
            issues.append(f"adapter {adapter_id} materials are not an object")
        raw_relative = adapter.get("raw_artifact")
        raw_sha = adapter.get("raw_artifact_sha256")
        raw_path: Path | None = None
        if raw_relative is None:
            if raw_sha is not None:
                issues.append(f"adapter {adapter_id} has a raw hash without an artifact")
            if status in {"PASS", "FAIL"}:
                issues.append(f"adapter {adapter_id} has no raw artifact")
        elif (
            not isinstance(raw_relative, str)
            or re.fullmatch(r"[0-9a-f]{64}", str(raw_sha)) is None
        ):
            issues.append(f"adapter {adapter_id} raw artifact binding is malformed")
        elif run_dir is not None:
            raw_path = (run_dir / raw_relative).resolve()
            try:
                raw_path.relative_to(run_dir)
            except ValueError:
                issues.append(f"adapter {adapter_id} raw artifact escapes its run directory")
                raw_path = None
            else:
                if not raw_path.is_file():
                    issues.append(f"adapter {adapter_id} raw artifact is missing")
                elif file_sha256(raw_path) != raw_sha:
                    issues.append(f"adapter {adapter_id} raw artifact hash does not match")
        local_definition = (
            local_adapters.definitions(repository_root).get(adapter_id)
            if suite != "core"
            else None
        )
        if local_definition is not None:
            if adapter.get("command") != local_adapters.canonical_command(local_definition):
                issues.append(f"adapter {adapter_id} command is not canonical")
            if raw_path is None or run_dir is None or not raw_path.is_file():
                issues.append(f"adapter {adapter_id} local raw evidence is unavailable")
            else:
                report = _load_mapping(raw_path)
                raw_issues = local_adapters.validate(
                    report, repository_root, run_dir, local_definition
                )
                raw_rows = report.get("rows", [])
                expected_counts = local_adapters.counts(
                    raw_rows, len(local_definition["expected_ids"])
                )
                expected_status = (
                    "BLOCKED" if raw_issues else "FAIL" if expected_counts["failed"] else "PASS"
                )
                if status != expected_status or counts != expected_counts:
                    issues.append(
                        f"adapter {adapter_id} status/counts disagree with native results"
                    )
                if adapter.get("materials") != report.get("materials"):
                    issues.append(f"adapter {adapter_id} raw material mismatch")
                expected_failed = [row["id"] for row in raw_rows if row["outcome"] == "failed"]
                actual_failed = [
                    failure.get("case_id")
                    for failure in failures
                    if failure.get("adapter_id") == adapter_id
                    and failure.get("run_status") == "FAIL"
                ]
                if actual_failed != expected_failed:
                    issues.append(f"adapter {adapter_id} failed case reconciliation mismatch")
                actual_problems = [
                    failure.get("observed", {}).get("structured_state", {}).get("issues")
                    for failure in failures
                    if failure.get("adapter_id") == adapter_id
                    and failure.get("run_status") == "BLOCKED"
                ]
                if actual_problems != ([raw_issues] if raw_issues else []):
                    issues.append(f"adapter {adapter_id} harness issue reconciliation mismatch")
                if report.get("identity") != {
                    key: envelope["identity"][key]
                    for key in ("commit", "tree", "application_sha")
                }:
                    issues.append(f"adapter {adapter_id} raw source identity mismatch")
        if suite == "core" and definition is not None:
            expected_raw_relative = f"raw/{adapter_id}.json"
            if status in {"PASS", "FAIL"} and raw_relative != expected_raw_relative:
                issues.append(f"adapter {adapter_id} raw artifact path is not canonical")
            if status in {"PASS", "FAIL"} and not _command_matches_core_contract(
                adapter.get("command"),
                adapter_id=adapter_id,
                raw_path=raw_path,
                repository_root=repository_root,
            ):
                issues.append(f"adapter {adapter_id} command does not match its core contract")
            elif status in {"BLOCKED", "NOT_RUN"} and adapter.get("command") != definition.get(
                "command"
            ):
                issues.append(f"adapter {adapter_id} blocked command disagrees with registry")
            raw_is_bound = bool(
                raw_path is not None
                and raw_path.is_file()
                and isinstance(raw_sha, str)
                and file_sha256(raw_path) == raw_sha
            )
            if status in {"PASS", "FAIL"} and run_dir is None:
                issues.append(
                    f"adapter {adapter_id} raw evidence cannot be verified without an envelope path"
                )
            if status in {"PASS", "FAIL"} and raw_is_bound:
                try:
                    raw_report = _load_mapping(cast(Path, raw_path))
                except Exception as exc:  # noqa: BLE001
                    issues.append(
                        f"adapter {adapter_id} raw evidence could not be loaded: "
                        f"{type(exc).__name__}: {exc}"
                    )
                else:
                    if adapter_id == "productbench_offline" and any(
                        isinstance(row, dict)
                        and isinstance(row.get("trace"), dict)
                        and "response_sha256" in cast(dict[str, Any], row["trace"])
                        for row in cast(list[Any], raw_report.get("results") or [])
                    ):
                        issues.append(
                            "adapter productbench_offline raw report claims an "
                            "unsupported volatile response SHA"
                        )
                    report_identity_field = {
                        "productbench_offline": "identity",
                        "claimbench_v2": "identity",
                        "hard_probe_rc2_2": "manifest",
                        "source_aware_conversation": "artifact_identity",
                    }[adapter_id]
                    report_identity = raw_report.get(report_identity_field)
                    run_identity = envelope.get("identity")
                    if not isinstance(report_identity, dict) or not isinstance(
                        run_identity, dict
                    ):
                        issues.append(
                            f"adapter {adapter_id} raw report revision identity is missing"
                        )
                    else:
                        for field in ("commit", "tree"):
                            if report_identity.get(field) != run_identity.get(field):
                                issues.append(
                                    f"adapter {adapter_id} raw report {field} disagrees "
                                    "with run identity"
                                )
                    raw_materials = _core_report_materials(adapter_id, raw_report)
                    if adapter.get("materials") != raw_materials:
                        issues.append(
                            f"adapter {adapter_id} material bindings do not exactly match "
                            "the hash-bound raw report"
                        )
                    # If the repository changed while the suite was running,
                    # replaying an initial raw report against the final source
                    # would turn the identity race into a validation crash.
                    # Such an envelope is forced BLOCKED below and is never
                    # comparison eligible; retain only structural/hash/identity
                    # reconciliation for its raw evidence.
                    if source_changed:
                        continue
                    try:
                        (
                            raw_validation_issues,
                            raw_counts,
                            raw_metrics,
                            canonical_materials,
                            raw_failed_case_ids,
                            case_failure_class,
                        ) = _core_report_evidence(
                            adapter_id,
                            raw_report,
                            repository_root=repository_root,
                        )
                    except Exception as exc:  # noqa: BLE001
                        issues.append(
                            f"adapter {adapter_id} canonical raw validation raised "
                            f"{type(exc).__name__}: {exc}"
                        )
                        continue
                    try:
                        replayed_report = _replay_core_report(
                            adapter_id,
                            str(repository_root.resolve()),
                            str(current_source_identity["working_tree_sha256"]),
                        )
                    except Exception as exc:  # noqa: BLE001
                        issues.append(
                            f"adapter {adapter_id} semantic replay was unavailable: "
                            f"{type(exc).__name__}: {exc}"
                        )
                    else:
                        if _semantic_report_projection(
                            adapter_id, raw_report
                        ) != _semantic_report_projection(adapter_id, replayed_report):
                            issues.append(
                                f"adapter {adapter_id} raw semantics differ from "
                                "deterministic replay"
                            )
                    expected_status = "FAIL" if raw_validation_issues else "PASS"
                    if status != expected_status:
                        issues.append(
                            f"adapter {adapter_id} status does not match canonical raw report"
                        )
                    if counts != raw_counts:
                        issues.append(
                            f"adapter {adapter_id} normalized case counts do not match "
                            "canonical raw report"
                        )
                    if adapter.get("metrics") != raw_metrics:
                        issues.append(
                            f"adapter {adapter_id} normalized metrics do not match "
                            "canonical raw report"
                        )
                    if adapter.get("materials") != canonical_materials:
                        issues.append(
                            f"adapter {adapter_id} material bindings do not exactly match "
                            "canonical raw report"
                        )
                    adapter_failures = [
                        failure
                        for failure in failures
                        if failure.get("adapter_id") == adapter_id
                    ]
                    report_issue_failures = [
                        failure
                        for failure in adapter_failures
                        if failure.get("case_id") is None
                        and failure.get("failure_class") == "report_contract_violation"
                    ]
                    recorded_report_issues = [
                        str(failure.get("summary")) for failure in report_issue_failures
                    ]
                    if recorded_report_issues != raw_validation_issues:
                        issues.append(
                            f"adapter {adapter_id} report-contract failures do not reconcile "
                            "with canonical raw validation"
                        )
                    if any(
                        failure.get("run_status") != "FAIL"
                        or failure.get("oracle") != definition.get("oracle")
                        for failure in report_issue_failures
                    ):
                        issues.append(
                            f"adapter {adapter_id} report-contract failure metadata is inconsistent"
                        )
                    case_failures = [
                        failure
                        for failure in adapter_failures
                        if failure.get("case_id") is not None
                    ]
                    recorded_case_ids = [
                        str(failure.get("case_id")) for failure in case_failures
                    ]
                    if recorded_case_ids != raw_failed_case_ids:
                        issues.append(
                            f"adapter {adapter_id} case failures do not reconcile with raw rows"
                        )
                    if any(
                        failure.get("failure_class") != case_failure_class
                        or failure.get("run_status") != "FAIL"
                        or failure.get("oracle") != definition.get("oracle")
                        for failure in case_failures
                    ):
                        issues.append(
                            f"adapter {adapter_id} case failure metadata is inconsistent"
                        )
                    recognized_failure_ids = {
                        str(failure.get("failure_id"))
                        for failure in report_issue_failures + case_failures
                    }
                    if recognized_failure_ids != {
                        str(failure.get("failure_id")) for failure in adapter_failures
                    }:
                        issues.append(
                            f"adapter {adapter_id} contains unreconciled failure records"
                        )
            elif status in {"BLOCKED", "NOT_RUN"} and not source_changed:
                registered_materials = cast(list[Any], definition.get("materials") or [])
                expected_materials = {
                    str(item): file_sha256(repository_root / str(item))
                    if (repository_root / str(item)).is_file()
                    else None
                    for item in registered_materials
                }
                if adapter.get("materials") != expected_materials:
                    issues.append(
                        f"adapter {adapter_id} blocked material bindings disagree with registry"
                    )
        elif definition is not None and adapter.get("command") != definition.get("command"):
            issues.append(f"adapter {adapter_id} command disagrees with registry")

    bindings = envelope.get("bindings")
    expected_bindings = {
        "eval_lab": eval_lab_source_identity(repository_root),
        "evaluation_source": expected_evaluator,
        "registry": {
            "path": str(REGISTRY_RELATIVE),
            "sha256": file_sha256(repository_root / REGISTRY_RELATIVE),
        },
        "policy": {
            "path": str(POLICY_RELATIVE),
            "sha256": file_sha256(repository_root / POLICY_RELATIVE),
        },
        "failure_record_schema": {
            "path": str(FAILURE_SCHEMA_RELATIVE),
            "sha256": file_sha256(repository_root / FAILURE_SCHEMA_RELATIVE),
        },
    }
    if bindings != expected_bindings:
        issues.append("run bindings are incomplete, incompatible, or stale")

    identity = envelope.get("identity")
    identity_keys = {
        "application_sha",
        "branch",
        "changed_during_run",
        "commit",
        "dirty",
        "final_working_tree_sha256",
        "final_working_tree_status_sha256",
        "imported_firelens_path",
        "python_executable",
        "tree",
        "working_tree_sha256",
        "working_tree_status_sha256",
    }
    if not isinstance(identity, dict) or not identity_keys <= set(identity):
        issues.append("run source identity is incomplete")
    else:
        commit = identity.get("commit")
        application_sha = identity.get("application_sha")
        if re.fullmatch(r"[0-9a-f]{40}", str(commit or "")) is None:
            issues.append("run commit is malformed")
        tree = identity.get("tree")
        if re.fullmatch(r"[0-9a-f]{40}", str(tree or "")) is None:
            issues.append("run tree is malformed")
        resolved_tree = (
            _git_value(repository_root, "rev-parse", "--verify", f"{commit}^{{tree}}")
            if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)
            else None
        )
        if resolved_tree is None:
            issues.append("run commit does not resolve to a local Git object")
        elif tree != resolved_tree:
            issues.append("run tree does not match the commit's Git tree")
        for field in (
            "working_tree_sha256",
            "working_tree_status_sha256",
            "final_working_tree_sha256",
            "final_working_tree_status_sha256",
        ):
            if re.fullmatch(r"[0-9a-f]{64}", str(identity.get(field) or "")) is None:
                issues.append(f"run {field} is malformed")
        if not isinstance(identity.get("dirty"), bool) or not isinstance(
            identity.get("changed_during_run"), bool
        ):
            issues.append("run dirty/change identity flags are not boolean")
        if identity.get("dirty") is False and application_sha != commit:
            issues.append("clean run application SHA is not its commit")
        if (
            identity.get("dirty") is True
            and re.fullmatch(r"[0-9a-f]{64}", str(application_sha or "")) is None
        ):
            issues.append("dirty run application SHA is not content-bound")
        if identity.get("changed_during_run") is False and identity.get(
            "working_tree_sha256"
        ) != identity.get("final_working_tree_sha256"):
            issues.append("stable run has different initial/final content digests")
        if identity.get("changed_during_run") is False and identity.get(
            "working_tree_status_sha256"
        ) != identity.get("final_working_tree_status_sha256"):
            issues.append("stable run has different initial/final status digests")
        if identity.get("changed_during_run") is False:
            exact_current_fields = [
                "application_sha",
                "commit",
                "dirty",
                "tree",
                "working_tree_sha256",
                "working_tree_status_sha256",
            ]
            if not historical_source:
                exact_current_fields.extend(
                    (
                        "branch",
                        "imported_firelens_path",
                        "python_executable",
                    )
                )
            for field in exact_current_fields:
                if identity.get(field) != current_source_identity.get(field):
                    issues.append(f"stable run {field} does not match current source identity")
        for field in ("working_tree_sha256", "working_tree_status_sha256"):
            if identity.get(f"final_{field}") != current_source_identity.get(field):
                issues.append(f"run final {field} does not match current source identity")

    identity_change_failures = [
        failure
        for failure in failures
        if failure.get("adapter_id") == "eval_lab_identity"
        and failure.get("failure_class") == "source_identity_changed_during_run"
        and failure.get("run_status") == "BLOCKED"
    ]
    if source_changed:
        if envelope.get("status") != "BLOCKED":
            issues.append("a source-changed run must be BLOCKED")
        if not identity_change_failures:
            issues.append("a source-changed run is missing its identity blocker")
    elif identity_change_failures:
        issues.append("a stable run contains a source-change identity blocker")

    summary = envelope.get("summary")
    if not isinstance(summary, dict):
        issues.append("run summary is missing")
    else:
        expected_summary = {
            "adapter_counts": {
                state: sum(adapter.get("status") == state for adapter in adapters)
                for state in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
            },
            "executed_cases": sum(
                int(cast(dict[str, Any], adapter.get("case_counts") or {}).get("executed") or 0)
                for adapter in adapters
            ),
            "passed_cases": sum(
                int(cast(dict[str, Any], adapter.get("case_counts") or {}).get("passed") or 0)
                for adapter in adapters
            ),
            "failed_cases": sum(
                int(cast(dict[str, Any], adapter.get("case_counts") or {}).get("failed") or 0)
                for adapter in adapters
            ),
            "failure_records": len(failures),
        }
        if summary != expected_summary:
            issues.append("run summary does not match adapters and failures")
    if envelope.get("status") != _status_from(adapters, failures):
        issues.append("run status does not match adapter/failure precedence")
    return issues


def _render_report(envelope: dict[str, Any]) -> str:
    lines = [
        f"# EvalLab {envelope['suite']} report",
        "",
        f"- Run: `{envelope['run_id']}`",
        f"- Status: `{envelope['status']}`",
        f"- Commit: `{envelope['identity'].get('commit')}`",
        f"- Tree: `{envelope['identity'].get('tree')}`",
        f"- Dirty: `{envelope['identity'].get('dirty')}`",
        "- Authority: engineering evidence only; not deployment or release qualification",
        "",
        "## Adapters",
        "",
        "| Adapter | Status | Executed | Passed | Failed |",
        "|---|---:|---:|---:|---:|",
    ]
    for adapter in cast(list[dict[str, Any]], envelope["adapters"]):
        counts = cast(dict[str, Any], adapter["case_counts"])
        lines.append(
            f"| `{adapter['adapter_id']}` | {adapter['status']} | "
            f"{counts['executed']} | {counts['passed']} | {counts['failed']} |"
        )
    failures = cast(list[dict[str, Any]], envelope["failures"])
    lines.extend(["", "## Failures and blockers", ""])
    if not failures:
        lines.append("None recorded.")
    else:
        for failure in failures:
            case = f" / `{failure['case_id']}`" if failure.get("case_id") else ""
            lines.append(
                f"- `{failure['run_status']}` `{failure['adapter_id']}`{case}: {failure['summary']}"
            )
    lines.extend(
        [
            "",
            "## Limits",
            "",
            "This report does not establish provider, live-feed, browser, sealed-label, human, deployed, or release qualification unless a separately authorized adapter records that evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _run_local(
    context: RunContext, suite: str, definition: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started_at = _utc_now()
    adapter_id = definition["id"]
    report = local_adapters.execute(context.root, context.run_dir, definition, context.identity)
    raw_relative = f"raw/{adapter_id}.json"
    _write_json(context.run_dir / raw_relative, report)
    issues = local_adapters.validate(report, context.root, context.run_dir, definition)
    rows = report["rows"]
    counts = local_adapters.counts(rows, len(definition["expected_ids"]))
    failures = [
        _new_failure(
            context,
            suite=suite,
            adapter_id=adapter_id,
            case_id=row["id"],
            status="FAIL",
            failure_class="local_diagnostic_assertion",
            severity="HIGH",
            oracle="browser_functional"
            if definition["engine"] == "playwright"
            else "deterministic_executable",
            summary="The named local diagnostic assertion failed; inspect native results.",
            expected={"outcome": "passed"},
            observed=row,
            evidence=[raw_relative],
            first_divergent_layer=None,
            first_divergence_confidence="unknown",
            lifecycle_status="review",
            reproduction=[f"python -m firelens_eval run --suite {suite}"],
        )
        for row in rows
        if row["outcome"] == "failed"
    ]
    if issues:
        failures.append(
            _new_failure(
                context,
                suite=suite,
                adapter_id=adapter_id,
                case_id=None,
                status="BLOCKED",
                failure_class="local_diagnostic_harness",
                severity="HIGH",
                oracle="deterministic_executable",
                summary="Local runner evidence is incomplete or inconsistent.",
                expected={"issues": []},
                observed={"issues": issues},
                evidence=[raw_relative],
                first_divergent_layer="evaluation",
                reproduction=[f"python -m firelens_eval run --suite {suite}"],
            )
        )
    status: Status = "BLOCKED" if issues else "FAIL" if failures else "PASS"
    return _adapter_result(
        context,
        adapter_id,
        status=status,
        command=local_adapters.canonical_command(definition),
        raw_artifact=raw_relative,
        case_counts=counts,
        metrics={"local_only": True},
        materials=report["materials"],
        failures=failures,
        limitations=[report["limits"]],
        started_at=started_at,
    ), failures


def run_suite(
    suite: str,
    *,
    output_dir: Path | None = None,
    repository_root: Path = ROOT,
) -> tuple[dict[str, Any], Path]:
    if suite not in SUITES:
        raise ValueError(f"unknown suite {suite!r}; choose one of {', '.join(SUITES)}")
    registry = load_registry(repository_root)
    policy = load_policy(repository_root)
    identity = source_identity(repository_root)
    started_at = _utc_now()
    run_seed = {
        "suite": suite,
        "started_at": started_at,
        "commit": identity.get("commit"),
        "tree": identity.get("tree"),
        "application_sha": identity.get("application_sha"),
        "registry": file_sha256(repository_root / REGISTRY_RELATIVE),
        "policy": file_sha256(repository_root / POLICY_RELATIVE),
        "runner": eval_lab_source_identity(repository_root)["sha256"],
        "evaluator": evaluation_source_identity(repository_root)["sha256"],
        "failure_record_schema": file_sha256(repository_root / FAILURE_SCHEMA_RELATIVE),
    }
    run_id = f"{suite}-{_canonical_sha256(run_seed)[:16]}"
    if output_dir is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = repository_root / "output/eval_lab" / f"{stamp}-{run_id}"
    else:
        run_dir = output_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    context = RunContext(
        root=repository_root,
        run_dir=run_dir,
        run_id=run_id,
        started_at=started_at,
        identity=identity,
        registry=registry,
        policy=policy,
    )
    adapters: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if suite == "core":
        for runner in (_run_productbench, _run_claimbench, _run_hard_probe, _run_source_aware):
            adapter, adapter_failures = runner(context)
            adapters.append(adapter)
            failures.extend(adapter_failures)
        if identity["dirty"] and policy.get("require_clean_tree_for_pass") is True:
            failures.append(
                _new_failure(
                    context,
                    suite=suite,
                    adapter_id="eval_lab_identity",
                    case_id=None,
                    status="BLOCKED",
                    failure_class="dirty_source_tree",
                    severity="HIGH",
                    oracle="deterministic_executable",
                    summary="The source tree was dirty when EvalLab captured its identity.",
                    expected={"dirty": False},
                    observed={
                        "dirty": True,
                        "status_sha256": identity["working_tree_status_sha256"],
                        "working_tree_sha256": identity["working_tree_sha256"],
                    },
                    evidence=[],
                    first_divergent_layer="source_identity",
                    reproduction=["git status --short"],
                )
            )
    else:
        raw_suite = cast(dict[str, Any], cast(dict[str, Any], registry["suites"])[suite])
        local_definitions = local_adapters.definitions(repository_root)
        for raw_definition in cast(list[Any], raw_suite["adapters"]):
            if raw_definition["id"] in local_definitions:
                adapter, adapter_failures = _run_local(
                    context, suite, local_definitions[raw_definition["id"]]
                )
            else:
                adapter, adapter_failures = _blocked_adapter(
                    context,
                    suite=suite,
                    definition=cast(dict[str, Any], raw_definition),
                )
            adapters.append(adapter)
            failures.extend(adapter_failures)
        if identity["dirty"] and policy.get("require_clean_tree_for_pass") is True:
            failures.append(
                _new_failure(
                    context,
                    suite=suite,
                    adapter_id="eval_lab_identity",
                    case_id=None,
                    status="BLOCKED",
                    failure_class="dirty_source_tree",
                    severity="HIGH",
                    oracle="deterministic_executable",
                    summary="The source tree was dirty when local execution started.",
                    expected={"dirty": False},
                    observed={"dirty": True},
                    evidence=[],
                    first_divergent_layer="source_identity",
                    reproduction=["git status --short"],
                )
            )
    final_identity = source_identity(repository_root)
    identity_changed = any(
        final_identity.get(key) != identity.get(key)
        for key in (
            "commit",
            "tree",
            "working_tree_sha256",
            "imported_firelens_path",
        )
    )
    identity["final_working_tree_status_sha256"] = final_identity["working_tree_status_sha256"]
    identity["final_working_tree_sha256"] = final_identity["working_tree_sha256"]
    identity["changed_during_run"] = identity_changed
    if identity_changed:
        failures.append(
            _new_failure(
                context,
                suite=suite,
                adapter_id="eval_lab_identity",
                case_id=None,
                status="BLOCKED",
                failure_class="source_identity_changed_during_run",
                severity="HIGH",
                oracle="deterministic_executable",
                summary="The source identity changed while EvalLab was executing.",
                expected={
                    key: identity.get(key) for key in ("commit", "tree", "working_tree_sha256")
                },
                observed={
                    key: final_identity.get(key)
                    for key in ("commit", "tree", "working_tree_sha256")
                },
                evidence=[],
                first_divergent_layer="source_identity",
                reproduction=[
                    "git status --short",
                    "git rev-parse HEAD",
                    "git rev-parse HEAD^{tree}",
                ],
            )
        )
    for failure in failures:
        record_issues = validate_failure_record(failure, repository_root=repository_root)
        if record_issues:
            raise RuntimeError(
                f"invalid FailureRecord {failure.get('failure_id')}: "
                + "; ".join(record_issues)
            )
    status = _status_from(adapters, failures)
    envelope: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite": suite,
        "status": status,
        "qualification_role": cast(dict[str, Any], registry["suites"])[suite][
            "qualification_role"
        ],
        "started_at": started_at,
        "finished_at": _utc_now(),
        "identity": identity,
        "bindings": {
            "eval_lab": eval_lab_source_identity(repository_root),
            "evaluation_source": evaluation_source_identity(repository_root),
            "registry": {
                "path": str(REGISTRY_RELATIVE),
                "sha256": file_sha256(repository_root / REGISTRY_RELATIVE),
            },
            "policy": {
                "path": str(POLICY_RELATIVE),
                "sha256": file_sha256(repository_root / POLICY_RELATIVE),
            },
            "failure_record_schema": {
                "path": str(FAILURE_SCHEMA_RELATIVE),
                "sha256": file_sha256(repository_root / FAILURE_SCHEMA_RELATIVE),
            },
        },
        "execution": {
            "network_allowed": False,
            "provider_calls_allowed": False,
            "cost_ceiling_usd": 0.0,
        },
        "adapters": adapters,
        "summary": {
            "adapter_counts": {
                state: sum(adapter["status"] == state for adapter in adapters)
                for state in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
            },
            "executed_cases": sum(adapter["case_counts"]["executed"] for adapter in adapters),
            "passed_cases": sum(adapter["case_counts"]["passed"] for adapter in adapters),
            "failed_cases": sum(adapter["case_counts"]["failed"] for adapter in adapters),
            "failure_records": len(failures),
        },
        "failures": failures,
        "limitations": [
            "Local zero-cost engineering evidence is not release qualification.",
            "Provider, live, sealed, human, accessibility, and deployment gates remain separate.",
        ],
    }
    envelope_issues = validate_run_envelope(
        envelope,
        envelope_path=run_dir / "envelope.json",
        repository_root=repository_root,
    )
    if envelope_issues:
        raise RuntimeError("invalid EvalLab run envelope: " + "; ".join(envelope_issues))
    _write_json(run_dir / "envelope.json", envelope)
    (run_dir / "failure_records.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in failures
        ),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(_render_report(envelope), encoding="utf-8")
    return envelope, run_dir


def _envelopes(artifact_roots: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    seen: set[Path] = set()
    for artifact_root in artifact_roots:
        if not artifact_root.exists():
            continue
        candidates = (
            [artifact_root]
            if artifact_root.name == "envelope.json"
            else artifact_root.rglob("envelope.json")
        )
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            try:
                report = _load_mapping(resolved)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if report.get("schema_version") == RUN_SCHEMA_VERSION:
                found.append((resolved, report))
    return sorted(found, key=lambda item: str(item[1].get("finished_at") or ""), reverse=True)


def _default_search_roots(repository_root: Path) -> list[Path]:
    return [repository_root / "output/eval_lab", repository_root / "evals/eval_lab/runs"]


def diagnose_case(
    case_id: str,
    *,
    artifact_root: Path | None = None,
    repository_root: Path = ROOT,
) -> tuple[dict[str, Any], int]:
    roots = (
        [artifact_root] if artifact_root is not None else _default_search_roots(repository_root)
    )
    matches: list[dict[str, Any]] = []
    for envelope_path, envelope in _envelopes(roots):
        if _validate_envelope_at_its_source(
            envelope,
            envelope_path=envelope_path,
            repository_root=repository_root,
        ):
            continue
        run_dir = envelope_path.parent
        failures = [
            item
            for item in cast(list[Any], envelope.get("failures") or [])
            if isinstance(item, dict) and item.get("case_id") == case_id
        ]
        for raw_adapter in cast(list[Any], envelope.get("adapters") or []):
            if not isinstance(raw_adapter, dict):
                continue
            raw_relative = raw_adapter.get("raw_artifact")
            if not isinstance(raw_relative, str):
                continue
            raw_path = run_dir / raw_relative
            try:
                raw_report = _load_mapping(raw_path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            rows_value = raw_report.get("results", raw_report.get("rows", []))
            if not isinstance(rows_value, list):
                continue
            rows = [
                row for row in rows_value if isinstance(row, dict) and row.get("id") == case_id
            ]
            adapter_failures = [
                item
                for item in failures
                if item.get("adapter_id") == raw_adapter.get("adapter_id")
            ]
            if rows or adapter_failures:
                matches.append(
                    {
                        "run_id": envelope.get("run_id"),
                        "suite": envelope.get("suite"),
                        "run_status": envelope.get("status"),
                        "adapter_id": raw_adapter.get("adapter_id"),
                        "adapter_status": raw_adapter.get("status"),
                        "identity": envelope.get("identity"),
                        "envelope_path": str(envelope_path),
                        "raw_artifact": str(raw_path),
                        "rows": rows,
                        "failure_records": adapter_failures,
                    }
                )
        matched_failure_ids = {
            str(failure.get("failure_id"))
            for match in matches
            if match.get("run_id") == envelope.get("run_id")
            for failure in cast(list[dict[str, Any]], match.get("failure_records") or [])
        }
        for failure in failures:
            if str(failure.get("failure_id")) in matched_failure_ids:
                continue
            matches.append(
                {
                    "run_id": envelope.get("run_id"),
                    "suite": envelope.get("suite"),
                    "run_status": envelope.get("status"),
                    "adapter_id": failure.get("adapter_id"),
                    "adapter_status": failure.get("run_status"),
                    "identity": envelope.get("identity"),
                    "envelope_path": str(envelope_path),
                    "raw_artifact": None,
                    "rows": [],
                    "failure_records": [failure],
                }
            )
    payload = {
        "schema_version": "firelens.eval_lab.diagnosis.v1",
        "case_id": case_id,
        "status": "FOUND" if matches else "BLOCKED",
        "matches": matches,
        "reason": None if matches else "No normalized EvalLab artifact contains this case ID.",
    }
    return payload, 0 if matches else 2


def _artifact_eligibility_issues(envelope: dict[str, Any]) -> list[str]:
    identity = envelope.get("identity")
    if not isinstance(identity, dict):
        return ["source identity is missing"]
    issues: list[str] = []
    commit = identity.get("commit")
    tree = identity.get("tree")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        issues.append("commit is not an exact 40-character SHA")
    if not isinstance(tree, str) or re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        issues.append("tree is not an exact 40-character SHA")
    if identity.get("dirty") is not False:
        issues.append("source tree was dirty")
    if identity.get("changed_during_run") is not False:
        issues.append("source identity was not proven stable for the run")
    if identity.get("application_sha") != commit:
        issues.append("application SHA is not the clean commit")
    return issues


def _validate_envelope_at_its_source(
    envelope: dict[str, Any],
    *,
    envelope_path: Path,
    repository_root: Path,
) -> list[str]:
    """Validate immutable evidence against the commit it claims to evaluate."""

    identity = envelope.get("identity")
    commit = identity.get("commit") if isinstance(identity, dict) else None
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        return validate_run_envelope(
            envelope,
            envelope_path=envelope_path,
            repository_root=repository_root,
        )
    current_commit = _git_value(repository_root, "rev-parse", "HEAD")
    if isinstance(identity, dict) and identity.get("dirty") is True:
        if current_commit != commit:
            return ["dirty historical evidence cannot be reconstructed from a Git commit"]
        return validate_run_envelope(
            envelope,
            envelope_path=envelope_path,
            repository_root=repository_root,
        )
    current_identity = source_identity(repository_root)
    if current_commit == commit and current_identity.get("dirty") is False:
        return validate_run_envelope(
            envelope,
            envelope_path=envelope_path,
            repository_root=repository_root,
            historical_source=True,
        )
    with tempfile.TemporaryDirectory(prefix="firelens-eval-source-") as temporary:
        snapshot_root = Path(temporary) / "repository"
        cloned = subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--shared",
                "--no-checkout",
                str(repository_root),
                str(snapshot_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if cloned.returncode != 0:
            return [
                "historical source snapshot could not be created: "
                + (cloned.stderr.strip() or f"git clone exited {cloned.returncode}")
            ]
        checked_out = subprocess.run(
            ["git", "-C", str(snapshot_root), "checkout", "--quiet", "--detach", commit],
            check=False,
            capture_output=True,
            text=True,
        )
        if checked_out.returncode != 0:
            return [
                "historical source snapshot could not be checked out: "
                + (
                    checked_out.stderr.strip()
                    or f"git checkout exited {checked_out.returncode}"
                )
            ]
        try:
            return validate_run_envelope(
                envelope,
                envelope_path=envelope_path,
                repository_root=snapshot_root,
                historical_source=True,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return [
                "historical source snapshot validation was unavailable: "
                f"{type(exc).__name__}: {exc}"
            ]


def _stable_material(value: Any) -> Any:
    """Remove evaluated-revision fields while retaining evaluator/data bindings."""

    volatile = {
        "application_sha",
        "branch",
        "changed_during_run",
        "commit",
        "dirty",
        "final_working_tree_sha256",
        "final_working_tree_status_sha256",
        "tree",
        "working_tree_sha256",
        "working_tree_status_sha256",
    }
    if isinstance(value, dict):
        return {
            str(key): _stable_material(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in volatile
        }
    if isinstance(value, list):
        return [_stable_material(item) for item in value]
    return value


def _comparison_bindings(envelope: dict[str, Any]) -> dict[str, Any]:
    bindings = envelope.get("bindings")
    adapters = envelope.get("adapters")
    return {
        "eval_lab": _stable_material(bindings if isinstance(bindings, dict) else {}),
        "adapter_materials": {
            str(adapter.get("adapter_id")): _stable_material(adapter.get("materials") or {})
            for adapter in cast(list[Any], adapters or [])
            if isinstance(adapter, dict) and adapter.get("adapter_id")
        },
        "adapter_evaluators": {
            str(adapter.get("adapter_id")): _stable_material(adapter.get("evaluator") or {})
            for adapter in cast(list[Any], adapters or [])
            if isinstance(adapter, dict) and adapter.get("adapter_id")
        },
    }


def _select_sha(
    sha: str,
    envelopes: list[tuple[Path, dict[str, Any]]],
    *,
    suite: str,
) -> tuple[Path, dict[str, Any]] | None:
    matches = [
        item
        for item in envelopes
        if item[1].get("suite") == suite
        and isinstance(cast(dict[str, Any], item[1].get("identity") or {}).get("commit"), str)
        and str(cast(dict[str, Any], item[1]["identity"])["commit"]).startswith(sha)
    ]
    distinct_commits = {
        str(cast(dict[str, Any], item[1]["identity"])["commit"]) for item in matches
    }
    if len(distinct_commits) > 1:
        raise ValueError(f"ambiguous Git SHA prefix for {suite}: {sha}")
    eligible = [item for item in matches if not _artifact_eligibility_issues(item[1])]
    return eligible[0] if eligible else matches[0] if matches else None


def _failed_case_ids(envelope: dict[str, Any]) -> set[str]:
    return {
        str(item["case_id"])
        for item in cast(list[Any], envelope.get("failures") or [])
        if isinstance(item, dict) and item.get("case_id")
    }


def compare_runs(
    base_sha: str,
    candidate_sha: str,
    *,
    artifact_root: Path | None = None,
    repository_root: Path = ROOT,
    suite: str = "core",
) -> tuple[dict[str, Any], int]:
    if suite not in SUITES:
        raise ValueError(f"unknown comparison suite: {suite}")
    resolved_inputs: dict[str, str] = {}
    for label, sha in (("base", base_sha), ("candidate", candidate_sha)):
        if re.fullmatch(r"[0-9a-f]{7,40}", sha) is None:
            raise ValueError(f"{label} SHA must contain 7-40 lowercase hexadecimal characters")
        resolved = _git_value(repository_root, "rev-parse", "--verify", f"{sha}^{{commit}}")
        if resolved is None or re.fullmatch(r"[0-9a-f]{40}", resolved) is None:
            raise ValueError(f"{label} SHA does not resolve to a local commit")
        resolved_inputs[label] = resolved
    roots = (
        [artifact_root] if artifact_root is not None else _default_search_roots(repository_root)
    )
    envelopes = _envelopes(roots)
    base = _select_sha(resolved_inputs["base"], envelopes, suite=suite)
    candidate = _select_sha(
        resolved_inputs["candidate"],
        envelopes,
        suite=suite,
    )
    if base is None or candidate is None:
        missing = [
            sha
            for sha, value in ((base_sha, base), (candidate_sha, candidate))
            if value is None
        ]
        return (
            {
                "schema_version": "firelens.eval_lab.comparison.v1",
                "status": "BLOCKED",
                "base_sha": base_sha,
                "candidate_sha": candidate_sha,
                "suite": suite,
                "missing_artifacts_for": missing,
                "reason": "Comparison requires normalized envelopes for both source identities.",
            },
            2,
        )
    base_path, base_envelope = base
    candidate_path, candidate_envelope = candidate
    envelope_issues = {
        "base": _validate_envelope_at_its_source(
            base_envelope,
            envelope_path=base_path,
            repository_root=repository_root,
        ),
        "candidate": _validate_envelope_at_its_source(
            candidate_envelope,
            envelope_path=candidate_path,
            repository_root=repository_root,
        ),
    }
    if any(envelope_issues.values()):
        return (
            {
                "schema_version": "firelens.eval_lab.comparison.v1",
                "status": "BLOCKED",
                "base_sha": base_sha,
                "candidate_sha": candidate_sha,
                "suite": suite,
                "envelope_validation_issues": envelope_issues,
                "reason": "Comparison requires complete, coherent, hash-bound envelopes.",
            },
            2,
        )
    eligibility = {
        "base": _artifact_eligibility_issues(base_envelope),
        "candidate": _artifact_eligibility_issues(candidate_envelope),
    }
    if any(eligibility.values()):
        return (
            {
                "schema_version": "firelens.eval_lab.comparison.v1",
                "status": "BLOCKED",
                "base_sha": base_sha,
                "candidate_sha": candidate_sha,
                "suite": suite,
                "artifact_eligibility_issues": eligibility,
                "reason": "Comparison requires clean, stable, exact source identities.",
            },
            2,
        )
    base_bindings = _comparison_bindings(base_envelope)
    candidate_bindings = _comparison_bindings(candidate_envelope)
    if base_bindings != candidate_bindings:
        return (
            {
                "schema_version": "firelens.eval_lab.comparison.v1",
                "status": "BLOCKED",
                "base_sha": base_sha,
                "candidate_sha": candidate_sha,
                "suite": suite,
                "base_bindings_sha256": _canonical_sha256(base_bindings),
                "candidate_bindings_sha256": _canonical_sha256(candidate_bindings),
                "reason": "Evaluator, policy, schema, or dataset bindings are incompatible.",
            },
            2,
        )
    base_adapters = {
        str(item["adapter_id"]): item
        for item in cast(list[Any], base_envelope.get("adapters") or [])
        if isinstance(item, dict) and item.get("adapter_id")
    }
    candidate_adapters = {
        str(item["adapter_id"]): item
        for item in cast(list[Any], candidate_envelope.get("adapters") or [])
        if isinstance(item, dict) and item.get("adapter_id")
    }
    adapter_ids = sorted(set(base_adapters) | set(candidate_adapters))
    comparisons: list[dict[str, Any]] = []
    regressions: list[str] = []
    for adapter_id in adapter_ids:
        before = base_adapters.get(adapter_id)
        after = candidate_adapters.get(adapter_id)
        row = {
            "adapter_id": adapter_id,
            "base_status": before.get("status") if before else None,
            "candidate_status": after.get("status") if after else None,
            "base_case_counts": before.get("case_counts") if before else None,
            "candidate_case_counts": after.get("case_counts") if after else None,
        }
        if before is None or after is None:
            regressions.append(f"adapter set changed: {adapter_id}")
        elif before.get("status") == "PASS" and after.get("status") != "PASS":
            regressions.append(f"{adapter_id} changed from PASS to {after.get('status')}")
        else:
            before_failed = (
                _integer(cast(dict[str, Any], before.get("case_counts") or {}).get("failed"))
                or 0
            )
            after_failed = (
                _integer(cast(dict[str, Any], after.get("case_counts") or {}).get("failed"))
                or 0
            )
            if after_failed > before_failed:
                regressions.append(
                    f"{adapter_id} failed cases increased from {before_failed} to {after_failed}"
                )
        comparisons.append(row)
    new_failed_ids = sorted(
        _failed_case_ids(candidate_envelope) - _failed_case_ids(base_envelope)
    )
    if new_failed_ids:
        regressions.append("new failed case IDs: " + ", ".join(new_failed_ids))
    candidate_status = str(candidate_envelope.get("status"))
    status: Status = (
        "BLOCKED"
        if candidate_status in {"BLOCKED", "NOT_RUN"}
        else "FAIL"
        if regressions or candidate_status == "FAIL"
        else "PASS"
    )
    payload = {
        "schema_version": "firelens.eval_lab.comparison.v1",
        "status": status,
        "suite": base_envelope.get("suite"),
        "base": {
            "requested_sha": base_sha,
            "identity": base_envelope.get("identity"),
            "envelope_path": str(base_path),
            "run_id": base_envelope.get("run_id"),
        },
        "candidate": {
            "requested_sha": candidate_sha,
            "identity": candidate_envelope.get("identity"),
            "envelope_path": str(candidate_path),
            "run_id": candidate_envelope.get("run_id"),
        },
        "adapter_comparisons": comparisons,
        "new_failed_case_ids": new_failed_ids,
        "regressions": regressions,
    }
    return payload, 0 if status == "PASS" else 1 if status == "FAIL" else 2


def exit_code_for_status(status: str) -> int:
    if status == "PASS":
        return 0
    if status == "FAIL":
        return 1
    return 2
