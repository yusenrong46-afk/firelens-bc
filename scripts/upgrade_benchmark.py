#!/usr/bin/env python3
"""Capture and compare immutable FireLens V1.5-2 benchmark snapshots."""

# Private imports intentionally preserve the historical benchmark-script facade.
# ruff: noqa: F401

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

import yaml
from PIL import Image, UnidentifiedImageError

from firelens.benchmark import (
    _mean,
    _ranking_metrics,
    apply_relevance_addendum,
    benchmark_runtime_configuration,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.evaluation.common import sha256_json as _sha256_json
from firelens.evaluation.frontend_browser import (
    _frontend_axe,
    _frontend_classify_console_errors,
    _frontend_console_event,
    _frontend_http_failure,
    _frontend_layout,
    _frontend_runtime,
)
from firelens.evaluation.frontend_map import (
    _frontend_expected_map_records,
    _frontend_expected_map_roster,
    _frontend_map_evidence,
    _frontend_surface_row,
)
from firelens.evaluation.frontend_privacy import (
    _frontend_functional_journeys,
    _frontend_privacy_evidence,
    _privacy_token_findings,
    _privacy_token_matches,
    _validate_privacy_browser_surfaces,
)
from firelens.evaluation.frontend_protocol import (
    _frontend_bundle,
    _frontend_p75,
    _frontend_surface_environment,
    _frontend_surface_protocol,
    _require_object_list,
    _require_string_list,
)
from firelens.evaluation.frontend_qualification import (
    _capture_frontend_surface as _capture_frontend_surface_impl,
)
from firelens.evaluation.frontend_qualification import (
    _frontend_performance,
    _frontend_surface,
)
from firelens.evaluation.qualification_reports import (
    _hard_probe,
    _live,
    _review,
    _validated_id_status_rows,
    _validated_public_live_rows,
)
from firelens.evaluation.release_surfaces import (
    _bind_raw_deployment_evidence,
    _deployment,
    _preview,
    _preview_exact_support,
    _validate_artifact_digest,
    _write_deployment_template,
    _write_ux_template,
)
from firelens.evaluation.retrieval import (
    _development_retrieval,
    _ranking_context,
    _recomputed_development_candidate,
    _retrieval_qualification,
)
from firelens.evaluation.runtime_artifact import (
    _artifact,
    _build_runtime_artifact_pair,
    _finalize_runtime_artifact_pair,
    _inventory_file_entry,
    _paths_overlap,
    _rendered_json_sha256,
    _resolved_artifact_root,
    _runtime_artifact_metric_values,
    _runtime_candidate_document,
    _runtime_candidate_evidence,
    _runtime_candidate_id,
    _runtime_prohibited_reason,
    _write_runtime_artifact_evidence,
)
from firelens.evaluation.spec_models import (
    BenchmarkSpec as BenchmarkSpec,
)
from firelens.evaluation.spec_models import (
    DatasetRoleRegistry as DatasetRoleRegistry,
)
from firelens.evaluation.spec_models import (
    MetricSpec as MetricSpec,
)
from firelens.evaluation.spec_models import (
    UXTask as UXTask,
)
from firelens.evaluation.ux import (
    EXECUTION_ENVIRONMENT_FIELDS,
    UX_ALLOWED_ACCESS_METHODS,
    UX_DISTRIBUTION_MAX_SHARE_DELTA,
    UX_MINIMUM_CORE_COHORT_SIZE,
    UX_MINIMUM_DEVICE_CLASS_SIZE,
    UX_REQUIRED_ACCESS_METHODS,
    UX_REQUIRED_COHORTS,
    UX_REQUIRED_DEVICE_CLASSES,
    _bootstrap_ux_round,
    _execution_environment_comparability,
    _named_frontend_reviewer,
    _percentile,
    _ux,
    _ux_distribution_comparability,
    _ux_effect_intervals,
    _wilson_interval,
)
from firelens.owner_review import validate_owner_review
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval_experiment import _candidate_summary
from firelens.retrieval_review import validate_retrieval_owner_review
from firelens.review_workspace.qualification import verify_review_qualification_package
from firelens.runtime_artifact import (
    ArtifactIdentity,
    RuntimeArtifactError,
    build_runtime_inventory,
    compare_runtime_inventories,
)
from firelens.storage import atomic_text_writer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "data/evaluation/upgrade_benchmark_v1_5_2.yaml"
FRONTEND_MANUAL_REVIEW_PROTOCOL = ROOT / "data/evaluation/frontend_manual_review.v1.yaml"
SEMANTIC_DEVELOPMENT_REGISTRY = (
    ROOT / "data/evaluation/benchmark_v1_5_2_semantic_development_registry.json"
)
SEMANTIC_HOLDOUT_MANIFEST = (
    ROOT / "data/evaluation/benchmark_v1_5_2_semantic_holdout.manifest.json"
)
RUNTIME_ARTIFACT_CONTRACT = ROOT / "config/runtime_artifact_allowlist.v1.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture_frontend_surface(
    *,
    output_dir: Path,
    expected_commit: str,
    expected_environment: dict[str, str | int],
) -> dict[str, Any]:
    """Preserve script-level dependency overrides for capture characterization."""

    return _capture_frontend_surface_impl(
        output_dir=output_dir,
        expected_commit=expected_commit,
        expected_environment=expected_environment,
        run_logged=_run_logged,
        bundle_builder=_frontend_bundle,
        surface_validator=_frontend_surface,
    )


def load_dataset_role_registry(path: Path) -> DatasetRoleRegistry:
    registry = DatasetRoleRegistry.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    for dataset in registry.datasets:
        if dataset.status != "available":
            continue
        for relative in dataset.inputs:
            if not (ROOT / relative).is_file():
                raise ValueError(f"available dataset-role input does not exist: {relative}")
    return registry


def load_spec(path: Path) -> BenchmarkSpec:
    spec = BenchmarkSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    registry_path = ROOT / spec.dataset_role_registry
    registry = load_dataset_role_registry(registry_path)
    if registry.registry_id != spec.benchmark_id:
        raise ValueError("dataset-role registry does not match benchmark_id")
    if spec.frozen_before_upgrade and registry.ratification_status != "ratified":
        raise ValueError("a frozen benchmark requires a ratified dataset-role registry")
    if spec.frozen_before_upgrade:
        planned = [dataset.id for dataset in registry.datasets if dataset.status == "planned"]
        if planned:
            raise ValueError(
                "a frozen benchmark cannot retain planned evaluation datasets; "
                f"unresolved={planned}"
            )
        sealed_datasets = [
            dataset
            for dataset in registry.datasets
            if dataset.role == "sealed_release_qualification"
        ]
        if not sealed_datasets:
            raise ValueError("a frozen benchmark requires a sealed release dataset")
        sealed_inputs = {relative for dataset in sealed_datasets for relative in dataset.inputs}
        missing_sealed_inputs = sorted(sealed_inputs - set(spec.identity_inputs))
        if missing_sealed_inputs:
            raise ValueError(
                "sealed qualification inputs must be frozen benchmark identities; "
                f"missing={missing_sealed_inputs}"
            )
    if spec.dataset_role_registry not in spec.identity_inputs:
        raise ValueError("dataset-role registry must be a frozen identity input")
    _spec_seal_path(spec)
    for relative in [*spec.identity_inputs, *spec.harness_inputs]:
        if not (ROOT / relative).is_file():
            raise ValueError(f"benchmark input does not exist: {relative}")
    return spec


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _tracked_dirty() -> bool:
    working = subprocess.run(["git", "diff", "--quiet"], cwd=ROOT, check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False)
    return working.returncode != 0 or staged.returncode != 0


def _relevant_untracked_paths() -> list[str]:
    ignored_prefixes = (".agents/", "output/")
    return sorted(
        path
        for path in _git("ls-files", "--others", "--exclude-standard").splitlines()
        if path and not path.startswith(ignored_prefixes)
    )


def _repo_relative_path(path: Path, *, context: str) -> tuple[Path, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ValueError(f"{context} must be inside the repository") from error
    return resolved, relative


def _spec_seal_path(spec: BenchmarkSpec) -> tuple[Path, str]:
    configured = Path(spec.before_snapshot_seal)
    if configured.is_absolute():
        raise ValueError("before snapshot seal path must be repository-relative")
    if ".." in configured.parts:
        raise ValueError("before snapshot seal path must not traverse parent directories")
    configured_relative = configured.as_posix()
    unresolved = ROOT / configured
    if unresolved.is_symlink():
        raise ValueError("before snapshot seal path cannot be a symbolic link")
    path, relative = _repo_relative_path(unresolved, context="before snapshot seal")
    if relative != configured_relative:
        raise ValueError(
            "before snapshot seal must use the exact canonical repository path "
            "without symbolic-link components"
        )
    if relative.startswith("output/"):
        raise ValueError("before snapshot seal cannot be stored under ignored output")
    return path, relative


def _path_is_tracked_and_unmodified(path: Path) -> bool:
    _, relative = _repo_relative_path(path, context="tracked benchmark artifact")
    tracked = _git_evidence_command(
        ["ls-files", "--error-unmatch", "--", relative],
        context=f"cannot verify tracked benchmark artifact {relative}",
        allowed_returncodes=(0, 1),
    )
    if tracked.returncode != 0:
        return False
    unstaged = _git_evidence_command(
        ["diff", "--quiet", "--", relative],
        context=f"cannot verify unstaged benchmark artifact state for {relative}",
        allowed_returncodes=(0, 1),
    )
    staged = _git_evidence_command(
        ["diff", "--cached", "--quiet", "--", relative],
        context=f"cannot verify staged benchmark artifact state for {relative}",
        allowed_returncodes=(0, 1),
    )
    return unstaged.returncode == 0 and staged.returncode == 0


def _git_evidence_command(
    args: list[str],
    *,
    context: str,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    """Run a Git evidence command while preserving fail-closed diagnostics."""

    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ValueError(
            f"{context}: Git could not run; verify the repository and Git installation"
        ) from error
    if completed.returncode not in allowed_returncodes:
        detail = (completed.stderr or completed.stdout).strip() or "no diagnostic output"
        command = "git " + " ".join(args)
        raise ValueError(
            f"{context}: `{command}` failed with exit {completed.returncode}: {detail}"
        )
    return completed


def _exact_git_commit(commitish: str, *, context: str) -> str:
    if not isinstance(commitish, str) or not commitish.strip():
        raise ValueError(f"{context} has no Git commit")
    observed = commitish.strip()
    completed = _git_evidence_command(
        ["rev-parse", "--verify", f"{observed}^{{commit}}"],
        context=f"cannot resolve {context}",
    )
    resolved = completed.stdout.strip()
    if not resolved or resolved != observed:
        raise ValueError(
            f"{context} must use the exact full Git commit ID; "
            f"recorded={observed!r}, resolved={resolved!r}"
        )
    return resolved


def _current_git_commit(*, context: str) -> str:
    resolved = _git_evidence_command(
        ["rev-parse", "--verify", "HEAD^{commit}"],
        context=f"cannot resolve {context}",
    ).stdout.strip()
    return _exact_git_commit(resolved, context=context)


def _resolve_before_snapshot_ancestry(
    *,
    spec: BenchmarkSpec,
    before: dict[str, Any],
    after_commit: str,
) -> dict[str, Any]:
    """Prove before -> seal introduction -> after using complete Git history."""

    seal_path, relative_seal = _spec_seal_path(spec)
    if not seal_path.is_file():
        raise ValueError(
            f"before snapshot seal is missing at {relative_seal}; create and commit it first"
        )
    if seal_path.is_symlink():
        raise ValueError("before snapshot seal must be a regular file, not a symbolic link")

    shallow = _git_evidence_command(
        ["rev-parse", "--is-shallow-repository"],
        context="cannot determine whether before-seal Git history is complete",
    ).stdout.strip()
    if shallow == "true":
        raise ValueError(
            "before-seal ancestry cannot be verified from a shallow repository; "
            "fetch complete history (for example `git fetch --unshallow`) and retry"
        )
    if shallow != "false":
        raise ValueError(
            "before-seal ancestry received an invalid shallow-history response from Git"
        )

    tracked = _git_evidence_command(
        ["ls-files", "--error-unmatch", "--", relative_seal],
        context=f"cannot verify tracked before snapshot seal {relative_seal}",
        allowed_returncodes=(0, 1),
    )
    if tracked.returncode != 0:
        raise ValueError(
            f"before snapshot seal {relative_seal} is untracked; commit the exact seal file"
        )
    for diff_args, state in (
        (["diff", "--quiet", "--", relative_seal], "unstaged"),
        (["diff", "--cached", "--quiet", "--", relative_seal], "staged"),
    ):
        diff = _git_evidence_command(
            diff_args,
            context=f"cannot verify {state} before snapshot seal state",
            allowed_returncodes=(0, 1),
        )
        if diff.returncode != 0:
            raise ValueError(
                f"before snapshot seal {relative_seal} has {state} modifications; "
                "restore the committed seal before qualification"
            )

    seal = _read_report(seal_path)
    if seal is None:
        raise ValueError("tracked before snapshot seal is unreadable")
    seal_candidate = seal.get("candidate_identity")
    before_identity = before.get("identity")
    if not isinstance(seal_candidate, dict) or not isinstance(before_identity, dict):
        raise ValueError("before snapshot and seal lack candidate commit evidence")
    seal_before_commit = seal_candidate.get("commit")
    snapshot_before_commit = before_identity.get("commit")
    if seal_before_commit != snapshot_before_commit:
        raise ValueError(
            "before snapshot candidate commit differs from the commit recorded by its seal"
        )
    before_commit = _exact_git_commit(seal_before_commit, context="before snapshot candidate")
    resolved_after_commit = _exact_git_commit(after_commit, context="after candidate")

    history = _git_evidence_command(
        [
            "log",
            "--format=%H",
            "--all",
            "HEAD",
            resolved_after_commit,
            "--",
            relative_seal,
        ],
        context=f"cannot resolve immutable history for {relative_seal}",
    ).stdout.splitlines()
    history_commits = [commit.strip() for commit in history if commit.strip()]
    if len(history_commits) != 1:
        if not history_commits:
            raise ValueError(
                f"no Git commit introduces before snapshot seal {relative_seal}; "
                "commit the seal and ensure complete history is available"
            )
        raise ValueError(
            f"before snapshot seal {relative_seal} has ambiguous or mutable history; "
            f"path_commits={history_commits}"
        )
    additions = _git_evidence_command(
        [
            "log",
            "--format=%H",
            "--diff-filter=A",
            "--all",
            "HEAD",
            resolved_after_commit,
            "--",
            relative_seal,
        ],
        context=f"cannot resolve the introducing commit for {relative_seal}",
    ).stdout.splitlines()
    addition_commits = [commit.strip() for commit in additions if commit.strip()]
    if not addition_commits:
        raise ValueError(
            f"no Git commit introduces before snapshot seal {relative_seal}; "
            "commit the seal and ensure complete history is available"
        )
    if len(addition_commits) != 1:
        raise ValueError(
            f"before snapshot seal {relative_seal} has ambiguous introduction history; "
            f"addition_commits={addition_commits}"
        )
    seal_commit = _exact_git_commit(
        addition_commits[0], context="before snapshot seal introducing commit"
    )
    if history_commits[0] != seal_commit:
        raise ValueError(
            f"Git history for before snapshot seal {relative_seal} does not identify "
            "one immutable introduction commit"
        )

    introduced_blob = _git_evidence_command(
        ["rev-parse", f"{seal_commit}:{relative_seal}"],
        context="cannot read the before snapshot seal from its introducing commit",
    ).stdout.strip()
    current_blob = _git_evidence_command(
        ["hash-object", "--", relative_seal],
        context="cannot hash the tracked before snapshot seal",
    ).stdout.strip()
    if not introduced_blob or introduced_blob != current_blob:
        raise ValueError(
            "the tracked before snapshot seal differs from the file introduced by its "
            f"resolved commit {seal_commit}; the seal must remain immutable"
        )
    after_blob = _git_evidence_command(
        ["rev-parse", f"{resolved_after_commit}:{relative_seal}"],
        context="after candidate does not contain the committed before snapshot seal",
    ).stdout.strip()
    if after_blob != introduced_blob:
        raise ValueError(
            "after candidate contains a different before snapshot seal blob; "
            "the committed seal must remain immutable"
        )

    def require_ancestor(ancestor: str, descendant: str, *, message: str) -> None:
        result = _git_evidence_command(
            ["merge-base", "--is-ancestor", ancestor, descendant],
            context="cannot verify before-seal Git ancestry",
            allowed_returncodes=(0, 1),
        )
        if result.returncode != 0:
            raise ValueError(message)

    require_ancestor(
        before_commit,
        seal_commit,
        message=(
            "before snapshot candidate is not an ancestor of the seal-introducing "
            "commit; the seal is on an unrelated or invalid history"
        ),
    )
    require_ancestor(
        seal_commit,
        resolved_after_commit,
        message=(
            "seal-introducing commit is not an ancestor of the after candidate; "
            "the after candidate is on an unrelated side branch or predates the seal"
        ),
    )
    return {
        "status": "verified",
        "seal_path": relative_seal,
        "seal_sha256": file_sha256(seal_path),
        "before_candidate_commit": before_commit,
        "seal_introducing_commit": seal_commit,
        "after_candidate_commit": resolved_after_commit,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }


def _read_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw) if path.suffix in {".yaml", ".yml"} else json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def _strict_bool(payload: dict[str, Any], key: str, context: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"{context} {key} must be a strict boolean")
    return value


def _strict_int(
    payload: dict[str, Any],
    key: str,
    context: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} {key} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{context} {key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{context} {key} must be at most {maximum}")
    return value


def _strict_number(
    payload: dict[str, Any],
    key: str,
    context: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{context} {key} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{context} {key} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{context} {key} must be at most {maximum}")
    return number


def _run_logged(command: list[str], log_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "log_path": str(log_path.relative_to(ROOT)),
        "log_sha256": file_sha256(log_path),
    }


def _command_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return completed.stdout.strip() or completed.stderr.strip() or "unavailable"


def _cpu_model() -> str:
    # The browser runner records Node's os.cpus()[0].model. Prefer the same
    # source so Python's coarse Darwin value (for example, "arm") cannot make
    # an otherwise identical frontend report fail its environment binding.
    observed = _command_version(
        [
            "node",
            "-e",
            "process.stdout.write(require('os').cpus()[0]?.model ?? '')",
        ]
    )
    if observed != "unavailable":
        return observed
    observed = platform.processor().strip() or platform.uname().processor.strip()
    if observed:
        return observed
    if platform.system() == "Darwin":
        observed = _command_version(["sysctl", "-n", "machdep.cpu.brand_string"])
        if observed != "unavailable":
            return observed
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return "unknown"


def _execution_environment() -> dict[str, str | int]:
    """Return stable fields that bind timing and bundle measurements."""

    frontend = ROOT / "apps/web"
    try:
        lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
        playwright_version = str(lock["packages"]["node_modules/@playwright/test"]["version"])
    except (KeyError, OSError, TypeError, ValueError):
        playwright_version = "unavailable"
    chromium_executable = _command_version(
        [
            "node",
            "-e",
            (
                "const {chromium}=require('./apps/web/node_modules/"
                "playwright');process.stdout.write(chromium.executablePath())"
            ),
        ]
    )
    chromium_version = (
        _command_version([chromium_executable, "--version"])
        if chromium_executable != "unavailable"
        else "unavailable"
    )
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_model": _cpu_model(),
        "logical_cpu_count": os.cpu_count() or 0,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "node_version": _command_version(["node", "--version"]),
        "npm_version": _command_version(["npm", "--version"]),
        "playwright_version": playwright_version,
        "chromium_version": chromium_version,
    }


def _assert_recomputed_summary_matches(
    submitted: dict[str, Any], recomputed: dict[str, Any], *, context: str
) -> None:
    submitted_evidence = {
        key: value for key, value in submitted.items() if key != "generated_at"
    }
    recomputed_evidence = {
        key: value for key, value in recomputed.items() if key != "generated_at"
    }
    if submitted_evidence != recomputed_evidence:
        raise ValueError(f"{context} summary differs from raw validated evidence")


def _require_exact_keys(payload: dict[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    raise ValueError(
        f"{context} does not match the canonical schema; "
        f"missing={missing}, unexpected={unexpected}"
    )


def _require_digest(value: Any, *, context: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _require_nonempty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{context} must not contain leading or trailing whitespace")
    return value


def _require_timestamp(value: Any, *, context: str) -> datetime:
    raw = _require_nonempty_string(value, context=context)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{context} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")
    return parsed


def _require_full_git_sha(value: Any, *, context: str) -> str:
    commit = _require_nonempty_string(value, context=context)
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError(f"{context} must be a full lowercase Git SHA")
    return commit


def _frontend_manual_review_protocol(path: Path) -> dict[str, Any]:
    protocol = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise ValueError("frontend manual review protocol must be an object")
    _require_exact_keys(
        protocol,
        {
            "schema_version",
            "protocol_id",
            "bundle_schema_version",
            "status",
            "frozen_at",
            "description",
            "candidate_contract",
            "standards",
            "manual_thresholds",
            "state_roster",
            "test_profiles",
            "roles",
            "criteria",
            "atomic_check_requirements",
            "evidence_contract",
            "qualification_contract",
        },
        context="frontend manual review protocol",
    )
    if protocol.get("schema_version") != "firelens.frontend_manual_review_protocol.v1":
        raise ValueError("frontend manual review protocol uses an unsupported schema")
    if protocol.get("bundle_schema_version") != "firelens.frontend_manual_review_bundle.v1":
        raise ValueError("frontend manual review protocol names an unsupported bundle schema")
    if protocol.get("status") != "frozen":
        raise ValueError("frontend manual review protocol must be frozen")
    _require_nonempty_string(
        protocol.get("protocol_id"), context="frontend manual review protocol ID"
    )
    _require_nonempty_string(
        protocol.get("description"), context="frontend manual review protocol description"
    )
    _require_timestamp(
        protocol.get("frozen_at"), context="frontend manual review protocol frozen_at"
    )

    candidate_contract = protocol.get("candidate_contract")
    if not isinstance(candidate_contract, dict):
        raise ValueError("frontend manual review candidate contract must be an object")
    _require_exact_keys(
        candidate_contract,
        {
            "candidate_id_prefix",
            "commit_format",
            "allowed_target_url_schemes",
            "identity_endpoint_path",
            "identity_evidence_schema_version",
        },
        context="frontend manual review candidate contract",
    )
    if candidate_contract.get("candidate_id_prefix") != "firelens-v1-5-2:":
        raise ValueError("frontend manual review candidate ID prefix is not canonical")
    if candidate_contract.get("commit_format") != "full_lowercase_git_sha":
        raise ValueError("frontend manual review commit format is not canonical")
    if candidate_contract.get("allowed_target_url_schemes") != ["http", "https"]:
        raise ValueError("frontend manual review target URL schemes are not canonical")
    if candidate_contract.get("identity_endpoint_path") != "/api/v1/health/ready":
        raise ValueError("frontend manual review identity endpoint is not canonical")
    if (
        candidate_contract.get("identity_evidence_schema_version")
        != "firelens.frontend_candidate_identity_evidence.v1"
    ):
        raise ValueError("frontend manual review identity-evidence schema is not canonical")

    standards = protocol.get("standards")
    if not isinstance(standards, dict):
        raise ValueError("frontend manual review standards block must be an object")
    _require_exact_keys(
        standards,
        {"wcag_version", "conformance_level", "success_criteria"},
        context="frontend manual review standards",
    )
    if standards.get("wcag_version") != "2.2" or standards.get("conformance_level") != "AA":
        raise ValueError("frontend manual review must use WCAG 2.2 AA")
    success_criteria = standards.get("success_criteria")
    expected_success_criteria = [
        "1.3.1",
        "1.3.2",
        "1.4.1",
        "1.4.3",
        "1.4.4",
        "1.4.10",
        "1.4.11",
        "1.4.12",
        "2.1.1",
        "2.1.2",
        "2.4.3",
        "2.4.6",
        "2.4.7",
        "2.4.11",
        "2.5.1",
        "2.5.8",
        "3.3.1",
        "3.3.3",
        "4.1.2",
        "4.1.3",
    ]
    if (
        not isinstance(success_criteria, list)
        or [row.get("id") for row in success_criteria if isinstance(row, dict)]
        != expected_success_criteria
    ):
        raise ValueError(
            "frontend manual review WCAG success-criterion roster is not canonical"
        )
    for index, criterion in enumerate(success_criteria):
        if not isinstance(criterion, dict):
            raise ValueError(f"frontend manual review WCAG criterion {index} must be an object")
        _require_exact_keys(
            criterion, {"id", "name"}, context=f"frontend manual review WCAG criterion {index}"
        )
        _require_nonempty_string(
            criterion.get("name"), context=f"frontend manual review WCAG criterion {index} name"
        )

    expected_thresholds = {
        "normal_text_contrast_ratio_min": 4.5,
        "large_text_contrast_ratio_min": 3.0,
        "non_text_and_focus_contrast_ratio_min": 3.0,
        "browser_zoom_percent_required": 200,
        "reflow_width_css_px": 320,
        "horizontal_content_scroll_max_css_px": 0,
        "target_width_css_px_min": 24,
        "target_height_css_px_min": 24,
        "text_spacing": {
            "line_height_em_min": 1.5,
            "paragraph_spacing_em_min": 2.0,
            "letter_spacing_em_min": 0.12,
            "word_spacing_em_min": 0.16,
        },
    }
    if protocol.get("manual_thresholds") != expected_thresholds:
        raise ValueError("frontend manual review thresholds are not canonical")

    expected_states = [
        "idle",
        "grounded",
        "partial",
        "abstention",
        "provider_failure",
        "live",
        "mixed",
        "stale",
        "no_result",
        "partial_layer",
    ]
    if protocol.get("state_roster") != expected_states:
        raise ValueError("frontend manual review state roster is not canonical")

    profiles = protocol.get("test_profiles")
    expected_profile_ids = [
        "desktop_chromium_keyboard",
        "desktop_safari_voiceover",
        "mobile_safari_voiceover_touch",
        "product_safety_desktop_chromium",
        "product_safety_mobile_safari",
    ]
    if (
        not isinstance(profiles, list)
        or [row.get("id") for row in profiles if isinstance(row, dict)] != expected_profile_ids
    ):
        raise ValueError("frontend manual review test-profile roster is not canonical")
    profile_by_id: dict[str, dict[str, Any]] = {}
    for index, profile in enumerate(profiles):
        context = f"frontend manual review test profile {index}"
        if not isinstance(profile, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            profile,
            {
                "id",
                "required_role",
                "os_name",
                "browser_name",
                "assistive_technology",
                "input_methods",
                "viewport",
                "zoom_percentages",
                "reflow_widths_css_px",
                "reduced_motion",
            },
            context=context,
        )
        if profile.get("required_role") not in {
            "accessibility_specialist",
            "wildfire_product_safety_reviewer",
        }:
            raise ValueError(f"{context} has an invalid reviewer role")
        for key in ("os_name", "browser_name", "assistive_technology"):
            _require_nonempty_string(profile.get(key), context=f"{context} {key}")
        input_methods = profile.get("input_methods")
        if (
            not isinstance(input_methods, list)
            or not input_methods
            or len(input_methods) != len(set(input_methods))
            or any(method not in {"keyboard", "pointer", "touch"} for method in input_methods)
        ):
            raise ValueError(f"{context} input method roster is invalid")
        viewport = profile.get("viewport")
        if not isinstance(viewport, dict):
            raise ValueError(f"{context} viewport must be an object")
        _require_exact_keys(viewport, {"width", "height"}, context=f"{context} viewport")
        _strict_int(viewport, "width", f"{context} viewport", minimum=320)
        _strict_int(viewport, "height", f"{context} viewport", minimum=320)
        zoom_percentages = profile.get("zoom_percentages")
        reflow_widths = profile.get("reflow_widths_css_px")
        if (
            not isinstance(zoom_percentages, list)
            or not zoom_percentages
            or any(type(value) is not int or value < 100 for value in zoom_percentages)
            or not isinstance(reflow_widths, list)
            or any(type(value) is not int or value < 320 for value in reflow_widths)
        ):
            raise ValueError(f"{context} zoom/reflow roster is invalid")
        if profile.get("reduced_motion") != "reduce":
            raise ValueError(f"{context} must test reduced motion")
        profile_by_id[str(profile["id"])] = profile

    roles = protocol.get("roles")
    expected_roles = [
        "accessibility_specialist",
        "wildfire_product_safety_reviewer",
        "release_adjudicator",
    ]
    if (
        not isinstance(roles, list)
        or [row.get("id") for row in roles if isinstance(row, dict)] != expected_roles
    ):
        raise ValueError("frontend manual review protocol role roster is not canonical")
    for index, role in enumerate(roles):
        if not isinstance(role, dict):
            raise ValueError(f"frontend manual review protocol role {index} must be an object")
        _require_exact_keys(
            role,
            {"id", "responsibility"},
            context=f"frontend manual review protocol role {index}",
        )
        _require_nonempty_string(
            role.get("responsibility"),
            context=f"frontend manual review protocol role {role['id']} responsibility",
        )

    criteria = protocol.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("frontend manual review protocol must define criteria")
    criterion_ids: set[str] = set()
    atomic_ids: set[str] = set()
    for criterion_index, criterion in enumerate(criteria):
        context = f"frontend manual review protocol criterion {criterion_index}"
        if not isinstance(criterion, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            criterion,
            {"id", "track", "required_role", "atomic_checks"},
            context=context,
        )
        criterion_id = _require_nonempty_string(criterion.get("id"), context=f"{context} ID")
        if not re.fullmatch(r"(?:A11Y|SAFETY)_[A-Z0-9_]+", criterion_id):
            raise ValueError(f"{context} ID is not canonical")
        if criterion_id in criterion_ids:
            raise ValueError("frontend manual review protocol criterion IDs must be unique")
        criterion_ids.add(criterion_id)
        track = criterion.get("track")
        role = criterion.get("required_role")
        if (track, role) not in {
            ("accessibility", "accessibility_specialist"),
            ("product_safety", "wildfire_product_safety_reviewer"),
        }:
            raise ValueError(f"{context} has an invalid track/role assignment")
        checks = criterion.get("atomic_checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"{context} must define atomic checks")
        for check_index, check in enumerate(checks):
            check_context = f"{context} atomic check {check_index}"
            if not isinstance(check, dict):
                raise ValueError(f"{check_context} must be an object")
            _require_exact_keys(check, {"id", "instruction"}, context=check_context)
            check_id = _require_nonempty_string(check.get("id"), context=f"{check_context} ID")
            expected_prefix = "A11Y-" if track == "accessibility" else "SAFETY-"
            if not check_id.startswith(expected_prefix) or not re.fullmatch(
                r"[A-Z0-9]+-[A-Z0-9]+-[0-9]{2}", check_id
            ):
                raise ValueError(f"{check_context} ID is not canonical")
            if check_id in atomic_ids:
                raise ValueError("frontend manual review atomic-check IDs must be unique")
            atomic_ids.add(check_id)
            _require_nonempty_string(
                check.get("instruction"), context=f"{check_context} instruction"
            )

    atomic_requirements = protocol.get("atomic_check_requirements")
    if not isinstance(atomic_requirements, dict) or set(atomic_requirements) != atomic_ids:
        raise ValueError("frontend manual review atomic-check requirements are incomplete")
    known_success_criteria = set(expected_success_criteria)
    for check_id, requirement in atomic_requirements.items():
        context = f"frontend manual review atomic requirement {check_id}"
        if not isinstance(requirement, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            requirement,
            {"wcag_2_2_success_criteria", "required_profile_ids"},
            context=context,
        )
        wcag_ids = requirement.get("wcag_2_2_success_criteria")
        required_profiles = requirement.get("required_profile_ids")
        if (
            not isinstance(wcag_ids, list)
            or len(wcag_ids) != len(set(wcag_ids))
            or any(wcag_id not in known_success_criteria for wcag_id in wcag_ids)
        ):
            raise ValueError(f"{context} WCAG mapping is invalid")
        if (
            not isinstance(required_profiles, list)
            or not required_profiles
            or len(required_profiles) != len(set(required_profiles))
            or any(profile_id not in profile_by_id for profile_id in required_profiles)
        ):
            raise ValueError(f"{context} required profile roster is invalid")
        expected_role = (
            "accessibility_specialist"
            if str(check_id).startswith("A11Y-")
            else "wildfire_product_safety_reviewer"
        )
        if any(
            profile_by_id[str(profile_id)]["required_role"] != expected_role
            for profile_id in required_profiles
        ):
            raise ValueError(f"{context} references a profile owned by the wrong role")

    evidence_contract = protocol.get("evidence_contract")
    if not isinstance(evidence_contract, dict):
        raise ValueError("frontend manual review evidence contract must be an object")
    _require_exact_keys(
        evidence_contract,
        {
            "path_prefix",
            "require_sha256",
            "require_byte_count",
            "require_every_item_referenced",
            "allowed_media_types",
        },
        context="frontend manual review evidence contract",
    )
    if evidence_contract.get("path_prefix") != "evidence":
        raise ValueError("frontend manual review evidence path prefix is not canonical")
    for key in ("require_sha256", "require_byte_count", "require_every_item_referenced"):
        if evidence_contract.get(key) is not True:
            raise ValueError(f"frontend manual review evidence contract must enable {key}")
    media_types = evidence_contract.get("allowed_media_types")
    if not isinstance(media_types, dict) or not media_types:
        raise ValueError("frontend manual review media-type roster is missing")
    for media_type, extensions in media_types.items():
        if (
            not isinstance(media_type, str)
            or not media_type.strip()
            or not isinstance(extensions, list)
            or not extensions
            or any(
                not isinstance(extension, str) or not re.fullmatch(r"\.[a-z0-9]+", extension)
                for extension in extensions
            )
        ):
            raise ValueError("frontend manual review media-type roster is invalid")

    qualification = protocol.get("qualification_contract")
    expected_qualification = {
        "required_atomic_status": "pass",
        "open_findings_must_equal": 0,
        "require_distinct_people_for_all_roles": True,
        "require_exact_criterion_roster": True,
        "require_exact_atomic_check_roster": True,
    }
    if qualification != expected_qualification:
        raise ValueError("frontend manual review qualification contract is not canonical")
    return protocol


def _safe_frontend_review_evidence_path(
    bundle_path: Path, relative_value: Any, *, context: str
) -> tuple[Path, str]:
    relative = _require_nonempty_string(relative_value, context=f"{context} path")
    configured = Path(relative)
    if (
        configured.is_absolute()
        or ".." in configured.parts
        or configured.parts[:1] != ("evidence",)
        or configured.as_posix() != relative
    ):
        raise ValueError(f"{context} path must be a canonical relative path under evidence/")
    base = bundle_path.resolve().parent
    unresolved = base / configured
    current = base
    for part in configured.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{context} path cannot use symbolic links")
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"{context} retained file is missing") from error
    if not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError(f"{context} retained file must be a regular file inside the bundle")
    return resolved, relative


def validate_frontend_manual_review(
    bundle_path: Path,
    *,
    expected_commit: str,
    protocol_path: Path = FRONTEND_MANUAL_REVIEW_PROTOCOL,
) -> dict[str, Any]:
    """Validate and recompute the after-only manual frontend qualification."""

    if bundle_path.is_symlink():
        raise ValueError("frontend manual review bundle cannot be a symbolic link")
    try:
        raw_bundle = bundle_path.read_bytes()
    except OSError as error:
        raise ValueError("frontend manual review bundle is not readable") from error
    try:
        bundle = yaml.safe_load(raw_bundle.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError(
            "frontend manual review bundle is not valid UTF-8 YAML/JSON"
        ) from error
    if not isinstance(bundle, dict):
        raise ValueError("frontend manual review bundle must be an object")
    protocol = _frontend_manual_review_protocol(protocol_path)
    _require_exact_keys(
        bundle,
        {
            "schema_version",
            "protocol",
            "candidate",
            "review_window",
            "role_assignments",
            "test_environments",
            "evidence",
            "coverage",
            "criteria",
            "findings",
            "adjudication",
            "generated_at",
        },
        context="frontend manual review bundle",
    )
    if bundle.get("schema_version") != protocol["bundle_schema_version"]:
        raise ValueError("frontend manual review bundle uses an unsupported schema")
    generated_at = _require_timestamp(
        bundle.get("generated_at"), context="frontend manual review generated_at"
    )
    frozen_at = _require_timestamp(
        protocol.get("frozen_at"), context="frontend manual review protocol frozen_at"
    )

    protocol_binding = bundle.get("protocol")
    if not isinstance(protocol_binding, dict):
        raise ValueError("frontend manual review protocol binding must be an object")
    _require_exact_keys(
        protocol_binding,
        {"protocol_id", "protocol_sha256"},
        context="frontend manual review protocol binding",
    )
    if protocol_binding.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("frontend manual review bundle targets the wrong protocol")
    submitted_protocol_digest = _require_digest(
        protocol_binding.get("protocol_sha256"),
        context="frontend manual review protocol digest",
    )
    protocol_digest = file_sha256(protocol_path)
    if submitted_protocol_digest != protocol_digest:
        raise ValueError(
            "frontend manual review protocol digest does not match the frozen file"
        )

    commit = _require_full_git_sha(
        expected_commit, context="expected frontend candidate commit"
    )
    candidate = bundle.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("frontend manual review candidate binding must be an object")
    _require_exact_keys(
        candidate,
        {
            "candidate_id",
            "commit",
            "target_url",
            "build_verified_at",
            "identity_evidence_id",
        },
        context="frontend manual review candidate binding",
    )
    candidate_commit = _require_full_git_sha(
        candidate.get("commit"), context="frontend manual review candidate commit"
    )
    if candidate_commit != commit:
        raise ValueError("frontend manual review bundle targets the wrong candidate commit")
    candidate_id = _require_nonempty_string(
        candidate.get("candidate_id"), context="frontend manual review candidate ID"
    )
    expected_candidate_id = f"{protocol['candidate_contract']['candidate_id_prefix']}{commit}"
    if candidate_id != expected_candidate_id:
        raise ValueError(
            "frontend manual review candidate ID is not derived from its exact commit"
        )
    target_url = _require_nonempty_string(
        candidate.get("target_url"), context="frontend manual review target URL"
    )
    parsed_url = urlsplit(target_url)
    if (
        parsed_url.scheme not in protocol["candidate_contract"]["allowed_target_url_schemes"]
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
        or parsed_url.query
        or parsed_url.path not in {"", "/"}
    ):
        raise ValueError("frontend manual review target URL is not canonical")
    identity_evidence_id = _require_nonempty_string(
        candidate.get("identity_evidence_id"),
        context="frontend manual review candidate identity evidence ID",
    )
    build_verified_at = _require_timestamp(
        candidate.get("build_verified_at"), context="frontend candidate build_verified_at"
    )

    review_window = bundle.get("review_window")
    if not isinstance(review_window, dict):
        raise ValueError("frontend manual review window must be an object")
    _require_exact_keys(
        review_window,
        {"started_at", "completed_at"},
        context="frontend manual review window",
    )
    review_started_at = _require_timestamp(
        review_window.get("started_at"), context="frontend manual review started_at"
    )
    review_completed_at = _require_timestamp(
        review_window.get("completed_at"), context="frontend manual review completed_at"
    )
    if not (frozen_at <= build_verified_at <= review_started_at <= review_completed_at):
        raise ValueError(
            "frontend manual review protocol/build/review timestamp chain is invalid"
        )

    expected_role_ids = [row["id"] for row in protocol["roles"]]
    assignments = bundle.get("role_assignments")
    if not isinstance(assignments, list) or len(assignments) != len(expected_role_ids):
        raise ValueError("frontend manual review role assignment roster is incomplete")
    assignment_by_role: dict[str, dict[str, Any]] = {}
    reviewer_ids: set[str] = set()
    reviewer_names: set[str] = set()
    for index, assignment in enumerate(assignments):
        context = f"frontend manual review role assignment {index}"
        if not isinstance(assignment, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            assignment,
            {
                "role",
                "reviewer_id",
                "reviewer_name",
                "credentials",
                "assigned_at",
                "attested_at",
                "attestation",
            },
            context=context,
        )
        role = assignment.get("role")
        if role != expected_role_ids[index]:
            raise ValueError(
                "frontend manual review role assignments must use the exact roster"
            )
        reviewer_id = _require_nonempty_string(
            assignment.get("reviewer_id"), context=f"{context} reviewer ID"
        )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{2,127}", reviewer_id):
            raise ValueError(f"{context} reviewer ID is not canonical")
        reviewer_name = _named_frontend_reviewer(
            assignment.get("reviewer_name"), context=f"{context} reviewer name"
        )
        if reviewer_id.casefold() in reviewer_ids or reviewer_name.casefold() in reviewer_names:
            raise ValueError("frontend manual review roles must be assigned to distinct people")
        reviewer_ids.add(reviewer_id.casefold())
        reviewer_names.add(reviewer_name.casefold())
        _require_nonempty_string(
            assignment.get("credentials"), context=f"{context} credentials"
        )
        _require_nonempty_string(
            assignment.get("attestation"), context=f"{context} attestation"
        )
        assigned_at = _require_timestamp(
            assignment.get("assigned_at"), context=f"{context} assigned_at"
        )
        attested_at = _require_timestamp(
            assignment.get("attested_at"), context=f"{context} attested_at"
        )
        if not (frozen_at <= assigned_at <= review_started_at) or attested_at < assigned_at:
            raise ValueError(f"{context} timestamp chain is invalid")
        assignment_by_role[str(role)] = {
            **assignment,
            "assigned_at_parsed": assigned_at,
            "attested_at_parsed": attested_at,
        }

    test_environments = bundle.get("test_environments")
    protocol_profiles = protocol["test_profiles"]
    if not isinstance(test_environments, list) or len(test_environments) != len(
        protocol_profiles
    ):
        raise ValueError("frontend manual review test-environment roster is incomplete")
    environment_by_profile: dict[str, dict[str, Any]] = {}
    for index, (expected_profile, environment) in enumerate(
        zip(protocol_profiles, test_environments, strict=True)
    ):
        context = f"frontend manual review test environment {index}"
        if not isinstance(environment, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            environment,
            {
                "profile_id",
                "reviewer_id",
                "os_name",
                "os_version",
                "browser_name",
                "browser_version",
                "assistive_technology",
                "assistive_technology_version",
                "input_methods",
                "viewport",
                "zoom_percentages",
                "reflow_widths_css_px",
                "reduced_motion",
                "verified_at",
            },
            context=context,
        )
        profile_id = environment.get("profile_id")
        if profile_id != expected_profile["id"]:
            raise ValueError(
                "frontend manual review test environments must use the exact roster"
            )
        expected_reviewer = assignment_by_role[expected_profile["required_role"]]
        if environment.get("reviewer_id") != expected_reviewer["reviewer_id"]:
            raise ValueError(f"{context} is not bound to its designated reviewer")
        for key in (
            "os_name",
            "browser_name",
            "assistive_technology",
            "input_methods",
            "viewport",
            "zoom_percentages",
            "reflow_widths_css_px",
            "reduced_motion",
        ):
            if environment.get(key) != expected_profile[key]:
                raise ValueError(f"{context} {key} differs from the frozen profile")
        _require_nonempty_string(environment.get("os_version"), context=f"{context} OS version")
        _require_nonempty_string(
            environment.get("browser_version"), context=f"{context} browser version"
        )
        assistive_version = environment.get("assistive_technology_version")
        if expected_profile["assistive_technology"] == "none":
            if assistive_version is not None:
                raise ValueError(f"{context} cannot name an assistive-technology version")
        else:
            _require_nonempty_string(
                assistive_version, context=f"{context} assistive-technology version"
            )
        verified_at = _require_timestamp(
            environment.get("verified_at"), context=f"{context} verified_at"
        )
        if not (review_started_at <= verified_at <= review_completed_at):
            raise ValueError(f"{context} verification falls outside the review window")
        environment_by_profile[str(profile_id)] = {
            **environment,
            "verified_at_parsed": verified_at,
        }

    evidence_rows = bundle.get("evidence")
    if not isinstance(evidence_rows, list) or not evidence_rows:
        raise ValueError("frontend manual review must retain evidence")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_paths: set[str] = set()
    evidence_digests: set[str] = set()
    allowed_media_types = protocol["evidence_contract"]["allowed_media_types"]
    for index, evidence in enumerate(evidence_rows):
        context = f"frontend manual review evidence {index}"
        if not isinstance(evidence, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            evidence,
            {
                "evidence_id",
                "path",
                "sha256",
                "bytes",
                "media_type",
                "captured_at",
                "description",
                "profile_ids",
                "state_ids",
            },
            context=context,
        )
        evidence_id = _require_nonempty_string(
            evidence.get("evidence_id"), context=f"{context} ID"
        )
        if not re.fullmatch(r"EV-[0-9]{3,}", evidence_id) or evidence_id in evidence_by_id:
            raise ValueError("frontend manual review evidence IDs must be unique canonical IDs")
        path, relative_path = _safe_frontend_review_evidence_path(
            bundle_path, evidence.get("path"), context=context
        )
        if relative_path in evidence_paths:
            raise ValueError("frontend manual review evidence paths must be unique")
        evidence_paths.add(relative_path)
        digest = _require_digest(evidence.get("sha256"), context=f"{context} digest")
        if digest != file_sha256(path):
            raise ValueError(f"{context} digest does not match the retained file")
        if digest in evidence_digests:
            raise ValueError(
                "frontend manual review evidence cannot duplicate retained content"
            )
        evidence_digests.add(str(digest))
        byte_count = _strict_int(evidence, "bytes", context, minimum=1)
        if byte_count != path.stat().st_size:
            raise ValueError(f"{context} byte count does not match the retained file")
        media_type = _require_nonempty_string(
            evidence.get("media_type"), context=f"{context} media type"
        )
        if (
            media_type not in allowed_media_types
            or path.suffix.lower() not in allowed_media_types[media_type]
        ):
            raise ValueError(f"{context} media type does not match its file extension")
        captured_at = _require_timestamp(
            evidence.get("captured_at"), context=f"{context} captured_at"
        )
        if not (review_started_at <= captured_at <= review_completed_at):
            raise ValueError(f"{context} falls outside the review window")
        profile_ids = evidence.get("profile_ids")
        state_ids = evidence.get("state_ids")
        if (
            not isinstance(profile_ids, list)
            or not profile_ids
            or len(profile_ids) != len(set(profile_ids))
            or any(profile_id not in environment_by_profile for profile_id in profile_ids)
        ):
            raise ValueError(f"{context} profile roster is invalid")
        if (
            not isinstance(state_ids, list)
            or not state_ids
            or len(state_ids) != len(set(state_ids))
            or any(state_id not in protocol["state_roster"] for state_id in state_ids)
        ):
            raise ValueError(f"{context} state roster is invalid")
        if any(
            environment_by_profile[str(profile_id)]["verified_at_parsed"] > captured_at
            for profile_id in profile_ids
        ):
            raise ValueError(f"{context} predates its recorded test environment")
        _require_nonempty_string(evidence.get("description"), context=f"{context} description")
        evidence_by_id[evidence_id] = {
            **evidence,
            "captured_at_parsed": captured_at,
            "resolved_path": path,
        }

    identity_evidence = evidence_by_id.get(identity_evidence_id)
    if identity_evidence is None:
        raise ValueError("frontend manual review candidate identity evidence is missing")
    if identity_evidence["media_type"] != "application/json":
        raise ValueError("frontend manual review candidate identity evidence must be JSON")
    try:
        identity_payload = json.loads(
            identity_evidence["resolved_path"].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "frontend manual review candidate identity evidence is unreadable"
        ) from error
    if not isinstance(identity_payload, dict):
        raise ValueError("frontend manual review candidate identity evidence must be an object")
    _require_exact_keys(
        identity_payload,
        {"schema_version", "captured_at", "request", "response"},
        context="frontend manual review candidate identity evidence",
    )
    if (
        identity_payload.get("schema_version")
        != protocol["candidate_contract"]["identity_evidence_schema_version"]
    ):
        raise ValueError("frontend manual review candidate identity evidence schema is invalid")
    identity_captured_at = _require_timestamp(
        identity_payload.get("captured_at"),
        context="frontend manual review candidate identity evidence captured_at",
    )
    if identity_captured_at != identity_evidence["captured_at_parsed"]:
        raise ValueError("frontend manual review candidate identity timestamps differ")
    identity_request = identity_payload.get("request")
    identity_response = identity_payload.get("response")
    if not isinstance(identity_request, dict) or not isinstance(identity_response, dict):
        raise ValueError(
            "frontend manual review candidate identity request/response is invalid"
        )
    _require_exact_keys(
        identity_request,
        {"method", "url"},
        context="frontend manual review candidate identity request",
    )
    expected_identity_url = (
        target_url.rstrip("/") + protocol["candidate_contract"]["identity_endpoint_path"]
    )
    if identity_request != {"method": "GET", "url": expected_identity_url}:
        raise ValueError(
            "frontend manual review candidate identity request targets the wrong URL"
        )
    _require_exact_keys(
        identity_response,
        {"status_code", "content_type", "candidate_id", "build_commit"},
        context="frontend manual review candidate identity response",
    )
    if (
        identity_response.get("status_code") != 200
        or identity_response.get("content_type") != "application/json"
        or identity_response.get("candidate_id") != candidate_id
        or identity_response.get("build_commit") != commit
    ):
        raise ValueError(
            "frontend manual review candidate URL does not prove the exact identity"
        )

    coverage_rows = bundle.get("coverage")
    expected_coverage = [
        (profile["id"], state_id)
        for profile in protocol_profiles
        for state_id in protocol["state_roster"]
    ]
    if not isinstance(coverage_rows, list) or len(coverage_rows) != len(expected_coverage):
        raise ValueError(
            "frontend manual review environment/state coverage roster is incomplete"
        )
    coverage_by_id: dict[str, dict[str, Any]] = {}
    coverage_order: list[str] = []
    coverage_track_statuses: dict[str, list[str]] = {
        "accessibility": [],
        "product_safety": [],
    }
    role_latest_coverage: dict[str, datetime] = {}
    used_evidence_ids: set[str] = set()
    for index, ((expected_profile_id, expected_state_id), coverage) in enumerate(
        zip(expected_coverage, coverage_rows, strict=True)
    ):
        context = f"frontend manual review coverage {index}"
        if not isinstance(coverage, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            coverage,
            {
                "profile_id",
                "state_id",
                "status",
                "reviewer_id",
                "observed_at",
                "evidence_ids",
                "notes",
            },
            context=context,
        )
        if (
            coverage.get("profile_id") != expected_profile_id
            or coverage.get("state_id") != expected_state_id
        ):
            raise ValueError(
                "frontend manual review environment/state coverage differs from the frozen matrix"
            )
        expected_profile = next(
            profile for profile in protocol_profiles if profile["id"] == expected_profile_id
        )
        expected_reviewer = assignment_by_role[expected_profile["required_role"]]
        if coverage.get("reviewer_id") != expected_reviewer["reviewer_id"]:
            raise ValueError(f"{context} was not performed by its designated reviewer")
        status = coverage.get("status")
        if status not in {"pass", "fail", "not_tested"}:
            raise ValueError(f"{context} status is invalid")
        evidence_ids = coverage.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
        ):
            raise ValueError(f"{context} must reference unique retained evidence")
        if any(
            expected_profile_id not in evidence_by_id[str(evidence_id)]["profile_ids"]
            or expected_state_id not in evidence_by_id[str(evidence_id)]["state_ids"]
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} evidence does not bind its profile and state")
        observed_at = _require_timestamp(
            coverage.get("observed_at"), context=f"{context} observed_at"
        )
        if not (
            environment_by_profile[expected_profile_id]["verified_at_parsed"]
            <= observed_at
            <= review_completed_at
        ) or any(
            evidence_by_id[str(evidence_id)]["captured_at_parsed"] > observed_at
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} evidence/observation timestamp chain is invalid")
        _require_nonempty_string(coverage.get("notes"), context=f"{context} notes")
        coverage_id = f"{expected_profile_id}/{expected_state_id}"
        coverage_order.append(coverage_id)
        coverage_by_id[coverage_id] = {
            **coverage,
            "observed_at_parsed": observed_at,
            "track": (
                "accessibility"
                if expected_profile["required_role"] == "accessibility_specialist"
                else "product_safety"
            ),
        }
        coverage_track_statuses[coverage_by_id[coverage_id]["track"]].append(str(status))
        profile_role = str(expected_profile["required_role"])
        role_latest_coverage[profile_role] = max(
            observed_at, role_latest_coverage.get(profile_role, observed_at)
        )
        used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)

    protocol_criteria = protocol["criteria"]
    submitted_criteria = bundle.get("criteria")
    if not isinstance(submitted_criteria, list) or len(submitted_criteria) != len(
        protocol_criteria
    ):
        raise ValueError("frontend manual review criterion roster is incomplete")
    checks_by_id: dict[str, dict[str, Any]] = {}
    check_order: list[str] = []
    criterion_order: list[str] = []
    role_latest_check: dict[str, datetime] = {}
    track_statuses: dict[str, list[str]] = {"accessibility": [], "product_safety": []}
    for criterion_index, (expected_criterion, submitted_criterion) in enumerate(
        zip(protocol_criteria, submitted_criteria, strict=True)
    ):
        context = f"frontend manual review criterion {criterion_index}"
        if not isinstance(submitted_criterion, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            submitted_criterion, {"criterion_id", "atomic_checks"}, context=context
        )
        criterion_id = submitted_criterion.get("criterion_id")
        if criterion_id != expected_criterion["id"]:
            raise ValueError(
                "frontend manual review criterion roster differs from the protocol"
            )
        criterion_order.append(str(criterion_id))
        expected_checks = expected_criterion["atomic_checks"]
        submitted_checks = submitted_criterion.get("atomic_checks")
        if not isinstance(submitted_checks, list) or len(submitted_checks) != len(
            expected_checks
        ):
            raise ValueError(f"{context} atomic-check roster is incomplete")
        required_role = expected_criterion["required_role"]
        required_reviewer = assignment_by_role[required_role]
        for check_index, (expected_check, submitted_check) in enumerate(
            zip(expected_checks, submitted_checks, strict=True)
        ):
            check_context = f"{context} atomic check {check_index}"
            if not isinstance(submitted_check, dict):
                raise ValueError(f"{check_context} must be an object")
            _require_exact_keys(
                submitted_check,
                {"check_id", "status", "reviewer_id", "reviewed_at", "evidence_ids", "notes"},
                context=check_context,
            )
            check_id = submitted_check.get("check_id")
            if check_id != expected_check["id"] or check_id in checks_by_id:
                raise ValueError(
                    "frontend manual review atomic-check roster differs from the protocol"
                )
            status = submitted_check.get("status")
            if status not in {"pass", "fail", "not_tested"}:
                raise ValueError(f"{check_context} status is invalid")
            reviewer_id = submitted_check.get("reviewer_id")
            if reviewer_id != required_reviewer["reviewer_id"]:
                raise ValueError(
                    f"{check_context} was not performed by its designated specialist"
                )
            reviewed_at = _require_timestamp(
                submitted_check.get("reviewed_at"), context=f"{check_context} reviewed_at"
            )
            evidence_ids = submitted_check.get("evidence_ids")
            if (
                not isinstance(evidence_ids, list)
                or not evidence_ids
                or len(evidence_ids) != len(set(evidence_ids))
                or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
            ):
                raise ValueError(f"{check_context} must reference unique retained evidence")
            latest_evidence = max(
                evidence_by_id[str(evidence_id)]["captured_at_parsed"]
                for evidence_id in evidence_ids
            )
            evidenced_profiles = {
                str(profile_id)
                for evidence_id in evidence_ids
                for profile_id in evidence_by_id[str(evidence_id)]["profile_ids"]
            }
            required_profiles = set(
                protocol["atomic_check_requirements"][str(check_id)]["required_profile_ids"]
            )
            if not required_profiles.issubset(evidenced_profiles):
                raise ValueError(
                    f"{check_context} evidence omits required test profiles: "
                    f"{sorted(required_profiles - evidenced_profiles)}"
                )
            if not (latest_evidence <= reviewed_at <= review_completed_at):
                raise ValueError(f"{check_context} evidence/review timestamp chain is invalid")
            if reviewed_at < required_reviewer["assigned_at_parsed"]:
                raise ValueError(f"{check_context} predates its reviewer assignment")
            _require_nonempty_string(
                submitted_check.get("notes"), context=f"{check_context} notes"
            )
            role_latest_check[required_role] = max(
                reviewed_at, role_latest_check.get(required_role, reviewed_at)
            )
            used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)
            check_order.append(str(check_id))
            track_statuses[expected_criterion["track"]].append(str(status))
            checks_by_id[str(check_id)] = {
                **submitted_check,
                "reviewed_at_parsed": reviewed_at,
                "track": expected_criterion["track"],
            }

    for role in ("accessibility_specialist", "wildfire_product_safety_reviewer"):
        assignment = assignment_by_role[role]
        latest_activity = max(role_latest_check[role], role_latest_coverage[role])
        if not (latest_activity <= assignment["attested_at_parsed"] <= review_completed_at):
            raise ValueError(f"frontend manual review {role} attestation chain is invalid")

    findings = bundle.get("findings")
    if not isinstance(findings, list):
        raise ValueError("frontend manual review findings must be a list")
    finding_ids: set[str] = set()
    open_findings_by_target: Counter[tuple[str, str]] = Counter()
    open_finding_count = 0
    for index, finding in enumerate(findings):
        context = f"frontend manual review finding {index}"
        if not isinstance(finding, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            finding,
            {
                "finding_id",
                "target_type",
                "target_id",
                "severity",
                "status",
                "opened_at",
                "resolved_at",
                "owner_id",
                "resolution",
                "evidence_ids",
            },
            context=context,
        )
        finding_id = _require_nonempty_string(
            finding.get("finding_id"), context=f"{context} ID"
        )
        if not re.fullmatch(r"F-[0-9]{3,}", finding_id) or finding_id in finding_ids:
            raise ValueError("frontend manual review finding IDs must be unique canonical IDs")
        finding_ids.add(finding_id)
        target_type = finding.get("target_type")
        target_id = finding.get("target_id")
        if target_type == "atomic_check":
            if target_id not in checks_by_id:
                raise ValueError(f"{context} references an unknown atomic check")
            target_reviewed_at = checks_by_id[str(target_id)]["reviewed_at_parsed"]
        elif target_type == "environment_state":
            if target_id not in coverage_by_id:
                raise ValueError(f"{context} references unknown environment/state coverage")
            target_reviewed_at = coverage_by_id[str(target_id)]["observed_at_parsed"]
        else:
            raise ValueError(f"{context} target type is invalid")
        if finding.get("severity") not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{context} severity is invalid")
        status = finding.get("status")
        if status not in {"open", "resolved"}:
            raise ValueError(f"{context} status is invalid")
        owner_id = _require_nonempty_string(
            finding.get("owner_id"), context=f"{context} owner ID"
        )
        if owner_id.casefold() not in reviewer_ids:
            raise ValueError(f"{context} owner is not in the named role registry")
        evidence_ids = finding.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
        ):
            raise ValueError(f"{context} must reference unique retained evidence")
        used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)
        opened_at = _require_timestamp(finding.get("opened_at"), context=f"{context} opened_at")
        if not (review_started_at <= opened_at <= target_reviewed_at):
            raise ValueError(f"{context} opened/reviewed timestamp chain is invalid")
        if any(
            evidence_by_id[str(evidence_id)]["captured_at_parsed"] > target_reviewed_at
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} references evidence captured after final review")
        if status == "open":
            if finding.get("resolved_at") is not None or finding.get("resolution") is not None:
                raise ValueError(f"{context} open finding cannot claim a resolution")
            open_findings_by_target[(str(target_type), str(target_id))] += 1
            open_finding_count += 1
        else:
            resolved_at = _require_timestamp(
                finding.get("resolved_at"), context=f"{context} resolved_at"
            )
            if not (opened_at <= resolved_at <= target_reviewed_at):
                raise ValueError(f"{context} resolution/review timestamp chain is invalid")
            _require_nonempty_string(finding.get("resolution"), context=f"{context} resolution")

    for check_id, check in checks_by_id.items():
        has_open_finding = open_findings_by_target[("atomic_check", check_id)] > 0
        if check["status"] == "pass" and has_open_finding:
            raise ValueError(
                f"frontend manual review check {check_id} passes with an open finding"
            )
        if check["status"] != "pass" and not has_open_finding:
            raise ValueError(
                f"frontend manual review non-passing check {check_id} requires an open finding"
            )
    for coverage_id, coverage in coverage_by_id.items():
        has_open_finding = open_findings_by_target[("environment_state", coverage_id)] > 0
        if coverage["status"] == "pass" and has_open_finding:
            raise ValueError(
                f"frontend manual review coverage {coverage_id} passes with an open finding"
            )
        if coverage["status"] != "pass" and not has_open_finding:
            raise ValueError(
                f"frontend manual review non-passing coverage {coverage_id} requires an open finding"
            )

    if used_evidence_ids != set(evidence_by_id):
        unused = sorted(set(evidence_by_id) - used_evidence_ids)
        raise ValueError(f"frontend manual review contains unused evidence padding: {unused}")

    accessibility_qualified = all(
        status == "pass"
        for status in [
            *track_statuses["accessibility"],
            *coverage_track_statuses["accessibility"],
        ]
    )
    product_safety_qualified = all(
        status == "pass"
        for status in [
            *track_statuses["product_safety"],
            *coverage_track_statuses["product_safety"],
        ]
    )
    qualified = accessibility_qualified and product_safety_qualified and open_finding_count == 0

    adjudication = bundle.get("adjudication")
    if not isinstance(adjudication, dict):
        raise ValueError("frontend manual review adjudication must be an object")
    _require_exact_keys(
        adjudication,
        {
            "adjudicator_id",
            "decision",
            "decided_at",
            "accessibility_qualified",
            "product_safety_qualified",
            "open_finding_count",
            "criterion_ids",
            "atomic_check_ids",
            "test_profile_ids",
            "state_ids",
            "coverage_ids",
            "evidence_ids",
            "attestation",
        },
        context="frontend manual review adjudication",
    )
    adjudicator = assignment_by_role["release_adjudicator"]
    if adjudication.get("adjudicator_id") != adjudicator["reviewer_id"]:
        raise ValueError(
            "frontend manual review decision was not made by the release adjudicator"
        )
    decided_at = _require_timestamp(
        adjudication.get("decided_at"), context="frontend manual review adjudication decided_at"
    )
    if not (
        review_completed_at <= decided_at <= adjudicator["attested_at_parsed"] <= generated_at
    ):
        raise ValueError("frontend manual review adjudication timestamp chain is invalid")
    expected_decision = "qualified" if qualified else "not_qualified"
    if adjudication.get("decision") != expected_decision:
        raise ValueError("frontend manual review decision differs from recomputed evidence")
    submitted_accessibility = _strict_bool(
        adjudication,
        "accessibility_qualified",
        "frontend manual review adjudication",
    )
    submitted_product_safety = _strict_bool(
        adjudication,
        "product_safety_qualified",
        "frontend manual review adjudication",
    )
    submitted_open_findings = _strict_int(
        adjudication,
        "open_finding_count",
        "frontend manual review adjudication",
        minimum=0,
    )
    if (
        submitted_accessibility != accessibility_qualified
        or submitted_product_safety != product_safety_qualified
        or submitted_open_findings != open_finding_count
    ):
        raise ValueError(
            "frontend manual review adjudication summary differs from raw evidence"
        )
    if adjudication.get("criterion_ids") != criterion_order:
        raise ValueError("frontend manual review adjudication omits or reorders criteria")
    if adjudication.get("atomic_check_ids") != check_order:
        raise ValueError("frontend manual review adjudication omits or reorders atomic checks")
    if adjudication.get("test_profile_ids") != list(environment_by_profile):
        raise ValueError("frontend manual review adjudication omits or reorders test profiles")
    if adjudication.get("state_ids") != protocol["state_roster"]:
        raise ValueError("frontend manual review adjudication omits or reorders states")
    if adjudication.get("coverage_ids") != coverage_order:
        raise ValueError("frontend manual review adjudication omits or reorders coverage")
    if adjudication.get("evidence_ids") != list(evidence_by_id):
        raise ValueError("frontend manual review adjudication omits or reorders evidence")
    _require_nonempty_string(
        adjudication.get("attestation"),
        context="frontend manual review adjudication attestation",
    )

    return {
        "status": "complete",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_digest,
        "bundle_sha256": hashlib.sha256(raw_bundle).hexdigest(),
        "candidate_id": candidate_id,
        "commit": commit,
        "target_url": target_url,
        "build_verified_at": candidate["build_verified_at"],
        "review_started_at": review_window["started_at"],
        "review_completed_at": review_window["completed_at"],
        "decided_at": adjudication["decided_at"],
        "generated_at": bundle["generated_at"],
        "roles": [
            {
                "role": assignment["role"],
                "reviewer_id": assignment["reviewer_id"],
                "reviewer_name": assignment["reviewer_name"],
                "attested_at": assignment["attested_at"],
            }
            for assignment in assignments
        ],
        "criterion_ids": criterion_order,
        "atomic_check_ids": check_order,
        "test_profile_ids": list(environment_by_profile),
        "state_ids": protocol["state_roster"],
        "coverage_ids": coverage_order,
        "criterion_count": len(criterion_order),
        "atomic_check_count": len(check_order),
        "test_profile_count": len(environment_by_profile),
        "state_count": len(protocol["state_roster"]),
        "coverage_count": len(coverage_by_id),
        "evidence_count": len(evidence_by_id),
        "evidence_manifest": [
            {
                "evidence_id": evidence["evidence_id"],
                "path": evidence["path"],
                "sha256": evidence["sha256"],
                "bytes": evidence["bytes"],
                "media_type": evidence["media_type"],
                "profile_ids": evidence["profile_ids"],
                "state_ids": evidence["state_ids"],
            }
            for evidence in evidence_rows
        ],
        "finding_count": len(findings),
        "open_finding_count": open_finding_count,
        "accessibility_qualified": accessibility_qualified,
        "product_safety_qualified": product_safety_qualified,
        "qualified": qualified,
    }


def _sorted_unique_strings(
    value: Any,
    *,
    context: str,
    minimum: int = 1,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{context} must contain at least {minimum} values")
    parsed = [
        _require_nonempty_string(item, context=f"{context} item {index}")
        for index, item in enumerate(value)
    ]
    if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
        raise ValueError(f"{context} must be sorted and unique")
    return parsed


def _semantic_development_registry_payload(
    registry: dict[str, Any],
) -> dict[str, Any]:
    _require_exact_keys(
        registry,
        {
            "registry_version",
            "registry_id",
            "frozen_at",
            "dataset_roster_sha256",
            "datasets",
            "source_id_sha256s",
            "source_roster_sha256",
            "question_family_ids",
            "question_family_roster_sha256",
        },
        context="semantic development exposure registry",
    )
    if registry.get("registry_version") != "firelens_semantic_development_exposure_registry.v1":
        raise ValueError("semantic development exposure registry uses an unsupported version")
    _require_nonempty_string(
        registry.get("registry_id"), context="semantic development registry ID"
    )
    _require_timestamp(
        registry.get("frozen_at"), context="semantic development registry frozen_at"
    )
    _require_digest(
        registry.get("dataset_roster_sha256"),
        context="semantic development dataset-roster commitment",
    )
    _require_digest(
        registry.get("source_roster_sha256"),
        context="semantic development source-roster commitment",
    )
    _require_digest(
        registry.get("question_family_roster_sha256"),
        context="semantic development question-family-roster commitment",
    )
    datasets = registry.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("semantic development registry requires dataset exposures")
    dataset_ids: list[str] = []
    aggregate_sources: set[str] = set()
    aggregate_families: set[str] = set()
    for index, row in enumerate(datasets):
        if not isinstance(row, dict):
            raise ValueError(f"semantic development dataset {index} must be an object")
        _require_exact_keys(
            row,
            {
                "dataset_id",
                "dataset_sha256",
                "source_id_sha256s",
                "question_family_ids",
            },
            context=f"semantic development dataset {index}",
        )
        dataset_ids.append(
            _require_nonempty_string(row.get("dataset_id"), context="development dataset ID")
        )
        _require_digest(
            row.get("dataset_sha256"), context=f"development dataset {index} digest"
        )
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            context=f"semantic development dataset {index} source roster",
            minimum=0,
        )
        for source in sources:
            _require_digest(
                source, context=f"semantic development dataset {index} source ID commitment"
            )
        families = _sorted_unique_strings(
            row.get("question_family_ids"),
            context=f"semantic development dataset {index} question-family roster",
            minimum=1,
        )
        aggregate_sources.update(sources)
        aggregate_families.update(families)
    if dataset_ids != sorted(dataset_ids) or len(dataset_ids) != len(set(dataset_ids)):
        raise ValueError("semantic development dataset roster must be sorted and unique")
    if registry["dataset_roster_sha256"] != _sha256_json(datasets):
        raise ValueError("semantic development dataset-roster digest is inconsistent")
    source_roster = _sorted_unique_strings(
        registry.get("source_id_sha256s"),
        context="semantic development source roster",
        minimum=1,
    )
    for source in source_roster:
        _require_digest(source, context="semantic development source ID commitment")
    if source_roster != sorted(aggregate_sources):
        raise ValueError("semantic development source roster differs from dataset exposures")
    if registry["source_roster_sha256"] != _sha256_json(source_roster):
        raise ValueError("semantic development source-roster digest is inconsistent")
    family_roster = _sorted_unique_strings(
        registry.get("question_family_ids"),
        context="semantic development question-family roster",
        minimum=5,
    )
    if family_roster != sorted(aggregate_families):
        raise ValueError(
            "semantic development question-family roster differs from dataset exposures"
        )
    if registry["question_family_roster_sha256"] != _sha256_json(family_roster):
        raise ValueError("semantic development question-family-roster digest is inconsistent")
    return registry


def _semantic_development_registry(path: Path) -> dict[str, Any]:
    registry = _read_report(path)
    if registry is None:
        raise ValueError("semantic development exposure registry is missing")
    return _semantic_development_registry_payload(registry)


def _semantic_holdout_manifest_payload(
    manifest: dict[str, Any],
    *,
    development_registry: dict[str, Any],
    development_registry_sha256: str,
) -> dict[str, Any]:
    _require_exact_keys(
        manifest,
        {
            "manifest_version",
            "dataset_sha256",
            "case_roster_sha256",
            "case_count",
            "case_roster",
            "source_id_sha256s",
            "source_roster_sha256",
            "question_family_ids",
            "question_family_roster_sha256",
            "question_family_distribution",
            "development_registry_id",
            "development_registry_sha256",
            "disjointness_audit",
            "frozen_before_candidate",
            "double_review_required",
            "frozen_at",
        },
        context="semantic holdout manifest",
    )
    if manifest.get("manifest_version") != "firelens_semantic_holdout_manifest.v3":
        raise ValueError("semantic holdout manifest uses an unsupported version")
    _require_digest(
        manifest.get("dataset_sha256"), context="semantic holdout dataset commitment"
    )
    _require_digest(
        manifest.get("case_roster_sha256"), context="semantic holdout case-roster commitment"
    )
    _require_digest(
        manifest.get("source_roster_sha256"),
        context="semantic holdout source-roster commitment",
    )
    _require_digest(
        manifest.get("question_family_roster_sha256"),
        context="semantic holdout question-family-roster commitment",
    )
    registry_digest = _require_digest(
        development_registry_sha256, context="semantic development registry digest"
    )
    if manifest.get("development_registry_id") != development_registry["registry_id"]:
        raise ValueError("semantic holdout manifest uses the wrong development registry")
    if manifest.get("development_registry_sha256") != registry_digest:
        raise ValueError("semantic holdout manifest does not bind the development registry")
    frozen_at = _require_timestamp(
        manifest.get("frozen_at"), context="semantic holdout frozen_at"
    )
    for key in ("frozen_before_candidate", "double_review_required"):
        if not _strict_bool(manifest, key, "semantic holdout manifest"):
            raise ValueError(f"semantic holdout manifest requires {key}")
    case_count = _strict_int(manifest, "case_count", "semantic holdout manifest", minimum=25)
    roster = manifest.get("case_roster")
    if not isinstance(roster, list) or len(roster) != case_count:
        raise ValueError("semantic holdout manifest case roster differs from case_count")
    case_ids: list[str] = []
    aggregate_sources: set[str] = set()
    family_counts: Counter[str] = Counter()
    for index, row in enumerate(roster):
        if not isinstance(row, dict):
            raise ValueError(f"semantic holdout roster row {index} must be an object")
        _require_exact_keys(
            row,
            {
                "case_id",
                "input_sha256",
                "source_id_sha256s",
                "question_family_id",
            },
            context=f"semantic holdout roster row {index}",
        )
        case_ids.append(
            _require_nonempty_string(
                row.get("case_id"), context=f"semantic holdout roster row {index} case_id"
            )
        )
        _require_digest(
            row.get("input_sha256"),
            context=f"semantic holdout roster row {index} input_sha256",
        )
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            context=f"semantic holdout roster row {index} source roster",
        )
        for source in sources:
            _require_digest(
                source, context=f"semantic holdout roster row {index} source ID commitment"
            )
        family = _require_nonempty_string(
            row.get("question_family_id"),
            context=f"semantic holdout roster row {index} question family",
        )
        aggregate_sources.update(sources)
        family_counts[family] += 1
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError("semantic holdout manifest case roster must use unique canonical IDs")
    if manifest["case_roster_sha256"] != _sha256_json(roster):
        raise ValueError("semantic holdout manifest case-roster digest does not match its rows")
    source_roster = _sorted_unique_strings(
        manifest.get("source_id_sha256s"), context="semantic holdout source roster"
    )
    for source in source_roster:
        _require_digest(source, context="semantic holdout source ID commitment")
    if source_roster != sorted(aggregate_sources):
        raise ValueError("semantic holdout source roster differs from case-level sources")
    if manifest["source_roster_sha256"] != _sha256_json(source_roster):
        raise ValueError("semantic holdout source-roster digest is inconsistent")
    family_roster = _sorted_unique_strings(
        manifest.get("question_family_ids"),
        context="semantic holdout question-family roster",
        minimum=5,
    )
    if family_roster != sorted(family_counts):
        raise ValueError("semantic holdout question-family roster differs from cases")
    if manifest["question_family_roster_sha256"] != _sha256_json(family_roster):
        raise ValueError("semantic holdout question-family-roster digest is inconsistent")
    family_distribution = manifest.get("question_family_distribution")
    if not isinstance(family_distribution, dict) or len(family_distribution) < 5:
        raise ValueError("semantic holdout manifest requires at least five question families")
    valid_family_counts = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 1
        for value in family_distribution.values()
    )
    if not valid_family_counts or family_distribution != dict(sorted(family_counts.items())):
        raise ValueError("semantic holdout family distribution does not match its cases")

    audit = manifest.get("disjointness_audit")
    if not isinstance(audit, dict):
        raise ValueError("semantic holdout disjointness audit must be an object")
    _require_exact_keys(
        audit,
        {
            "audit_version",
            "audited_at",
            "development_registry_sha256",
            "development_source_roster_sha256",
            "development_question_family_roster_sha256",
            "holdout_source_roster_sha256",
            "holdout_question_family_roster_sha256",
            "source_overlap_id_sha256s",
            "question_family_overlap_ids",
            "source_disjoint_from_development",
            "question_family_disjoint_from_development",
        },
        context="semantic holdout disjointness audit",
    )
    if audit.get("audit_version") != "firelens_semantic_disjointness_audit.v1":
        raise ValueError("semantic holdout disjointness audit uses an unsupported version")
    audited_at = _require_timestamp(
        audit.get("audited_at"), context="semantic holdout disjointness audited_at"
    )
    development_frozen_at = _require_timestamp(
        development_registry.get("frozen_at"),
        context="semantic development registry frozen_at",
    )
    if audited_at < development_frozen_at or audited_at > frozen_at:
        raise ValueError("semantic holdout disjointness audit timestamps are out of order")
    expected_audit_digests = {
        "development_registry_sha256": registry_digest,
        "development_source_roster_sha256": development_registry["source_roster_sha256"],
        "development_question_family_roster_sha256": development_registry[
            "question_family_roster_sha256"
        ],
        "holdout_source_roster_sha256": manifest["source_roster_sha256"],
        "holdout_question_family_roster_sha256": manifest["question_family_roster_sha256"],
    }
    for key, expected in expected_audit_digests.items():
        _require_digest(audit.get(key), context=f"semantic disjointness audit {key}")
        if audit[key] != expected:
            raise ValueError(f"semantic holdout disjointness audit has the wrong {key}")
    source_overlap = sorted(set(source_roster) & set(development_registry["source_id_sha256s"]))
    family_overlap = sorted(
        set(family_roster) & set(development_registry["question_family_ids"])
    )
    if audit.get("source_overlap_id_sha256s") != source_overlap:
        raise ValueError("semantic holdout source-overlap audit is inconsistent")
    if audit.get("question_family_overlap_ids") != family_overlap:
        raise ValueError("semantic holdout question-family-overlap audit is inconsistent")
    source_disjoint = _strict_bool(
        audit, "source_disjoint_from_development", "semantic holdout disjointness audit"
    )
    family_disjoint = _strict_bool(
        audit,
        "question_family_disjoint_from_development",
        "semantic holdout disjointness audit",
    )
    if source_disjoint != (not source_overlap) or family_disjoint != (not family_overlap):
        raise ValueError("semantic holdout disjointness flags disagree with recomputed overlap")
    if not source_disjoint or not family_disjoint:
        raise ValueError("semantic holdout is not source and question-family disjoint")
    return manifest


def _semantic_holdout_manifest(
    path: Path,
    *,
    development_registry: dict[str, Any],
    development_registry_sha256: str,
) -> dict[str, Any]:
    manifest = _read_report(path)
    if manifest is None:
        raise ValueError("semantic holdout manifest is missing")
    return _semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256=development_registry_sha256,
    )


def _semantic_holdout_candidate_report(
    report: dict[str, Any],
    *,
    manifest: dict[str, Any],
    dataset_manifest_sha256: str,
) -> dict[str, Any]:
    _require_exact_keys(
        report,
        {
            "report_version",
            "candidate_id",
            "candidate_identity_sha256",
            "generated_at",
            "commit",
            "corpus_sha256",
            "vector_matrix_sha256",
            "document_context_sha256",
            "repairs_sha256",
            "configuration_sha256",
            "dataset_sha256",
            "dataset_manifest_sha256",
            "case_count",
            "cases",
        },
        context="semantic holdout candidate report",
    )
    if report.get("report_version") != "firelens_semantic_holdout_report.v1":
        raise ValueError("semantic holdout candidate report uses an unsupported version")
    candidate_id = _require_nonempty_string(
        report.get("candidate_id"), context="semantic holdout candidate_id"
    )
    generated_at = _require_timestamp(
        report.get("generated_at"), context="semantic holdout report generated_at"
    )
    if (
        _require_timestamp(
            manifest.get("frozen_at"), context="semantic holdout manifest frozen_at"
        )
        >= generated_at
    ):
        raise ValueError("semantic holdout manifest was not frozen before candidate generation")
    commit = _require_nonempty_string(
        report.get("commit"), context="semantic holdout candidate commit"
    )
    if len(commit) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in commit
    ):
        raise ValueError("semantic holdout candidate commit must be a Git object ID")
    for key in (
        "candidate_identity_sha256",
        "corpus_sha256",
        "vector_matrix_sha256",
        "repairs_sha256",
        "configuration_sha256",
        "dataset_sha256",
        "dataset_manifest_sha256",
    ):
        _require_digest(report.get(key), context=f"semantic holdout report {key}")
    _require_digest(
        report.get("document_context_sha256"),
        context="semantic holdout report document_context_sha256",
        optional=True,
    )
    if report["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("semantic holdout report uses the wrong dataset commitment")
    if report["dataset_manifest_sha256"] != dataset_manifest_sha256:
        raise ValueError("semantic holdout report uses the wrong manifest")
    candidate_identity = {
        "candidate_id": candidate_id,
        "commit": commit,
        "corpus_sha256": report["corpus_sha256"],
        "vector_matrix_sha256": report["vector_matrix_sha256"],
        "document_context_sha256": report["document_context_sha256"],
        "repairs_sha256": report["repairs_sha256"],
        "configuration_sha256": report["configuration_sha256"],
    }
    if report["candidate_identity_sha256"] != _sha256_json(candidate_identity):
        raise ValueError("semantic holdout candidate identity digest is inconsistent")
    case_count = _strict_int(
        report, "case_count", "semantic holdout candidate report", minimum=25
    )
    if case_count != manifest["case_count"]:
        raise ValueError("semantic holdout candidate report case_count differs from manifest")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != case_count:
        raise ValueError("semantic holdout candidate report must retain every case")
    expected_roster = manifest["case_roster"]
    expected_case_ids = [row["case_id"] for row in expected_roster]
    expected_input_hashes = {row["case_id"]: row["input_sha256"] for row in expected_roster}
    actual_case_ids: list[str] = []
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"semantic holdout report case {case_index} must be an object")
        _require_exact_keys(
            case,
            {"case_id", "input_sha256", "response", "response_sha256", "claims"},
            context=f"semantic holdout report case {case_index}",
        )
        case_id = _require_nonempty_string(
            case.get("case_id"), context=f"semantic holdout report case {case_index} case_id"
        )
        actual_case_ids.append(case_id)
        if case.get("input_sha256") != expected_input_hashes.get(case_id):
            raise ValueError(f"semantic holdout report case {case_id} input is not committed")
        response = case.get("response")
        if not isinstance(response, str) or not response.strip():
            raise ValueError(
                f"semantic holdout report case {case_id} response must be a non-empty string"
            )
        _require_digest(
            case.get("response_sha256"),
            context=f"semantic holdout report case {case_id} response_sha256",
        )
        if case["response_sha256"] != hashlib.sha256(response.encode("utf-8")).hexdigest():
            raise ValueError(f"semantic holdout report case {case_id} response digest is wrong")
        claims = case.get("claims")
        if not isinstance(claims, list) or not claims:
            raise ValueError(f"semantic holdout report case {case_id} has no reviewable claims")
        claim_ids: list[str] = []
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_index} must be an object"
                )
            _require_exact_keys(
                claim,
                {"claim_id", "text", "text_sha256"},
                context=f"semantic holdout report case {case_id} claim {claim_index}",
            )
            claim_id = _require_nonempty_string(
                claim.get("claim_id"),
                context=f"semantic holdout report case {case_id} claim {claim_index} claim_id",
            )
            claim_ids.append(claim_id)
            text = claim.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_id} text "
                    "must be a non-empty string"
                )
            _require_digest(
                claim.get("text_sha256"),
                context=f"semantic holdout report case {case_id} claim {claim_id} text_sha256",
            )
            if claim["text_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest():
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_id} digest is wrong"
                )
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError(f"semantic holdout report case {case_id} repeats claim IDs")
    if actual_case_ids != expected_case_ids:
        raise ValueError(
            "semantic holdout candidate report roster differs from frozen manifest"
        )
    return report


def _semantic_randomization_context_sha256(
    *,
    candidate_report_sha256: str,
    candidate_identity_sha256: str,
    dataset_manifest_sha256: str,
    development_registry_sha256: str,
) -> str:
    return _sha256_json(
        {
            "algorithm": "sha256_identity_bound_sort.v1",
            "candidate_report_sha256": candidate_report_sha256,
            "candidate_identity_sha256": candidate_identity_sha256,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "development_registry_sha256": development_registry_sha256,
        }
    )


def _semantic_actor_case_order(
    case_ids: list[str],
    *,
    randomization_context_sha256: str,
    actor_role: str,
    actor_id: str,
) -> list[str]:
    def key(case_id: str) -> tuple[str, str]:
        payload = (
            f"{randomization_context_sha256}\0{actor_role}\0{actor_id}\0{case_id}"
        ).encode()
        return hashlib.sha256(payload).hexdigest(), case_id

    return sorted(case_ids, key=key)


def _semantic_claim_roster_sha256(candidate_case: dict[str, Any]) -> str:
    return _sha256_json(
        [
            {"claim_id": claim["claim_id"], "text_sha256": claim["text_sha256"]}
            for claim in candidate_case["claims"]
        ]
    )


def _semantic_displayed_payload_sha256(event: dict[str, Any]) -> str:
    return _sha256_json(
        {
            "event_type": event["event_type"],
            "actor_role": event["actor_role"],
            "actor_id": event["actor_id"],
            "case_id": event["case_id"],
            "case_position": event["case_position"],
            "blinded_candidate_label": event["blinded_candidate_label"],
            "candidate_position": event["candidate_position"],
            "input_sha256": event["input_sha256"],
            "response_sha256": event["response_sha256"],
            "claim_roster_sha256": event["claim_roster_sha256"],
            "review_material_sha256": event["review_material_sha256"],
        }
    )


def _semantic_presentation_event_sha256(event: dict[str, Any]) -> str:
    return _sha256_json({key: value for key, value in event.items() if key != "event_sha256"})


def _semantic_presentation_history(
    presentation: dict[str, Any],
    presentation_log: dict[str, Any],
    *,
    report: dict[str, Any],
    expected_case_ids: list[str],
    reviewers: dict[str, str],
    adjudicator_id: str,
    candidate_report_sha256: str,
    dataset_manifest_sha256: str,
    development_registry_sha256: str,
    report_generated_at: datetime,
    bundle_generated_at: datetime,
) -> dict[str, Any]:
    _require_exact_keys(
        presentation,
        {
            "candidate_identity_blinded",
            "reviewers_blinded_to_each_other",
            "randomized",
            "randomization_algorithm",
            "randomization_context_sha256",
            "blinded_candidate_label",
            "actor_orders",
            "presentation_log_sha256",
        },
        context="semantic holdout presentation evidence",
    )
    for key in (
        "candidate_identity_blinded",
        "reviewers_blinded_to_each_other",
        "randomized",
    ):
        if not _strict_bool(presentation, key, "semantic holdout presentation"):
            raise ValueError(f"semantic holdout presentation requires {key}")
    if presentation.get("randomization_algorithm") != "sha256_identity_bound_sort.v1":
        raise ValueError("semantic holdout presentation randomization algorithm is invalid")
    randomization_context = _semantic_randomization_context_sha256(
        candidate_report_sha256=candidate_report_sha256,
        candidate_identity_sha256=report["candidate_identity_sha256"],
        dataset_manifest_sha256=dataset_manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    _require_digest(
        presentation.get("randomization_context_sha256"),
        context="semantic holdout randomization-context digest",
    )
    if presentation["randomization_context_sha256"] != randomization_context:
        raise ValueError("semantic holdout randomization context is inconsistent")
    blinded_label = _require_nonempty_string(
        presentation.get("blinded_candidate_label"),
        context="semantic holdout blinded candidate label",
    )
    if blinded_label.casefold() == str(report["candidate_id"]).casefold():
        raise ValueError("semantic holdout presentation exposes the candidate identity")

    expected_actors = [("reviewer", reviewer_id) for reviewer_id in reviewers] + [
        ("adjudicator", adjudicator_id)
    ]
    actor_orders = presentation.get("actor_orders")
    if not isinstance(actor_orders, list) or len(actor_orders) != len(expected_actors):
        raise ValueError("semantic holdout presentation requires every exact review actor")
    expected_orders: dict[tuple[str, str], list[str]] = {}
    for index, ((expected_role, expected_actor), actor_order) in enumerate(
        zip(expected_actors, actor_orders, strict=True)
    ):
        if not isinstance(actor_order, dict):
            raise ValueError(f"semantic holdout actor order {index} must be an object")
        _require_exact_keys(
            actor_order,
            {"actor_role", "actor_id", "case_ids", "case_order_sha256"},
            context=f"semantic holdout actor order {index}",
        )
        if (actor_order.get("actor_role"), actor_order.get("actor_id")) != (
            expected_role,
            expected_actor,
        ):
            raise ValueError("semantic holdout presentation actor roster is not canonical")
        expected_order = _semantic_actor_case_order(
            expected_case_ids,
            randomization_context_sha256=randomization_context,
            actor_role=expected_role,
            actor_id=expected_actor,
        )
        if actor_order.get("case_ids") != expected_order:
            raise ValueError("semantic holdout actor presentation order is not reproducible")
        _require_digest(
            actor_order.get("case_order_sha256"),
            context=f"semantic holdout actor order {index} digest",
        )
        if actor_order["case_order_sha256"] != _sha256_json(expected_order):
            raise ValueError("semantic holdout actor presentation-order digest is inconsistent")
        expected_orders[(expected_role, expected_actor)] = expected_order

    _require_exact_keys(
        presentation_log,
        {
            "log_version",
            "log_id",
            "append_only",
            "created_at",
            "finalized_at",
            "candidate_identity_sha256",
            "candidate_report_sha256",
            "dataset_manifest_sha256",
            "development_registry_sha256",
            "randomization_context_sha256",
            "event_count",
            "events",
            "head_event_sha256",
        },
        context="semantic holdout presentation log",
    )
    if presentation_log.get("log_version") != "firelens_semantic_holdout_presentation_log.v1":
        raise ValueError("semantic holdout presentation log uses an unsupported version")
    _require_nonempty_string(
        presentation_log.get("log_id"), context="semantic holdout presentation log ID"
    )
    if not _strict_bool(presentation_log, "append_only", "semantic presentation log"):
        raise ValueError("semantic holdout presentation log must be append-only")
    created_at = _require_timestamp(
        presentation_log.get("created_at"), context="semantic presentation log created_at"
    )
    finalized_at = _require_timestamp(
        presentation_log.get("finalized_at"), context="semantic presentation log finalized_at"
    )
    if created_at <= report_generated_at or finalized_at < created_at:
        raise ValueError("semantic holdout presentation-log timestamps are out of order")
    if finalized_at > bundle_generated_at:
        raise ValueError("semantic holdout presentation log postdates its review bundle")
    expected_log_bindings = {
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "randomization_context_sha256": randomization_context,
    }
    for key, expected in expected_log_bindings.items():
        _require_digest(presentation_log.get(key), context=f"semantic presentation log {key}")
        if presentation_log[key] != expected:
            raise ValueError(f"semantic holdout presentation log has the wrong {key}")

    events = presentation_log.get("events")
    event_count = _strict_int(
        presentation_log, "event_count", "semantic presentation log", minimum=0
    )
    expected_event_count = len(expected_case_ids) * len(expected_actors)
    if not isinstance(events, list) or event_count != expected_event_count:
        raise ValueError("semantic holdout presentation log has an incomplete event roster")
    if len(events) != event_count:
        raise ValueError("semantic holdout presentation event_count differs from events")
    event_keys = {
        "sequence",
        "event_id",
        "event_type",
        "actor_role",
        "actor_id",
        "case_id",
        "case_position",
        "blinded_candidate_label",
        "candidate_position",
        "candidate_identity_sha256",
        "candidate_report_sha256",
        "input_sha256",
        "response_sha256",
        "claim_roster_sha256",
        "review_material_sha256",
        "displayed_payload_sha256",
        "presented_at",
        "previous_event_sha256",
        "event_sha256",
    }
    report_cases = {case["case_id"]: case for case in report["cases"]}
    events_by_exposure: dict[tuple[str, str, str], dict[str, Any]] = {}
    prior_digest: str | None = None
    prior_timestamp: datetime | None = None
    event_ids: set[str] = set()
    observed_actor_orders: dict[tuple[str, str], list[str]] = {
        actor: [] for actor in expected_actors
    }
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"semantic presentation event {index} must be an object")
        _require_exact_keys(event, event_keys, context=f"semantic presentation event {index}")
        if (
            _strict_int(event, "sequence", f"semantic presentation event {index}", minimum=1)
            != index
        ):
            raise ValueError("semantic holdout presentation event sequence is not contiguous")
        event_id = _require_nonempty_string(
            event.get("event_id"), context=f"semantic presentation event {index} ID"
        )
        if event_id in event_ids:
            raise ValueError("semantic holdout presentation event IDs must be unique")
        event_ids.add(event_id)
        actor_key = (event.get("actor_role"), event.get("actor_id"))
        if actor_key not in expected_orders:
            raise ValueError("semantic holdout presentation event uses an unknown actor")
        expected_event_type = (
            "independent_review_presentation"
            if actor_key[0] == "reviewer"
            else "adjudication_presentation"
        )
        if event.get("event_type") != expected_event_type:
            raise ValueError("semantic holdout presentation event has the wrong event_type")
        case_id = event.get("case_id")
        candidate_case = report_cases.get(case_id)
        if candidate_case is None:
            raise ValueError("semantic holdout presentation event uses an unknown case")
        observed_actor_orders[actor_key].append(case_id)
        expected_position = len(observed_actor_orders[actor_key])
        if (
            _strict_int(
                event, "case_position", f"semantic presentation event {index}", minimum=1
            )
            != expected_position
        ):
            raise ValueError("semantic holdout presentation case positions are not contiguous")
        if event.get("blinded_candidate_label") != blinded_label:
            raise ValueError("semantic holdout presentation event exposes the wrong candidate")
        if (
            _strict_int(
                event, "candidate_position", f"semantic presentation event {index}", minimum=1
            )
            != 1
        ):
            raise ValueError(
                "semantic holdout final qualification presents exactly one candidate"
            )
        for key, expected in {
            "candidate_identity_sha256": report["candidate_identity_sha256"],
            "candidate_report_sha256": candidate_report_sha256,
            "input_sha256": candidate_case["input_sha256"],
            "response_sha256": candidate_case["response_sha256"],
            "claim_roster_sha256": _semantic_claim_roster_sha256(candidate_case),
        }.items():
            _require_digest(
                event.get(key), context=f"semantic presentation event {index} {key}"
            )
            if event[key] != expected:
                raise ValueError(f"semantic holdout presentation event has the wrong {key}")
        if actor_key[0] == "reviewer":
            if event.get("review_material_sha256") is not None:
                raise ValueError("independent reviewer presentation exposes review material")
        else:
            _require_digest(
                event.get("review_material_sha256"),
                context=f"semantic presentation event {index} review material",
            )
        _require_digest(
            event.get("displayed_payload_sha256"),
            context=f"semantic presentation event {index} displayed payload",
        )
        if event["displayed_payload_sha256"] != _semantic_displayed_payload_sha256(event):
            raise ValueError("semantic holdout displayed-payload digest is inconsistent")
        presented_at = _require_timestamp(
            event.get("presented_at"),
            context=f"semantic presentation event {index} timestamp",
        )
        if presented_at < created_at or presented_at > finalized_at:
            raise ValueError("semantic holdout presentation event is outside the log window")
        if prior_timestamp is not None and presented_at <= prior_timestamp:
            raise ValueError(
                "semantic holdout presentation timestamps are not strictly ordered"
            )
        prior_timestamp = presented_at
        if event.get("previous_event_sha256") != prior_digest:
            raise ValueError("semantic holdout presentation hash chain is broken")
        _require_digest(
            event.get("event_sha256"),
            context=f"semantic presentation event {index} digest",
        )
        recomputed_event_digest = _semantic_presentation_event_sha256(event)
        if event["event_sha256"] != recomputed_event_digest:
            raise ValueError("semantic holdout presentation event digest is inconsistent")
        prior_digest = recomputed_event_digest
        exposure_key = (actor_key[0], actor_key[1], case_id)
        if exposure_key in events_by_exposure:
            raise ValueError("semantic holdout presentation repeats an actor/case exposure")
        events_by_exposure[exposure_key] = {
            "event": event,
            "presented_at": presented_at,
        }
    for actor_key, expected_order in expected_orders.items():
        if observed_actor_orders[actor_key] != expected_order:
            raise ValueError("semantic holdout presentation log differs from actor order")
    _require_digest(
        presentation_log.get("head_event_sha256"),
        context="semantic holdout presentation-log head digest",
    )
    if presentation_log["head_event_sha256"] != prior_digest:
        raise ValueError("semantic holdout presentation-log head is inconsistent")
    presentation_log_digest = _sha256_json(presentation_log)
    _require_digest(
        presentation.get("presentation_log_sha256"),
        context="semantic holdout presentation-log digest",
    )
    if presentation["presentation_log_sha256"] != presentation_log_digest:
        raise ValueError("semantic holdout presentation-log digest is inconsistent")
    return {
        "events_by_exposure": events_by_exposure,
        "actor_orders": expected_orders,
        "event_count": event_count,
        "head_event_sha256": prior_digest,
        "presentation_log_sha256": presentation_log_digest,
        "randomization_context_sha256": randomization_context,
    }


def _semantic_holdout(
    candidate_report: dict[str, Any] | None,
    review_bundle: dict[str, Any] | None = None,
    *,
    manifest: dict[str, Any] | None = None,
    development_registry: dict[str, Any] | None = None,
    candidate_report_sha256: str | None = None,
    review_bundle_sha256: str | None = None,
    dataset_manifest_sha256: str | None = None,
    development_registry_sha256: str | None = None,
    submitted_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if candidate_report is None and review_bundle is None and submitted_summary is None:
        return {"status": "not_run"}
    if (
        candidate_report is None
        or review_bundle is None
        or manifest is None
        or development_registry is None
    ):
        raise ValueError(
            "semantic holdout requires the candidate report, review bundle, manifest, "
            "and frozen development registry"
        )
    candidate_report_digest = _require_digest(
        candidate_report_sha256, context="semantic holdout candidate report digest"
    )
    review_bundle_digest = _require_digest(
        review_bundle_sha256, context="semantic holdout review bundle digest"
    )
    manifest_digest = _require_digest(
        dataset_manifest_sha256, context="semantic holdout manifest digest"
    )
    development_registry_digest = _require_digest(
        development_registry_sha256,
        context="semantic holdout development registry digest",
    )
    development_registry = _semantic_development_registry_payload(development_registry)
    manifest = _semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256=development_registry_digest,
    )
    report = _semantic_holdout_candidate_report(
        candidate_report,
        manifest=manifest,
        dataset_manifest_sha256=manifest_digest,
    )
    _require_exact_keys(
        review_bundle,
        {
            "bundle_version",
            "generated_at",
            "candidate_id",
            "candidate_identity_sha256",
            "candidate_report_sha256",
            "dataset_sha256",
            "dataset_manifest_sha256",
            "development_registry_sha256",
            "case_count",
            "case_ids",
            "presentation",
            "presentation_log",
            "reviewer_registry",
            "adjudicator",
            "cases",
        },
        context="semantic holdout review bundle",
    )
    if review_bundle.get("bundle_version") != "firelens_semantic_holdout_review_bundle.v2":
        raise ValueError("semantic holdout review bundle uses an unsupported version")
    bundle_generated_at = _require_timestamp(
        review_bundle.get("generated_at"), context="semantic holdout review bundle generated_at"
    )
    if review_bundle.get("candidate_id") != report["candidate_id"]:
        raise ValueError("semantic holdout review bundle targets the wrong candidate")
    if review_bundle.get("candidate_identity_sha256") != report["candidate_identity_sha256"]:
        raise ValueError("semantic holdout review bundle has the wrong candidate identity")
    if review_bundle.get("candidate_report_sha256") != candidate_report_digest:
        raise ValueError("semantic holdout review bundle does not match the candidate report")
    if review_bundle.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise ValueError("semantic holdout review bundle uses the wrong dataset commitment")
    if review_bundle.get("dataset_manifest_sha256") != manifest_digest:
        raise ValueError("semantic holdout review bundle uses the wrong manifest")
    if review_bundle.get("development_registry_sha256") != development_registry_digest:
        raise ValueError("semantic holdout review bundle uses the wrong development registry")
    case_count = _strict_int(
        review_bundle, "case_count", "semantic holdout review bundle", minimum=25
    )
    if case_count != manifest["case_count"]:
        raise ValueError("semantic holdout review bundle case_count differs from manifest")
    expected_case_ids = [row["case_id"] for row in manifest["case_roster"]]
    if review_bundle.get("case_ids") != expected_case_ids:
        raise ValueError("semantic holdout review bundle roster differs from frozen manifest")

    presentation = review_bundle.get("presentation")
    if not isinstance(presentation, dict):
        raise ValueError("semantic holdout presentation evidence must be an object")
    presentation_log = review_bundle.get("presentation_log")
    if not isinstance(presentation_log, dict):
        raise ValueError("semantic holdout presentation log must be an object")

    reviewer_registry = review_bundle.get("reviewer_registry")
    if not isinstance(reviewer_registry, list) or len(reviewer_registry) != 2:
        raise ValueError("semantic holdout requires exactly two named reviewers")
    reviewers: dict[str, str] = {}
    for index, reviewer in enumerate(reviewer_registry):
        if not isinstance(reviewer, dict):
            raise ValueError(f"semantic holdout reviewer {index} must be an object")
        _require_exact_keys(
            reviewer,
            {"reviewer_id", "name"},
            context=f"semantic holdout reviewer {index}",
        )
        reviewer_id = _require_nonempty_string(
            reviewer.get("reviewer_id"), context=f"semantic holdout reviewer {index} ID"
        )
        name = _require_nonempty_string(
            reviewer.get("name"), context=f"semantic holdout reviewer {index} name"
        )
        if reviewer_id in reviewers:
            raise ValueError("semantic holdout reviewer IDs must be unique")
        reviewers[reviewer_id] = name
    if len(set(reviewers.values())) != len(reviewers):
        raise ValueError("semantic holdout reviewer names must identify distinct people")

    adjudicator = review_bundle.get("adjudicator")
    if not isinstance(adjudicator, dict):
        raise ValueError("semantic holdout adjudicator must be an object")
    _require_exact_keys(
        adjudicator,
        {"adjudicator_id", "name"},
        context="semantic holdout adjudicator",
    )
    adjudicator_id = _require_nonempty_string(
        adjudicator.get("adjudicator_id"), context="semantic holdout adjudicator ID"
    )
    adjudicator_name = _require_nonempty_string(
        adjudicator.get("name"), context="semantic holdout adjudicator name"
    )
    if adjudicator_id in reviewers or adjudicator_name in reviewers.values():
        raise ValueError("semantic holdout adjudicator must be distinct from both reviewers")

    report_generated_at = _require_timestamp(
        report.get("generated_at"), context="semantic holdout report generated_at"
    )
    presentation_history = _semantic_presentation_history(
        presentation,
        presentation_log,
        report=report,
        expected_case_ids=expected_case_ids,
        reviewers=reviewers,
        adjudicator_id=adjudicator_id,
        candidate_report_sha256=candidate_report_digest,
        dataset_manifest_sha256=manifest_digest,
        development_registry_sha256=development_registry_digest,
        report_generated_at=report_generated_at,
        bundle_generated_at=bundle_generated_at,
    )
    report_cases = {case["case_id"]: case for case in report["cases"]}
    bundle_cases = review_bundle.get("cases")
    if not isinstance(bundle_cases, list) or len(bundle_cases) != case_count:
        raise ValueError("semantic holdout review bundle must retain every case")
    if [case.get("case_id") for case in bundle_cases if isinstance(case, dict)] != (
        presentation_history["actor_orders"][("adjudicator", adjudicator_id)]
    ):
        raise ValueError(
            "semantic holdout review rows do not follow the randomized presentation"
        )

    approved_case_count = 0
    unsupported_or_unclear = 0
    dangerous_omission_count = 0
    claim_count = 0
    agreement_count = 0
    first_reviewer_labels: Counter[str] = Counter()
    second_reviewer_labels: Counter[str] = Counter()
    reviewer_ids_used: set[str] = set()
    adjudication_times: list[datetime] = []
    valid_labels = {"supported", "unsupported", "unclear"}
    for case_index, case_review in enumerate(bundle_cases):
        if not isinstance(case_review, dict):
            raise ValueError(f"semantic holdout review case {case_index} must be an object")
        _require_exact_keys(
            case_review,
            {"case_id", "independent_reviews", "adjudication"},
            context=f"semantic holdout review case {case_index}",
        )
        case_id = case_review.get("case_id")
        candidate_case = report_cases.get(case_id)
        if candidate_case is None:
            raise ValueError(
                "semantic holdout review contains a case outside the frozen roster"
            )
        expected_claim_ids = [claim["claim_id"] for claim in candidate_case["claims"]]
        independent_reviews = case_review.get("independent_reviews")
        if not isinstance(independent_reviews, list) or len(independent_reviews) != 2:
            raise ValueError(f"semantic holdout case {case_id} requires exactly two reviews")
        case_reviewer_ids: list[str] = []
        review_times: list[datetime] = []
        review_label_sequences: list[list[str]] = []
        for review_index, review in enumerate(independent_reviews):
            if not isinstance(review, dict):
                raise ValueError(
                    f"semantic holdout case {case_id} review {review_index} must be an object"
                )
            _require_exact_keys(
                review,
                {
                    "reviewer_id",
                    "reviewed_at",
                    "presentation_event_sha256",
                    "independent",
                    "blinded_to_candidate_identity",
                    "blinded_to_other_review",
                    "claim_labels",
                    "dangerous_omission",
                    "case_decision",
                },
                context=f"semantic holdout case {case_id} review {review_index}",
            )
            reviewer_id = review.get("reviewer_id")
            if reviewer_id not in reviewers:
                raise ValueError(f"semantic holdout case {case_id} uses an unnamed reviewer")
            case_reviewer_ids.append(reviewer_id)
            reviewer_ids_used.add(reviewer_id)
            reviewed_at = _require_timestamp(
                review.get("reviewed_at"),
                context=f"semantic holdout case {case_id} review timestamp",
            )
            if reviewed_at <= report_generated_at:
                raise ValueError(
                    f"semantic holdout case {case_id} review predates candidate generation"
                )
            presentation_event_digest = _require_digest(
                review.get("presentation_event_sha256"),
                context=f"semantic holdout case {case_id} reviewer presentation event",
            )
            review_exposure = presentation_history["events_by_exposure"].get(
                ("reviewer", reviewer_id, case_id)
            )
            if (
                review_exposure is None
                or presentation_event_digest != review_exposure["event"]["event_sha256"]
            ):
                raise ValueError(
                    f"semantic holdout case {case_id} review is not bound to its presentation"
                )
            if review_exposure["presented_at"] >= reviewed_at:
                raise ValueError(
                    f"semantic holdout case {case_id} review predates its presentation"
                )
            review_times.append(reviewed_at)
            for key in (
                "independent",
                "blinded_to_candidate_identity",
                "blinded_to_other_review",
            ):
                if not _strict_bool(review, key, f"semantic holdout case {case_id} review"):
                    raise ValueError(
                        f"semantic holdout case {case_id} review does not establish {key}"
                    )
            dangerous = _strict_bool(
                review, "dangerous_omission", f"semantic holdout case {case_id} review"
            )
            claim_labels = review.get("claim_labels")
            if not isinstance(claim_labels, list):
                raise ValueError(f"semantic holdout case {case_id} claim labels must be a list")
            labels: list[str] = []
            actual_claim_ids: list[str] = []
            for label_index, label_row in enumerate(claim_labels):
                if not isinstance(label_row, dict):
                    raise ValueError(
                        f"semantic holdout case {case_id} label {label_index} must be an object"
                    )
                _require_exact_keys(
                    label_row,
                    {"claim_id", "label"},
                    context=f"semantic holdout case {case_id} label {label_index}",
                )
                actual_claim_ids.append(label_row.get("claim_id"))
                label = label_row.get("label")
                if label not in valid_labels:
                    raise ValueError(
                        f"semantic holdout case {case_id} has an invalid claim label"
                    )
                labels.append(label)
            if actual_claim_ids != expected_claim_ids:
                raise ValueError(
                    f"semantic holdout case {case_id} review does not label every exact claim"
                )
            expected_decision = (
                "approved"
                if all(label == "supported" for label in labels) and not dangerous
                else "rejected"
            )
            if review.get("case_decision") != expected_decision:
                raise ValueError(
                    f"semantic holdout case {case_id} reviewer decision disagrees with labels"
                )
            review_label_sequences.append(labels)
        if case_reviewer_ids != list(reviewers):
            raise ValueError(
                f"semantic holdout case {case_id} requires two distinct reviewers "
                "in canonical registry order"
            )

        adjudication = case_review.get("adjudication")
        if not isinstance(adjudication, dict):
            raise ValueError(f"semantic holdout case {case_id} adjudication must be an object")
        _require_exact_keys(
            adjudication,
            {
                "adjudicator_id",
                "adjudicated_at",
                "presentation_event_sha256",
                "reviewer_decisions_locked",
                "independent_reviews_sha256",
                "resolution_status",
                "claim_labels",
                "dangerous_omission",
                "case_decision",
            },
            context=f"semantic holdout case {case_id} adjudication",
        )
        if adjudication.get("adjudicator_id") != adjudicator_id:
            raise ValueError(f"semantic holdout case {case_id} uses the wrong adjudicator")
        adjudicated_at = _require_timestamp(
            adjudication.get("adjudicated_at"),
            context=f"semantic holdout case {case_id} adjudication timestamp",
        )
        if adjudicated_at <= max(review_times):
            raise ValueError(
                f"semantic holdout case {case_id} was adjudicated before reviews were complete"
            )
        if adjudicated_at > bundle_generated_at:
            raise ValueError(
                f"semantic holdout case {case_id} adjudication postdates its review bundle"
            )
        adjudication_event_digest = _require_digest(
            adjudication.get("presentation_event_sha256"),
            context=f"semantic holdout case {case_id} adjudication presentation event",
        )
        adjudication_exposure = presentation_history["events_by_exposure"].get(
            ("adjudicator", adjudicator_id, case_id)
        )
        if (
            adjudication_exposure is None
            or adjudication_event_digest != adjudication_exposure["event"]["event_sha256"]
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication is not bound to its presentation"
            )
        if (
            adjudication_exposure["presented_at"] <= max(review_times)
            or adjudication_exposure["presented_at"] >= adjudicated_at
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication presentation is out of order"
            )
        adjudication_times.append(adjudicated_at)
        if not _strict_bool(
            adjudication,
            "reviewer_decisions_locked",
            f"semantic holdout case {case_id} adjudication",
        ):
            raise ValueError(
                f"semantic holdout case {case_id} reviewer decisions were not locked"
            )
        _require_digest(
            adjudication.get("independent_reviews_sha256"),
            context=f"semantic holdout case {case_id} independent-review digest",
        )
        if adjudication["independent_reviews_sha256"] != _sha256_json(independent_reviews):
            raise ValueError(
                f"semantic holdout case {case_id} independent-review digest is inconsistent"
            )
        if (
            adjudication_exposure["event"]["review_material_sha256"]
            != adjudication["independent_reviews_sha256"]
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication presentation uses stale reviews"
            )
        if adjudication.get("resolution_status") != "resolved":
            raise ValueError(f"semantic holdout case {case_id} remains unresolved")
        final_labels = adjudication.get("claim_labels")
        if not isinstance(final_labels, list):
            raise ValueError(
                f"semantic holdout case {case_id} adjudicated claim labels must be a list"
            )
        final_claim_ids: list[str] = []
        final_label_values: list[str] = []
        for label_index, label_row in enumerate(final_labels):
            if not isinstance(label_row, dict):
                raise ValueError(
                    f"semantic holdout case {case_id} adjudicated label {label_index} must be an object"
                )
            _require_exact_keys(
                label_row,
                {"claim_id", "label"},
                context=f"semantic holdout case {case_id} adjudicated label {label_index}",
            )
            final_claim_ids.append(label_row.get("claim_id"))
            label = label_row.get("label")
            if label not in valid_labels:
                raise ValueError(
                    f"semantic holdout case {case_id} has an invalid adjudicated label"
                )
            final_label_values.append(label)
        if final_claim_ids != expected_claim_ids:
            raise ValueError(
                f"semantic holdout case {case_id} adjudication does not cover every exact claim"
            )
        final_dangerous = _strict_bool(
            adjudication,
            "dangerous_omission",
            f"semantic holdout case {case_id} adjudication",
        )
        final_decision = (
            "approved"
            if all(label == "supported" for label in final_label_values) and not final_dangerous
            else "rejected"
        )
        if adjudication.get("case_decision") != final_decision:
            raise ValueError(
                f"semantic holdout case {case_id} adjudicated decision disagrees with findings"
            )
        approved_case_count += int(final_decision == "approved")
        unsupported_or_unclear += sum(
            label in {"unsupported", "unclear"} for label in final_label_values
        )
        dangerous_omission_count += int(final_dangerous)
        for first_label, second_label in zip(
            review_label_sequences[0], review_label_sequences[1], strict=True
        ):
            claim_count += 1
            agreement_count += int(first_label == second_label)
            first_reviewer_labels[first_label] += 1
            second_reviewer_labels[second_label] += 1
    if reviewer_ids_used != set(reviewers):
        raise ValueError("semantic holdout reviewer registry contains unused identities")

    agreement_rate = agreement_count / claim_count
    expected_agreement = sum(
        (first_reviewer_labels[label] / claim_count)
        * (second_reviewer_labels[label] / claim_count)
        for label in valid_labels
    )
    if math.isclose(expected_agreement, 1.0, rel_tol=0, abs_tol=1e-15):
        cohens_kappa = 1.0 if math.isclose(agreement_rate, 1.0) else 0.0
    else:
        cohens_kappa = (agreement_rate - expected_agreement) / (1.0 - expected_agreement)
    qualified = (
        approved_case_count == case_count
        and unsupported_or_unclear == 0
        and dangerous_omission_count == 0
    )
    recomputed_summary = {
        "summary_version": "firelens_semantic_holdout_summary.v3",
        "candidate_id": report["candidate_id"],
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "commit": report["commit"],
        "corpus_sha256": report["corpus_sha256"],
        "vector_matrix_sha256": report["vector_matrix_sha256"],
        "document_context_sha256": report["document_context_sha256"],
        "repairs_sha256": report["repairs_sha256"],
        "configuration_sha256": report["configuration_sha256"],
        "dataset_sha256": report["dataset_sha256"],
        "dataset_manifest_sha256": manifest_digest,
        "development_registry_sha256": development_registry_digest,
        "candidate_report_sha256": candidate_report_digest,
        "review_bundle_sha256": review_bundle_digest,
        "presentation_log_sha256": presentation_history["presentation_log_sha256"],
        "presentation_log_head_sha256": presentation_history["head_event_sha256"],
        "presentation_event_count": presentation_history["event_count"],
        "randomization_context_sha256": presentation_history["randomization_context_sha256"],
        "case_count": case_count,
        "claim_count": claim_count,
        "independent_review_count": case_count * 2,
        "approved_case_count": approved_case_count,
        "unsupported_or_unclear": unsupported_or_unclear,
        "dangerous_omission_count": dangerous_omission_count,
        "unresolved_case_count": 0,
        "reviewers": sorted(reviewers.values()),
        "adjudicator": adjudicator_name,
        "reviewed_at": max(adjudication_times).astimezone(UTC).isoformat(),
        "claim_label_agreement_count": agreement_count,
        "claim_label_agreement_rate": agreement_rate,
        "claim_label_cohens_kappa": cohens_kappa,
        "qualified": qualified,
    }
    if submitted_summary is not None:
        _assert_recomputed_summary_matches(
            submitted_summary,
            recomputed_summary,
            context="semantic holdout",
        )
    return {"status": "complete", **recomputed_summary}


def validate_semantic_holdout(
    candidate_report_path: Path,
    review_bundle_path: Path,
    manifest_path: Path,
    development_registry_path: Path,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    candidate_report = _read_report(candidate_report_path)
    review_bundle = _read_report(review_bundle_path)
    development_registry = _semantic_development_registry(development_registry_path)
    development_registry_digest = file_sha256(development_registry_path)
    manifest = _semantic_holdout_manifest(
        manifest_path,
        development_registry=development_registry,
        development_registry_sha256=development_registry_digest,
    )
    if candidate_report is None or review_bundle is None:
        raise ValueError("semantic holdout raw artifacts are missing")
    return _semantic_holdout(
        candidate_report,
        review_bundle,
        manifest=manifest,
        development_registry=development_registry,
        candidate_report_sha256=file_sha256(candidate_report_path),
        review_bundle_sha256=file_sha256(review_bundle_path),
        dataset_manifest_sha256=file_sha256(manifest_path),
        development_registry_sha256=development_registry_digest,
        submitted_summary=_read_report(summary_path),
    )


def _check_report_identity(
    name: str, observed: str | None, commit: str, *, required: bool = True
) -> None:
    if required and observed is None:
        raise ValueError(f"{name} report has no commit identity")
    if observed is not None and observed != commit:
        raise ValueError(f"{name} report commit {observed} does not match {commit}")


def _metrics(snapshot: dict[str, Any]) -> dict[str, float | bool | None]:
    hard = snapshot["hard_probe_offline"]
    qualified_hard = snapshot["hard_probe_qualified"]
    live = snapshot["live"]
    development_retrieval = snapshot["development_retrieval"]
    semantic = snapshot["semantic_review"]
    semantic_holdout = snapshot["semantic_holdout"]
    retrieval_review = snapshot["retrieval_review"]
    retrieval = snapshot["retrieval_qualification"]
    ux = snapshot["ux"]
    preview = snapshot["preview"]
    deployment = snapshot["deployment"]
    frontend_bundle = snapshot["frontend_bundle"]
    frontend_surface = snapshot["frontend_surface"]
    frontend_manual = snapshot["frontend_manual_review"]
    runtime_artifact = _runtime_artifact_metric_values(snapshot)
    frontend_performance = frontend_surface.get("worst_profile_p75") or {}
    return {
        "verification_passed": snapshot["verification"].get("passed"),
        "offline_hard_probe_pass_rate": hard.get("pass_rate"),
        "offline_hard_probe_critical_failures": hard.get("critical_failures"),
        "offline_hard_probe_p95_ms": hard.get("p95_latency_ms"),
        "frontend_initial_route_js_gzip_bytes": frontend_bundle.get("initial_js_gzip_bytes"),
        "frontend_lazy_js_gzip_bytes": frontend_bundle.get("lazy_js_gzip_bytes"),
        "frontend_initial_css_gzip_bytes": frontend_bundle.get("initial_css_gzip_bytes"),
        "frontend_lazy_css_gzip_bytes": frontend_bundle.get("lazy_css_gzip_bytes"),
        "frontend_server_js_gzip_bytes": frontend_bundle.get("server_js_gzip_bytes"),
        "frontend_font_bytes": frontend_bundle.get("font_bytes"),
        "frontend_image_bytes": frontend_bundle.get("image_bytes"),
        "frontend_deployment_metadata_bytes": frontend_bundle.get("deployment_metadata_bytes"),
        "frontend_other_bytes": frontend_bundle.get("other_bytes"),
        "frontend_total_emitted_bytes": frontend_bundle.get("total_emitted_bytes"),
        "frontend_unclassified_output_bytes": frontend_bundle.get("unclassified_bytes"),
        "frontend_surface_qualified": frontend_surface.get("qualified"),
        "frontend_visual_matrix_pass_rate": frontend_surface.get("visual_matrix_pass_rate"),
        "frontend_css_layout_violation_count": frontend_surface.get(
            "css_layout_violation_count"
        ),
        "frontend_axe_wcag_a_aa_finding_count": frontend_surface.get(
            "axe_wcag_a_aa_finding_count"
        ),
        "frontend_runtime_violation_count": frontend_surface.get("runtime_violation_count"),
        "frontend_keyboard_journey_passed": frontend_surface.get("keyboard_journey_passed"),
        "frontend_map_list_parity": frontend_surface.get("map_list_parity"),
        "frontend_map_detail_integrity": frontend_surface.get("map_detail_integrity"),
        "frontend_map_marker_placement_sanity": frontend_surface.get(
            "map_marker_placement_sanity"
        ),
        "frontend_direct_third_party_tile_request_count": frontend_surface.get(
            "direct_third_party_tile_request_count"
        ),
        "frontend_worst_p75_lcp_ms": frontend_performance.get("lcp_ms"),
        "frontend_worst_p75_cls": frontend_performance.get("cls"),
        "frontend_worst_p75_inp_proxy_ms": frontend_performance.get("inp_interaction_proxy_ms"),
        "frontend_worst_p75_map_ready_ms": frontend_performance.get(
            "map_ready_after_interaction_ms"
        ),
        "frontend_manual_accessibility_qualified": frontend_manual.get(
            "accessibility_qualified"
        ),
        "frontend_manual_product_safety_qualified": frontend_manual.get(
            "product_safety_qualified"
        ),
        "frontend_manual_open_findings": frontend_manual.get("open_finding_count"),
        "live_qualified": live.get("qualified"),
        "live_cached_p95_ms": live.get("cached_p95_ms"),
        "development_retrieval_recall_at_5": development_retrieval.get("recall_at_5"),
        "development_retrieval_mrr_at_5": development_retrieval.get("mrr_at_5"),
        "development_retrieval_ndcg_at_5": development_retrieval.get("ndcg_at_5"),
        "development_retrieval_mean_source_coverage": development_retrieval.get(
            "mean_source_coverage"
        ),
        "development_retrieval_cost_usd": development_retrieval.get("reported_cost_usd"),
        "qualified_hard_probe_pass_rate": qualified_hard.get("pass_rate"),
        "qualified_hard_probe_cost_usd": qualified_hard.get("cost_usd"),
        "sealed_retrieval_qualified": retrieval.get("qualified"),
        "sealed_retrieval_repetitions": retrieval.get("repetitions"),
        "sealed_retrieval_min_recall_at_5": retrieval.get("min_recall_at_5"),
        "semantic_review_qualified": semantic.get("qualified"),
        "semantic_review_approval_rate": semantic.get("approval_rate"),
        "semantic_review_unsupported_or_unclear": (
            int(semantic.get("unsupported_verified_claim_count") or 0)
            + int(semantic.get("unclear_claim_count") or 0)
            if semantic.get("status") == "complete"
            else None
        ),
        "semantic_holdout_qualified": semantic_holdout.get("qualified"),
        "semantic_holdout_unsupported_or_unclear": semantic_holdout.get(
            "unsupported_or_unclear"
        ),
        "semantic_holdout_dangerous_omissions": semantic_holdout.get(
            "dangerous_omission_count"
        ),
        "retrieval_review_qualified": retrieval_review.get("qualified"),
        "retrieval_review_approval_rate": retrieval_review.get("approval_rate"),
        "ux_participant_count": ux.get("participant_count"),
        "ux_task_completion_rate": ux.get("task_completion_rate"),
        "ux_min_task_completion_rate": ux.get("min_task_completion_rate"),
        "ux_critical_error_count": ux.get("critical_error_count"),
        "ux_near_me_median_seconds": ux.get("near_me_median_seconds"),
        "ux_median_seq_score": ux.get("median_seq_score"),
        "ux_evidence_comprehension_rate": ux.get("evidence_comprehension_rate"),
        "ux_freshness_comprehension_rate": ux.get("freshness_comprehension_rate"),
        "ux_official_source_open_rate": ux.get("official_source_open_rate"),
        "ux_access_method_sampling_coverage": ux.get("accessibility_coverage"),
        "preview_qualified": preview.get("qualified"),
        "distributed_rate_limit_verified": deployment.get("distributed_rate_limit_verified"),
        "rollback_rehearsal_passed": deployment.get("rollback_rehearsal_passed"),
        **runtime_artifact,
    }


def _validated_snapshot_metrics(
    snapshot: dict[str, Any], spec: BenchmarkSpec, *, label: str
) -> dict[str, float | bool | None]:
    stored = snapshot.get("metrics")
    if not isinstance(stored, dict):
        raise ValueError(f"{label} snapshot has no stored metrics object")
    expected_keys = {metric.key for metric in spec.comparison_metrics}
    if set(stored) != expected_keys:
        missing = sorted(expected_keys - set(stored))
        unknown = sorted(set(stored) - expected_keys)
        raise ValueError(
            f"{label} snapshot metric schema mismatch; missing={missing}, unknown={unknown}"
        )
    try:
        recomputed = _metrics(snapshot)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{label} snapshot cannot recompute metrics from detailed sections"
        ) from error
    if set(recomputed) != expected_keys:
        missing = sorted(expected_keys - set(recomputed))
        unknown = sorted(set(recomputed) - expected_keys)
        raise ValueError(
            f"benchmark metric extractor differs from the specification; "
            f"missing={missing}, unknown={unknown}"
        )
    for metric in spec.comparison_metrics:
        stored_value = _validated_metric_value(metric, stored[metric.key], label=label)
        recomputed_value = _validated_metric_value(
            metric, recomputed[metric.key], label=f"{label} recomputed"
        )
        if type(stored_value) is not type(recomputed_value) or stored_value != recomputed_value:
            raise ValueError(
                f"{label} snapshot stored metric {metric.key} diverges from its "
                "detailed evidence"
            )
    return recomputed


def _candidate_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("before snapshot has no candidate identity")
    keys = (
        "commit",
        "branch",
        "candidate_id",
        "release_version",
        "corpus_version",
        "corpus_sha256",
        "vector_matrix_sha256",
        "vector_manifest_sha256",
        "document_context_sha256",
        "repairs_sha256",
        "configuration_sha256",
        "execution_environment",
    )
    missing = [key for key in keys if key not in identity]
    if missing:
        raise ValueError(f"before snapshot candidate identity is incomplete: {missing}")
    if not isinstance(identity.get("commit"), str) or not identity["commit"].strip():
        raise ValueError("before snapshot candidate identity has no commit")
    return {key: identity[key] for key in keys}


def _current_benchmark_identities(
    spec: BenchmarkSpec, spec_path: Path
) -> tuple[str, dict[str, str], dict[str, str]]:
    return (
        file_sha256(spec_path),
        {relative: file_sha256(ROOT / relative) for relative in spec.identity_inputs},
        {relative: file_sha256(ROOT / relative) for relative in spec.harness_inputs},
    )


def _validate_before_snapshot_contract(
    before: dict[str, Any], spec: BenchmarkSpec, spec_path: Path
) -> dict[str, float | bool | None]:
    if before.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2":
        raise ValueError("before seal requires snapshot schema v2")
    if before.get("benchmark_id") != spec.benchmark_id or before.get("label") != "before":
        raise ValueError("before seal requires the matching before snapshot")
    if before.get("capture_complete") is not True:
        raise ValueError("before seal requires a complete before capture")
    if before.get("missing_required_metrics") not in ([], None):
        raise ValueError("before seal cannot attest a snapshot with missing metrics")
    metrics = _validated_snapshot_metrics(before, spec, label="before")
    missing_paired = sorted(
        metric.key
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "paired" and metrics.get(metric.key) is None
    )
    if missing_paired:
        raise ValueError(f"before seal requires every paired metric; missing={missing_paired}")
    identity = before.get("identity") or {}
    if identity.get("candidate_id") != _runtime_candidate_id(
        spec.benchmark_id, identity.get("commit", "")
    ):
        raise ValueError("before snapshot candidate ID is not canonical for its commit")
    spec_sha256, dataset_identity, harness_identity = _current_benchmark_identities(
        spec, spec_path
    )
    if identity.get("spec_sha256") != spec_sha256:
        raise ValueError("before snapshot does not match the current benchmark specification")
    if identity.get("identity_input_sha256") != dataset_identity:
        raise ValueError("before snapshot does not match current frozen evaluation inputs")
    if identity.get("harness_input_sha256") != harness_identity:
        raise ValueError("before snapshot does not match the current benchmark harness")
    _candidate_identity(before)
    return metrics


def _parse_attestation_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("before snapshot seal requires a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("before snapshot seal timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("before snapshot seal timestamp must include a timezone")
    return value


def _build_before_snapshot_seal(
    *,
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
    owner: str,
    sealed_at: str,
) -> dict[str, Any]:
    metrics = _validate_before_snapshot_contract(before, spec, spec_path)
    normalized_owner = owner.strip()
    if not normalized_owner or normalized_owner.casefold() in {"owner", "unknown", "tbd"}:
        raise ValueError("before snapshot seal requires a named owner")
    _parse_attestation_timestamp(sealed_at)
    resolved_before, relative_before = _repo_relative_path(
        before_path, context="before snapshot"
    )
    identity = before["identity"]
    paired_metrics = {
        metric.key: metrics[metric.key]
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "paired"
    }
    return {
        "schema_version": "firelens_upgrade_before_snapshot_seal.v1",
        "benchmark_id": spec.benchmark_id,
        "sealed_by": normalized_owner,
        "sealed_at": sealed_at,
        "before_snapshot": {
            "path": relative_before,
            "sha256": file_sha256(resolved_before),
        },
        "candidate_identity": _candidate_identity(before),
        "spec_identity": {
            "path": spec_path.resolve().relative_to(ROOT).as_posix(),
            "sha256": identity["spec_sha256"],
        },
        "dataset_identity": {
            "registry": spec.dataset_role_registry,
            "identity_input_sha256": identity["identity_input_sha256"],
        },
        "harness_identity": {
            "harness_input_sha256": identity["harness_input_sha256"],
        },
        "paired_metric_keys": sorted(paired_metrics),
        "paired_metrics_sha256": _sha256_json(paired_metrics),
    }


def _verify_before_snapshot_seal_payload(
    *,
    seal: dict[str, Any],
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
) -> None:
    if seal.get("schema_version") != "firelens_upgrade_before_snapshot_seal.v1":
        raise ValueError("before snapshot seal uses an unsupported schema")
    if seal.get("benchmark_id") != spec.benchmark_id:
        raise ValueError("before snapshot seal uses the wrong benchmark_id")
    owner = seal.get("sealed_by")
    if (
        not isinstance(owner, str)
        or not owner.strip()
        or owner.strip().casefold() in {"owner", "unknown", "tbd"}
    ):
        raise ValueError("before snapshot seal requires a named owner")
    _parse_attestation_timestamp(seal.get("sealed_at"))
    metrics = _validate_before_snapshot_contract(before, spec, spec_path)
    resolved_before, relative_before = _repo_relative_path(
        before_path, context="before snapshot"
    )
    before_commitment = seal.get("before_snapshot")
    if not isinstance(before_commitment, dict) or before_commitment != {
        "path": relative_before,
        "sha256": file_sha256(resolved_before),
    }:
        raise ValueError("before snapshot seal does not match the supplied snapshot")
    identity = before["identity"]
    expected_paired_metrics = {
        metric.key: metrics[metric.key]
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "paired"
    }
    expected = {
        "candidate_identity": _candidate_identity(before),
        "spec_identity": {
            "path": spec_path.resolve().relative_to(ROOT).as_posix(),
            "sha256": identity["spec_sha256"],
        },
        "dataset_identity": {
            "registry": spec.dataset_role_registry,
            "identity_input_sha256": identity["identity_input_sha256"],
        },
        "harness_identity": {
            "harness_input_sha256": identity["harness_input_sha256"],
        },
        "paired_metric_keys": sorted(expected_paired_metrics),
        "paired_metrics_sha256": _sha256_json(expected_paired_metrics),
    }
    for key, value in expected.items():
        if seal.get(key) != value:
            raise ValueError(f"before snapshot seal has a mismatched {key}")


def _verify_tracked_before_snapshot_seal(
    *, spec: BenchmarkSpec, spec_path: Path, before_path: Path
) -> dict[str, Any]:
    seal_path, _ = _spec_seal_path(spec)
    if not seal_path.is_file():
        raise ValueError("tracked before snapshot seal is missing")
    if not _path_is_tracked_and_unmodified(seal_path):
        raise ValueError("before snapshot seal must be tracked and unmodified")
    seal = _read_report(seal_path)
    before = _read_report(before_path)
    if seal is None or before is None:
        raise ValueError("before snapshot seal and snapshot must both be readable")
    _verify_before_snapshot_seal_payload(
        seal=seal,
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
    )
    return before


def seal_before(args: argparse.Namespace) -> int:
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path)
    if not spec.frozen_before_upgrade:
        raise ValueError("benchmark specification is not frozen")
    if _tracked_dirty() or _relevant_untracked_paths():
        raise ValueError("before sealing requires a clean, fully tracked benchmark worktree")
    seal_path, relative_seal = _spec_seal_path(spec)
    if seal_path.exists():
        raise FileExistsError(f"refusing to overwrite before snapshot seal: {relative_seal}")
    before_path = args.before.resolve()
    before = _read_report(before_path)
    if before is None:
        raise ValueError("before snapshot is required")
    identity = before.get("identity") or {}
    if identity.get("commit") != _git("rev-parse", "HEAD"):
        raise ValueError("before snapshot commit is not the current baseline commit")
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner=args.owner,
        sealed_at=datetime.now(UTC).isoformat(),
    )
    seal_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(seal_path) as stream:
        json.dump(seal, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "seal": relative_seal,
                "before_snapshot_sha256": seal["before_snapshot"]["sha256"],
                "sealed_by": seal["sealed_by"],
                "status": "created_untracked_commit_required",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def capture(args: argparse.Namespace) -> int:
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path)
    rate_limit_evidence = getattr(args, "rate_limit_evidence", None)
    rollback_evidence = getattr(args, "rollback_evidence", None)
    before_snapshot = getattr(args, "before_snapshot", None)
    semantic_holdout_report_path = getattr(args, "semantic_holdout_report", None)
    semantic_holdout_review_bundle_path = getattr(args, "semantic_holdout_review_bundle", None)
    semantic_holdout_summary_path = getattr(args, "semantic_holdout_summary", None)
    frontend_manual_review_bundle_path = getattr(args, "frontend_manual_review_bundle", None)
    runtime_artifact_args = {
        "vercel_artifact_root": getattr(args, "vercel_artifact_root", None),
        "vercel_artifact_id": getattr(args, "vercel_artifact_id", None),
        "vercel_platform_root": getattr(args, "vercel_platform_root", None),
        "docker_artifact_root": getattr(args, "docker_artifact_root", None),
        "docker_artifact_id": getattr(args, "docker_artifact_id", None),
        "docker_platform_root": getattr(args, "docker_platform_root", None),
    }
    if not spec.frozen_before_upgrade:
        raise ValueError("benchmark specification is not frozen")
    if _tracked_dirty():
        raise ValueError("benchmark capture requires a clean tracked worktree")
    relevant_untracked = _relevant_untracked_paths()
    if relevant_untracked:
        raise ValueError(
            "benchmark capture requires all runtime and benchmark inputs to be tracked; "
            f"untracked={relevant_untracked}"
        )
    before_snapshot_ancestry: dict[str, Any] | None = None
    verified_before: dict[str, Any] | None = None
    after_preflight_commit: str | None = None
    frontend_manual_prevalidated: dict[str, Any] | None = None
    if args.label == "after":
        if before_snapshot is None:
            raise ValueError("after capture requires the sealed before snapshot")
        verified_before = _verify_tracked_before_snapshot_seal(
            spec=spec,
            spec_path=spec_path,
            before_path=before_snapshot.resolve(),
        )
        after_preflight_commit = _current_git_commit(context="after capture candidate")
        before_snapshot_ancestry = _resolve_before_snapshot_ancestry(
            spec=spec,
            before=verified_before,
            after_commit=after_preflight_commit,
        )
    if args.label == "before" and frontend_manual_review_bundle_path is not None:
        raise ValueError("frontend manual review is required-after-only")
    if args.label == "before" and args.retrieval_qualification is not None:
        raise ValueError("sealed retrieval qualification is required-after-only")
    if args.label == "before" and any(
        path is not None
        for path in (
            semantic_holdout_report_path,
            semantic_holdout_review_bundle_path,
            semantic_holdout_summary_path,
        )
    ):
        raise ValueError("semantic holdout qualification is required-after-only")
    if args.label == "before" and args.preview_report is not None:
        raise ValueError("preview qualification is required-after-only")
    if args.label == "before" and any(
        path is not None
        for path in (args.deployment_report, rate_limit_evidence, rollback_evidence)
    ):
        raise ValueError("deployment qualification is required-after-only")
    if args.label == "before" and any(
        value is not None for value in runtime_artifact_args.values()
    ):
        raise ValueError("runtime artifact qualification is required-after-only")
    if args.deployment_report is None and (
        rate_limit_evidence is not None or rollback_evidence is not None
    ):
        raise ValueError("raw deployment evidence requires a deployment report")
    semantic_artifacts = (
        args.semantic_report,
        args.semantic_review_sidecar,
        args.semantic_review_summary,
        args.semantic_review_qualification,
    )
    if any(path is not None for path in semantic_artifacts) and not all(
        path is not None for path in semantic_artifacts
    ):
        raise ValueError(
            "semantic review evidence requires the source report, review sidecar, summary, "
            "and blind-review qualification manifest"
        )
    if (semantic_holdout_report_path is None) != (semantic_holdout_review_bundle_path is None):
        raise ValueError(
            "semantic holdout evidence requires both the candidate report and review bundle"
        )
    if semantic_holdout_summary_path is not None and semantic_holdout_report_path is None:
        raise ValueError(
            "semantic holdout summary requires its raw candidate report and review bundle"
        )
    semantic_holdout_prevalidated: dict[str, Any] | None = None
    if semantic_holdout_report_path is not None:
        semantic_holdout_prevalidated = validate_semantic_holdout(
            semantic_holdout_report_path,
            semantic_holdout_review_bundle_path,
            SEMANTIC_HOLDOUT_MANIFEST,
            SEMANTIC_DEVELOPMENT_REGISTRY,
            semantic_holdout_summary_path,
        )
    retrieval_review_artifacts = (
        args.retrieval_review_sidecar,
        args.retrieval_review_summary,
        args.retrieval_review_qualification,
    )
    if any(path is not None for path in retrieval_review_artifacts) and not all(
        path is not None for path in retrieval_review_artifacts
    ):
        raise ValueError(
            "retrieval review evidence requires its sidecar, summary, and blind-review "
            "qualification manifest"
        )
    if args.label == "after":
        if frontend_manual_review_bundle_path is None:
            raise ValueError("after capture requires the frontend manual review bundle")
        if after_preflight_commit is None:
            raise ValueError("after capture lost its candidate commit preflight")
        frontend_manual_prevalidated = validate_frontend_manual_review(
            frontend_manual_review_bundle_path,
            expected_commit=after_preflight_commit,
        )
    output_dir = args.output_dir.resolve()
    runtime_artifact_prevalidated: dict[str, Any] | None = None
    config = FireLensConfig.from_env(ROOT)
    corpus_manifest = _read_report(config.corpus_manifest_path)
    if not isinstance(corpus_manifest, dict) or not isinstance(
        corpus_manifest.get("corpus_version"), str
    ):
        raise ValueError("runtime corpus manifest has no corpus_version")
    corpus_version = corpus_manifest["corpus_version"]
    if args.label == "after":
        missing_runtime_inputs = sorted(
            name for name, value in runtime_artifact_args.items() if value is None
        )
        if missing_runtime_inputs:
            raise ValueError(
                "after capture requires capture-owned Vercel and Docker runtime artifact "
                f"inputs; missing={missing_runtime_inputs}"
            )
        if after_preflight_commit is None:
            raise ValueError("after capture lost its candidate commit preflight")
        runtime_artifact_prevalidated = _build_runtime_artifact_pair(
            spec=spec,
            commit=after_preflight_commit,
            release_version=config.release_version,
            output_dir=output_dir,
            **runtime_artifact_args,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    ux_template = output_dir / "ux_tasks.template.yaml"
    _write_ux_template(ux_template, args.label, spec)
    _write_deployment_template(output_dir / "deployment.template.yaml", args.label)

    verification = _run_logged(["make", "verify"], output_dir / "verification.log")
    commit = _git("rev-parse", "HEAD")
    if after_preflight_commit is not None and commit != after_preflight_commit:
        raise ValueError(
            "after candidate commit changed during benchmark capture; rerun from a stable checkout"
        )
    if args.label == "after":
        frontend_manual_review = validate_frontend_manual_review(
            frontend_manual_review_bundle_path,
            expected_commit=commit,
        )
        if frontend_manual_review != frontend_manual_prevalidated:
            raise ValueError("frontend manual review evidence changed during benchmark capture")
    else:
        frontend_manual_review = {
            "status": "required_after_only",
            "accessibility_qualified": None,
            "product_safety_qualified": None,
            "open_finding_count": None,
        }
    execution_environment = _execution_environment()
    frontend_capture = _capture_frontend_surface(
        output_dir=output_dir,
        expected_commit=commit,
        expected_environment=execution_environment,
    )
    frontend_bundle = frontend_capture["bundle"]
    frontend_surface = frontend_capture["surface"]
    hard_path = output_dir / "hard_probe_offline.json"
    hard_path.unlink(missing_ok=True)
    hard_run = _run_logged(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/run_hard_probe.py",
            "--mode",
            "offline",
            "--output",
            str(hard_path),
        ],
        output_dir / "hard_probe_offline.log",
    )
    if not hard_run["passed"]:
        raise RuntimeError("offline hard probe failed; see its benchmark log")

    live_path = output_dir / "live_qualification.json"
    if args.skip_live:
        live_path.unlink(missing_ok=True)
        live_run: dict[str, Any] = {"passed": None, "status": "skipped"}
    else:
        live_path.unlink(missing_ok=True)
        live_run = _run_logged(
            [
                str(ROOT / ".venv/bin/python"),
                "scripts/run_live_qualification.py",
                "--output",
                str(live_path),
            ],
            output_dir / "live_qualification.log",
        )

    hard = _hard_probe(_read_report(hard_path), expected_mode="offline")
    live = _live(
        None if args.skip_live else _read_report(live_path) if live_path.is_file() else None
    )
    _check_report_identity("offline hard probe", hard.get("commit"), commit)
    _check_report_identity(
        "live qualification", live.get("commit"), commit, required=not args.skip_live
    )

    qualified_hard = _hard_probe(
        _read_report(args.qualified_hard_probe), expected_mode="qualified"
    )
    development_retrieval = _development_retrieval(
        _read_report(args.development_retrieval_report)
    )
    retrieval = _retrieval_qualification(_read_report(args.retrieval_qualification))
    submitted_semantic_summary = _read_report(args.semantic_review_summary)
    if submitted_semantic_summary is not None:
        recomputed_semantic_summary = validate_owner_review(
            args.semantic_report,
            args.semantic_review_sidecar,
            expected_case_count=50,
        )
        _assert_recomputed_summary_matches(
            submitted_semantic_summary,
            recomputed_semantic_summary,
            context="semantic review",
        )
        semantic = _review(
            recomputed_semantic_summary,
            expected_cases=50,
            expected_summary_version="firelens_owner_semantic_review_summary.v1",
        )
        semantic_review_qualification = verify_review_qualification_package(
            args.semantic_review_qualification,
            source_path=args.semantic_report,
            sidecar_path=args.semantic_review_sidecar,
            summary_path=args.semantic_review_summary,
            expected_suite_kind="conversation",
            expected_case_count=50,
        ).model_dump(mode="json")
    else:
        semantic = _review(
            None,
            expected_cases=50,
            expected_summary_version="firelens_owner_semantic_review_summary.v1",
        )
        semantic_review_qualification = None
    if semantic_holdout_prevalidated is not None:
        semantic_holdout = validate_semantic_holdout(
            semantic_holdout_report_path,
            semantic_holdout_review_bundle_path,
            SEMANTIC_HOLDOUT_MANIFEST,
            SEMANTIC_DEVELOPMENT_REGISTRY,
            semantic_holdout_summary_path,
        )
    else:
        semantic_holdout = _semantic_holdout(None)
    submitted_retrieval_review = _read_report(args.retrieval_review_summary)
    if submitted_retrieval_review is not None:
        recomputed_retrieval_review = validate_retrieval_owner_review(
            ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
            args.retrieval_review_sidecar,
            expected_case_count=47,
        )
        _assert_recomputed_summary_matches(
            submitted_retrieval_review,
            recomputed_retrieval_review,
            context="retrieval owner review",
        )
        retrieval_review = _review(
            recomputed_retrieval_review,
            expected_cases=47,
            expected_summary_version="firelens_retrieval_owner_review_summary.v1",
        )
        retrieval_review_qualification = verify_review_qualification_package(
            args.retrieval_review_qualification,
            source_path=ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
            sidecar_path=args.retrieval_review_sidecar,
            summary_path=args.retrieval_review_summary,
            expected_suite_kind="retrieval",
            expected_case_count=47,
        ).model_dump(mode="json")
    else:
        retrieval_review = _review(
            None,
            expected_cases=47,
            expected_summary_version="firelens_retrieval_owner_review_summary.v1",
        )
        retrieval_review_qualification = None
    preview = _preview(_read_report(args.preview_report))
    ux = _ux(_read_report(args.ux_report), spec)
    deployment = _deployment(
        _read_report(args.deployment_report),
        rate_limit_artifact=rate_limit_evidence,
        rollback_artifact=rollback_evidence,
    )
    runtime_configuration = benchmark_runtime_configuration(config)
    configuration_sha256 = hashlib.sha256(
        json.dumps(
            runtime_configuration,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    expected_dataset_sha256 = file_sha256(ROOT / "data/evaluation/hard_probe.v1.yaml")
    expected_corpus_sha256 = file_sha256(config.corpus_path)
    expected_vector_sha256 = file_sha256(config.vector_matrix_path)
    expected_document_context_sha256 = (
        file_sha256(config.document_context_path)
        if config.document_context_path.is_file()
        else None
    )
    expected_repairs_sha256 = file_sha256(ROOT / "data/repairs/text_overrides.yaml")

    for name, probe in (("offline hard probe", hard), ("qualified hard probe", qualified_hard)):
        if probe.get("status") == "not_run":
            continue
        if probe.get("dataset_sha256") != expected_dataset_sha256:
            raise ValueError(f"{name} uses the wrong dataset")
        if probe.get("corpus_sha256") != expected_corpus_sha256:
            raise ValueError(f"{name} uses the wrong corpus")
        if probe.get("vector_matrix_sha256") != expected_vector_sha256:
            raise ValueError(f"{name} uses the wrong vector matrix")
        if probe.get("document_context_sha256") != expected_document_context_sha256:
            raise ValueError(f"{name} uses the wrong document context")
        if probe.get("repairs_sha256") != expected_repairs_sha256:
            raise ValueError(f"{name} uses the wrong repair governance")
        if probe.get("configuration_sha256") != configuration_sha256:
            raise ValueError(f"{name} uses the wrong runtime configuration")

    if args.qualified_hard_probe is not None:
        _check_report_identity("qualified hard probe", qualified_hard.get("commit"), commit)
    if args.development_retrieval_report is not None:
        _check_report_identity(
            "development retrieval", development_retrieval.get("commit"), commit
        )
        if development_retrieval.get("dataset_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1.yaml"
        ):
            raise ValueError("development retrieval report uses the wrong dataset")
        if development_retrieval.get("relevance_addendum_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml"
        ):
            raise ValueError("development retrieval report uses the wrong relevance addendum")
        if development_retrieval.get("corpus_sha256") != expected_corpus_sha256:
            raise ValueError("development retrieval report uses the wrong corpus")
        if development_retrieval.get("vector_matrix_sha256") != expected_vector_sha256:
            raise ValueError("development retrieval report uses the wrong vector matrix")
        if (
            development_retrieval.get("document_context_sha256")
            != expected_document_context_sha256
        ):
            raise ValueError("development retrieval report uses the wrong document context")
        if development_retrieval.get("repairs_sha256") != expected_repairs_sha256:
            raise ValueError("development retrieval report uses the wrong repair governance")
        if development_retrieval.get("configuration") != runtime_configuration:
            raise ValueError(
                "development retrieval report uses the wrong runtime configuration"
            )
    if args.retrieval_qualification is not None:
        _check_report_identity("sealed retrieval", retrieval.get("commit"), commit)
        if retrieval.get("dataset_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
        ):
            raise ValueError("sealed retrieval report uses the wrong dataset")
        if retrieval.get("dataset_manifest_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
        ):
            raise ValueError("sealed retrieval report uses the wrong manifest")
        if retrieval.get("corpus_sha256") != expected_corpus_sha256:
            raise ValueError("sealed retrieval report uses the wrong corpus")
        if retrieval.get("vector_matrix_sha256") != expected_vector_sha256:
            raise ValueError("sealed retrieval report uses the wrong vector matrix")
        if retrieval.get("document_context_sha256") != expected_document_context_sha256:
            raise ValueError("sealed retrieval report uses the wrong document context")
        if retrieval.get("repairs_sha256") != expected_repairs_sha256:
            raise ValueError("sealed retrieval report uses the wrong repair governance")
        if retrieval.get("configuration_sha256") != configuration_sha256:
            raise ValueError("sealed retrieval report uses the wrong runtime configuration")
    if args.semantic_review_summary is not None:
        if semantic.get("report_sha256") != file_sha256(args.semantic_report):
            raise ValueError("semantic review summary does not match its source report")
        if semantic.get("review_sha256") != file_sha256(args.semantic_review_sidecar):
            raise ValueError("semantic review summary does not match its review sidecar")
        _check_report_identity("semantic review", semantic.get("commit"), commit)
        if semantic.get("dataset_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1_1_conversation.yaml"
        ):
            raise ValueError("semantic review uses the wrong conversation dataset")
        if semantic.get("corpus_sha256") != expected_corpus_sha256:
            raise ValueError("semantic review uses the wrong corpus")
        if semantic.get("vector_matrix_sha256") != expected_vector_sha256:
            raise ValueError("semantic review uses the wrong vector matrix")
        if semantic.get("document_context_sha256") != expected_document_context_sha256:
            raise ValueError("semantic review uses the wrong document context")
        if semantic.get("repairs_sha256") != expected_repairs_sha256:
            raise ValueError("semantic review uses the wrong repair governance")
        if semantic.get("configuration_sha256") != configuration_sha256:
            raise ValueError("semantic review uses the wrong runtime configuration")
    if args.retrieval_review_summary is not None:
        if retrieval_review.get("review_sha256") != file_sha256(args.retrieval_review_sidecar):
            raise ValueError("retrieval review summary does not match its review sidecar")
        if retrieval_review.get("dataset_sha256") != file_sha256(
            ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
        ):
            raise ValueError("retrieval review uses the wrong sealed dataset")
    if semantic_holdout_report_path is not None:
        _check_report_identity("semantic holdout", semantic_holdout.get("commit"), commit)
        if semantic_holdout.get("corpus_sha256") != file_sha256(config.corpus_path):
            raise ValueError("semantic holdout uses the wrong corpus")
        if semantic_holdout.get("vector_matrix_sha256") != file_sha256(
            config.vector_matrix_path
        ):
            raise ValueError("semantic holdout uses the wrong vector matrix")
        if semantic_holdout.get("document_context_sha256") != expected_document_context_sha256:
            raise ValueError("semantic holdout uses the wrong document context")
        if semantic_holdout.get("repairs_sha256") != expected_repairs_sha256:
            raise ValueError("semantic holdout uses the wrong repair governance")
        if semantic_holdout.get("configuration_sha256") != configuration_sha256:
            raise ValueError("semantic holdout uses the wrong runtime configuration")
    if args.ux_report is not None:
        _check_report_identity("UX", ux.get("commit"), commit)
        if ux.get("label") != args.label or ux.get("protocol_id") != spec.benchmark_id:
            raise ValueError("UX report does not match the capture label and protocol")
    if args.preview_report is not None:
        _check_report_identity("preview", preview.get("commit"), commit)
    if args.deployment_report is not None:
        _check_report_identity("deployment", deployment.get("commit"), commit)
        if deployment.get("label") != args.label:
            raise ValueError("deployment report does not match the capture label")
        if args.preview_report is not None and deployment.get(
            "candidate_deployment_id"
        ) != preview.get("deployment_id"):
            raise ValueError("deployment controls do not target the qualified preview")

    if args.label == "after":
        final_frontend_manual_review = validate_frontend_manual_review(
            frontend_manual_review_bundle_path,
            expected_commit=commit,
        )
        if final_frontend_manual_review != frontend_manual_review:
            raise ValueError("frontend manual review evidence changed during benchmark capture")
        frontend_manual_review = final_frontend_manual_review

    if _tracked_dirty() or _relevant_untracked_paths():
        raise ValueError(
            "benchmark commands changed the tracked or relevant untracked worktree"
        )
    if args.label == "after":
        if verified_before is None or before_snapshot_ancestry is None:
            raise ValueError("after capture lost its verified before-seal ancestry state")
        final_ancestry = _resolve_before_snapshot_ancestry(
            spec=spec,
            before=verified_before,
            after_commit=commit,
        )
        if final_ancestry != before_snapshot_ancestry:
            raise ValueError(
                "before-seal ancestry changed during benchmark capture; rerun from a "
                "stable checkout"
            )
        before_snapshot_ancestry = final_ancestry

    runtime_artifact_paths: dict[str, Path] = {}
    if args.label == "after":
        if runtime_artifact_prevalidated is None:
            raise ValueError("after capture lost its runtime artifact preflight evidence")
        runtime_artifact_final = _build_runtime_artifact_pair(
            spec=spec,
            commit=commit,
            release_version=config.release_version,
            output_dir=output_dir,
            **runtime_artifact_args,
        )
        runtime_artifact = _finalize_runtime_artifact_pair(
            runtime_artifact_prevalidated, runtime_artifact_final
        )
        runtime_artifact_paths = _write_runtime_artifact_evidence(output_dir, runtime_artifact)
    else:
        runtime_artifact = {"status": "required_after_only"}

    identity_hashes = {
        relative: file_sha256(ROOT / relative) for relative in spec.identity_inputs
    }
    harness_hashes = {
        relative: file_sha256(ROOT / relative) for relative in spec.harness_inputs
    }
    snapshot: dict[str, Any] = {
        "schema_version": "firelens_upgrade_benchmark_snapshot.v2",
        "benchmark_id": spec.benchmark_id,
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": {
            "commit": commit,
            "branch": _git("branch", "--show-current"),
            "candidate_id": _runtime_candidate_id(spec.benchmark_id, commit),
            "tracked_dirty": _tracked_dirty(),
            "untracked_paths": _git("ls-files", "--others", "--exclude-standard").splitlines(),
            "release_version": config.release_version,
            "corpus_version": corpus_version,
            "spec_sha256": file_sha256(spec_path),
            "identity_input_sha256": identity_hashes,
            "harness_input_sha256": harness_hashes,
            "corpus_sha256": file_sha256(config.corpus_path),
            "vector_matrix_sha256": file_sha256(config.vector_matrix_path),
            "vector_manifest_sha256": file_sha256(config.vector_manifest_path),
            "document_context_sha256": expected_document_context_sha256,
            "repairs_sha256": expected_repairs_sha256,
            "configuration_sha256": configuration_sha256,
            "configuration": runtime_configuration,
            "execution_environment": execution_environment,
        },
        "verification": verification,
        "hard_probe_run": hard_run,
        "hard_probe_offline": hard,
        "hard_probe_qualified": qualified_hard,
        "live_run": live_run,
        "live": live,
        "frontend_surface_run": {
            "run": frontend_capture["run"],
            "started_at": frontend_capture["started_at"],
            "finished_at": frontend_capture["finished_at"],
        },
        "frontend_bundle": frontend_bundle,
        "frontend_surface": frontend_surface,
        "frontend_manual_review": frontend_manual_review,
        "runtime_artifact": runtime_artifact,
        "before_snapshot_ancestry": before_snapshot_ancestry,
        "development_retrieval": development_retrieval,
        "semantic_review": semantic,
        "semantic_review_qualification": semantic_review_qualification,
        "semantic_holdout": semantic_holdout,
        "retrieval_review": retrieval_review,
        "retrieval_review_qualification": retrieval_review_qualification,
        "retrieval_qualification": retrieval,
        "ux": ux,
        "preview": preview,
        "deployment": deployment,
        "artifacts": {
            "hard_probe_offline": _artifact(hard_path),
            "live_qualification": _artifact(live_path if live_path.is_file() else None),
            "qualified_hard_probe": _artifact(args.qualified_hard_probe),
            "development_retrieval": _artifact(args.development_retrieval_report),
            "retrieval_qualification": _artifact(args.retrieval_qualification),
            "semantic_review_summary": _artifact(args.semantic_review_summary),
            "semantic_report": _artifact(args.semantic_report),
            "semantic_review_sidecar": _artifact(args.semantic_review_sidecar),
            "semantic_review_qualification": _artifact(args.semantic_review_qualification),
            "semantic_holdout_report": _artifact(semantic_holdout_report_path),
            "semantic_holdout_review_bundle": _artifact(semantic_holdout_review_bundle_path),
            "semantic_holdout_summary": _artifact(semantic_holdout_summary_path),
            "semantic_holdout_manifest": _artifact(
                SEMANTIC_HOLDOUT_MANIFEST if semantic_holdout_report_path is not None else None
            ),
            "semantic_development_registry": _artifact(
                SEMANTIC_DEVELOPMENT_REGISTRY
                if semantic_holdout_report_path is not None
                else None
            ),
            "retrieval_review_summary": _artifact(args.retrieval_review_summary),
            "retrieval_review_sidecar": _artifact(args.retrieval_review_sidecar),
            "retrieval_review_qualification": _artifact(args.retrieval_review_qualification),
            "ux_report": _artifact(args.ux_report),
            "preview_report": _artifact(args.preview_report),
            "deployment_report": _artifact(args.deployment_report),
            "rate_limit_evidence": _artifact(rate_limit_evidence),
            "rollback_evidence": _artifact(rollback_evidence),
            "frontend_surface_report": _artifact(frontend_capture["report_path"]),
            "frontend_manual_review_bundle": _artifact(frontend_manual_review_bundle_path),
            "runtime_artifact_vercel_inventory": _artifact(
                runtime_artifact_paths.get("vercel_inventory")
            ),
            "runtime_artifact_docker_inventory": _artifact(
                runtime_artifact_paths.get("docker_inventory")
            ),
            "runtime_artifact_comparison": _artifact(runtime_artifact_paths.get("comparison")),
            "runtime_artifact_vercel_candidate": _artifact(
                runtime_artifact_paths.get("vercel_runtime_candidate")
            ),
            "runtime_artifact_docker_candidate": _artifact(
                runtime_artifact_paths.get("docker_runtime_candidate")
            ),
        },
    }
    snapshot["metrics"] = _metrics(snapshot)
    missing_required_metrics = sorted(
        metric.key
        for metric in spec.comparison_metrics
        if (
            (args.label == "before" and metric.comparison_mode == "paired")
            or (args.label == "after" and metric.required_after)
        )
        and snapshot["metrics"].get(metric.key) is None
    )
    snapshot["capture_complete"] = not missing_required_metrics
    snapshot["missing_required_metrics"] = missing_required_metrics
    output_path = output_dir / "snapshot.json"
    with atomic_text_writer(output_path) as stream:
        json.dump(snapshot, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "snapshot": str(output_path.relative_to(ROOT)),
                "commit": commit,
                "verification_passed": snapshot["metrics"]["verification_passed"],
                "offline_hard_probe_pass_rate": snapshot["metrics"][
                    "offline_hard_probe_pass_rate"
                ],
                "live_qualified": snapshot["metrics"]["live_qualified"],
                "missing_required_metrics": missing_required_metrics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if verification["passed"] and hard["pass_rate"] == 1.0 and not missing_required_metrics
        else 2
    )


def _validated_metric_value(metric: MetricSpec, value: Any, *, label: str) -> Any:
    if value is None:
        return None
    if metric.value_type == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{metric.key} {label} value must be a strict boolean")
        return value
    if metric.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{metric.key} {label} value must be an integer")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{metric.key} {label} value must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{metric.key} {label} value must be finite")
    return value


def _target_passed(metric: MetricSpec, value: Any) -> bool | None:
    if metric.gate_operator is None:
        return None
    if value is None:
        return False
    value = _validated_metric_value(metric, value, label="after")
    if metric.gate_operator == "eq":
        return type(value) is type(metric.gate_value) and value == metric.gate_value
    target = float(metric.gate_value)
    if metric.gate_operator == "gte":
        return float(value) >= target
    return float(value) <= target


def _verdict(metric: MetricSpec, before: Any, after: Any) -> tuple[str, float | None]:
    if metric.comparison_mode == "after_only":
        if before is not None:
            raise ValueError(f"after-only metric {metric.key} must not have a before value")
        if after is not None:
            _validated_metric_value(metric, after, label="after")
        return "after_only", None
    if metric.comparison_mode == "prerequisite":
        if before is not None:
            _validated_metric_value(metric, before, label="before")
        if after is not None:
            _validated_metric_value(metric, after, label="after")
        return "prerequisite", None
    if before is None or after is None:
        return "not_measured", None
    before = _validated_metric_value(metric, before, label="before")
    after = _validated_metric_value(metric, after, label="after")
    if isinstance(before, bool) and isinstance(after, bool):
        if before == after:
            return "within_tolerance", 0.0
        directed = (
            float(after) - float(before)
            if metric.direction == "higher_is_better"
            else float(before) - float(after)
        )
        return ("improved" if directed > 0 else "regressed"), float(after) - float(before)
    delta = float(after) - float(before)
    tolerance = metric.tolerance
    if tolerance is None:
        raise ValueError(f"paired numeric metric {metric.key} has no tolerance")
    limit = max(tolerance.absolute, abs(float(before)) * tolerance.relative)
    directed = delta if metric.direction == "higher_is_better" else -delta
    if metric.comparison_requirement == "must_improve":
        if directed > 0 and directed >= limit:
            return "improved", delta
        if directed < -limit:
            return "regressed", delta
        return "within_tolerance", delta
    if directed > limit:
        return "improved", delta
    if directed < -limit:
        return "regressed", delta
    return "within_tolerance", delta


def _comparison_requirement_passed(metric: MetricSpec, verdict: str) -> bool | None:
    if metric.comparison_mode != "paired":
        return None
    if verdict == "not_measured":
        return False
    if metric.comparison_requirement == "must_improve":
        return verdict == "improved"
    if metric.comparison_requirement == "no_regression":
        return verdict in {"improved", "within_tolerance"}
    return True


def compare_snapshots(
    before: dict[str, Any], after: dict[str, Any], spec: BenchmarkSpec
) -> dict[str, Any]:
    if (
        before.get("benchmark_id") != spec.benchmark_id
        or after.get("benchmark_id") != spec.benchmark_id
    ):
        raise ValueError("snapshot benchmark_id does not match the specification")
    if before.get("label") != "before" or after.get("label") != "after":
        raise ValueError("comparison requires explicit before and after snapshot labels")
    before_identity = before.get("identity") or {}
    after_identity = after.get("identity") or {}
    if (
        before.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2"
        or after.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2"
    ):
        raise ValueError("before and after snapshots must use snapshot schema v2")
    if before_identity.get("spec_sha256") != after_identity.get("spec_sha256"):
        raise ValueError("before and after snapshots use different benchmark specifications")
    if before_identity.get("identity_input_sha256") != after_identity.get(
        "identity_input_sha256"
    ):
        raise ValueError("before and after snapshots use different frozen evaluation inputs")
    if before_identity.get("harness_input_sha256") != after_identity.get(
        "harness_input_sha256"
    ):
        raise ValueError("before and after snapshots use different benchmark harnesses")

    environment_comparability = _execution_environment_comparability(
        before_identity, after_identity
    )
    ux_comparability = _ux_distribution_comparability(
        before.get("ux") or {}, after.get("ux") or {}
    )
    comparability_failures = [
        name
        for name, result in (
            ("execution_environment", environment_comparability),
            ("ux_sampling", ux_comparability),
        )
        if not result["passed"]
    ]

    before_metrics = _validated_snapshot_metrics(before, spec, label="before")
    after_metrics = _validated_snapshot_metrics(after, spec, label="after")
    rows = []
    for metric in spec.comparison_metrics:
        before_value = before_metrics.get(metric.key)
        after_value = after_metrics.get(metric.key)
        verdict, delta = _verdict(metric, before_value, after_value)
        requirement_passed = _comparison_requirement_passed(metric, verdict)
        rows.append(
            {
                "key": metric.key,
                "track": metric.track,
                "direction": metric.direction,
                "value_type": metric.value_type,
                "comparison_mode": metric.comparison_mode,
                "comparison_requirement": metric.comparison_requirement,
                "tolerance": metric.tolerance.model_dump() if metric.tolerance else None,
                "before": before_value,
                "after": after_value,
                "delta": delta,
                "verdict": verdict,
                "comparison_requirement_passed": requirement_passed,
                "required_after": metric.required_after,
                "gate_operator": metric.gate_operator,
                "gate_value": metric.gate_value,
                "after_gate_passed": _target_passed(metric, after_value),
            }
        )
    required = [row for row in rows if row["required_after"]]
    missing_before = [
        row["key"]
        for row in rows
        if row["comparison_mode"] == "paired" and row["before"] is None
    ]
    missing = [row["key"] for row in required if row["after"] is None]
    failed = [row["key"] for row in required if row["after_gate_passed"] is False]
    regressions = [row["key"] for row in rows if row["verdict"] == "regressed"]
    insufficient_improvement = [
        row["key"]
        for row in rows
        if row["comparison_requirement"] == "must_improve"
        and row["comparison_requirement_passed"] is False
    ]
    return {
        "schema_version": "firelens_upgrade_benchmark_comparison.v2",
        "benchmark_id": spec.benchmark_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "before": {
            "label": before.get("label"),
            "commit": before_identity.get("commit"),
        },
        "after": {
            "label": after.get("label"),
            "commit": after_identity.get("commit"),
        },
        "comparability": {
            "execution_environment": environment_comparability,
            "ux_sampling": ux_comparability,
        },
        "metrics": rows,
        "summary": {
            "improved": sum(row["verdict"] == "improved" for row in rows),
            "regressed": len(regressions),
            "within_tolerance": sum(row["verdict"] == "within_tolerance" for row in rows),
            "not_measured": sum(row["verdict"] == "not_measured" for row in rows),
            "missing_required_before": missing_before,
            "missing_required_after": missing,
            "failed_after_gates": failed,
            "regressions": regressions,
            "insufficient_improvement": insufficient_improvement,
            "comparability_failures": comparability_failures,
            "benchmark_gate_passed": not any(
                (
                    missing_before,
                    missing,
                    failed,
                    regressions,
                    insufficient_improvement,
                    comparability_failures,
                )
            ),
        },
    }


def _markdown(comparison: dict[str, Any]) -> str:
    ancestry = comparison.get("before_snapshot_ancestry") or {}
    lines = [
        "# FireLens V1.5-2 before/after benchmark",
        "",
        f"Before: `{comparison['before']['label']}` at `{comparison['before']['commit']}`  ",
        f"After: `{comparison['after']['label']}` at `{comparison['after']['commit']}`",
        f"Before-seal commit: `{ancestry.get('seal_introducing_commit', 'not verified')}`",
        "",
        "| Metric | Track | Before | After | Delta | Verdict | Gate |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in comparison["metrics"]:
        gate = (
            "pass"
            if row["after_gate_passed"] is True
            else "fail"
            if row["after_gate_passed"] is False
            else "comparison only"
        )
        lines.append(
            "| {key} | {track} | {before} | {after} | {delta} | {verdict} | {gate} |".format(
                key=row["key"],
                track=row["track"],
                before=row["before"] if row["before"] is not None else "not measured",
                after=row["after"] if row["after"] is not None else "not measured",
                delta=row["delta"] if row["delta"] is not None else "—",
                verdict=row["verdict"],
                gate=gate,
            )
        )
    summary = comparison["summary"]
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Improved: {summary['improved']}",
            f"- Regressed: {summary['regressed']}",
            f"- Within tolerance: {summary['within_tolerance']}",
            f"- Not measured: {summary['not_measured']}",
            f"- Benchmark gate passed: {summary['benchmark_gate_passed']}",
            f"- Missing required before metrics: {', '.join(summary['missing_required_before']) or 'none'}",
            f"- Missing required after metrics: {', '.join(summary['missing_required_after']) or 'none'}",
            f"- Failed after gates: {', '.join(summary['failed_after_gates']) or 'none'}",
            f"- Regressions: {', '.join(summary['regressions']) or 'none'}",
            f"- Insufficient improvements: {', '.join(summary['insufficient_improvement']) or 'none'}",
            f"- Comparability failures: {', '.join(summary['comparability_failures']) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines)


def compare(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec.resolve())
    if not spec.frozen_before_upgrade:
        raise ValueError("benchmark specification is not frozen")
    before = _verify_tracked_before_snapshot_seal(
        spec=spec,
        spec_path=args.spec.resolve(),
        before_path=args.before.resolve(),
    )
    after = _read_report(args.after.resolve())
    if after is None:
        raise ValueError("both before and after snapshots are required")
    after_identity = after.get("identity")
    if not isinstance(after_identity, dict):
        raise ValueError("after snapshot has no candidate identity")
    ancestry = _resolve_before_snapshot_ancestry(
        spec=spec,
        before=before,
        after_commit=after_identity.get("commit"),
    )
    if after.get("before_snapshot_ancestry") != ancestry:
        raise ValueError(
            "after snapshot before-seal ancestry evidence is missing or differs from "
            "recomputed Git history; recapture the after candidate"
        )
    current_spec_sha256 = file_sha256(args.spec.resolve())
    if (before.get("identity") or {}).get("spec_sha256") != current_spec_sha256:
        raise ValueError("before snapshot does not match the current benchmark specification")
    current_identity_hashes = {
        relative: file_sha256(ROOT / relative) for relative in spec.identity_inputs
    }
    current_harness_hashes = {
        relative: file_sha256(ROOT / relative) for relative in spec.harness_inputs
    }
    before_identity = before.get("identity") or {}
    if before_identity.get("identity_input_sha256") != current_identity_hashes:
        raise ValueError("current frozen evaluation inputs differ from the before snapshot")
    if before_identity.get("harness_input_sha256") != current_harness_hashes:
        raise ValueError("current benchmark harness differs from the before snapshot")
    comparison = compare_snapshots(before, after, spec)
    comparison["before_snapshot_ancestry"] = ancestry
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(args.output_json) as stream:
        json.dump(comparison, stream, indent=2, sort_keys=True)
        stream.write("\n")
    args.output_markdown.write_text(_markdown(comparison), encoding="utf-8")
    print(json.dumps(comparison["summary"], indent=2, sort_keys=True))
    return 0 if comparison["summary"]["benchmark_gate_passed"] else 2


def _optional_path(value: str | None) -> Path | None:
    return Path(value).resolve() if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    commands = parser.add_subparsers(dest="command", required=True)

    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--label", choices=("before", "after"), required=True)
    capture_parser.add_argument("--output-dir", type=Path, required=True)
    capture_parser.add_argument("--before-snapshot", type=Path)
    capture_parser.add_argument("--skip-live", action="store_true")
    for option in (
        "qualified-hard-probe",
        "development-retrieval-report",
        "retrieval-qualification",
        "semantic-review-summary",
        "semantic-report",
        "semantic-review-sidecar",
        "semantic-review-qualification",
        "semantic-holdout-report",
        "semantic-holdout-review-bundle",
        "semantic-holdout-summary",
        "frontend-manual-review-bundle",
        "retrieval-review-summary",
        "retrieval-review-sidecar",
        "retrieval-review-qualification",
        "ux-report",
        "preview-report",
        "deployment-report",
        "rate-limit-evidence",
        "rollback-evidence",
    ):
        capture_parser.add_argument(f"--{option}", type=_optional_path)
    capture_parser.add_argument("--vercel-artifact-root", type=_optional_path)
    capture_parser.add_argument("--vercel-artifact-id")
    capture_parser.add_argument("--vercel-platform-root")
    capture_parser.add_argument("--docker-artifact-root", type=_optional_path)
    capture_parser.add_argument("--docker-artifact-id")
    capture_parser.add_argument("--docker-platform-root")

    seal_parser = commands.add_parser("seal-before")
    seal_parser.add_argument("--before", type=Path, required=True)
    seal_parser.add_argument("--owner", required=True)

    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    compare_parser.add_argument("--output-json", type=Path, required=True)
    compare_parser.add_argument("--output-markdown", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "capture":
        raise SystemExit(capture(args))
    if args.command == "seal-before":
        raise SystemExit(seal_before(args))
    raise SystemExit(compare(args))


if __name__ == "__main__":
    main()
