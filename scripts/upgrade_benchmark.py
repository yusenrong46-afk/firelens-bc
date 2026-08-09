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
from firelens.evaluation.common import (
    assert_recomputed_summary_matches as _assert_recomputed_summary_matches,
)
from firelens.evaluation.common import sha256_json as _sha256_json
from firelens.evaluation.comparison import (
    _comparison_requirement_passed,
    _markdown,
    _target_passed,
    _verdict,
    compare_snapshots,
)
from firelens.evaluation.frontend_browser import (
    _frontend_axe,
    _frontend_classify_console_errors,
    _frontend_console_event,
    _frontend_http_failure,
    _frontend_layout,
    _frontend_runtime,
)
from firelens.evaluation.frontend_manual_protocol import _frontend_manual_review_protocol
from firelens.evaluation.frontend_manual_review import validate_frontend_manual_review
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
from firelens.evaluation.semantic_holdout import (
    _semantic_holdout,
    validate_semantic_holdout,
)
from firelens.evaluation.semantic_inputs import (
    _semantic_development_registry,
    _semantic_development_registry_payload,
    _semantic_holdout_candidate_report,
    _semantic_holdout_manifest,
    _semantic_holdout_manifest_payload,
    _sorted_unique_strings,
)
from firelens.evaluation.semantic_review import (
    _semantic_actor_case_order,
    _semantic_claim_roster_sha256,
    _semantic_displayed_payload_sha256,
    _semantic_presentation_event_sha256,
    _semantic_presentation_history,
    _semantic_randomization_context_sha256,
)
from firelens.evaluation.snapshot import (
    _candidate_identity,
    _check_report_identity,
    _metrics,
    _validated_metric_value,
    _validated_snapshot_metrics,
)
from firelens.evaluation.snapshot import (
    _current_benchmark_identities as _current_benchmark_identities_impl,
)
from firelens.evaluation.snapshot import (
    _validate_before_snapshot_contract as _validate_before_snapshot_contract_impl,
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


def _current_benchmark_identities(
    spec: BenchmarkSpec, spec_path: Path
) -> tuple[str, dict[str, str], dict[str, str]]:
    return _current_benchmark_identities_impl(spec, spec_path, repository_root=ROOT)


def _validate_before_snapshot_contract(
    before: dict[str, Any], spec: BenchmarkSpec, spec_path: Path
) -> dict[str, float | bool | None]:
    return _validate_before_snapshot_contract_impl(
        before, spec, spec_path, repository_root=ROOT
    )


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
