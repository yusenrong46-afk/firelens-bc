#!/usr/bin/env python3
"""Capture and compare immutable FireLens V1.5-2 benchmark snapshots."""

# Private imports intentionally preserve the historical benchmark-script facade.
# ruff: noqa: F401

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import re
import shutil
import statistics
import subprocess
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
from firelens.evaluation.capture import CaptureDependencies, capture_benchmark
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
from firelens.evaluation.environment import (
    command_version as _command_version_impl,
)
from firelens.evaluation.environment import cpu_model as _cpu_model_impl
from firelens.evaluation.environment import (
    execution_environment as _execution_environment_impl,
)
from firelens.evaluation.environment import p95 as _p95
from firelens.evaluation.environment import read_report as _read_report
from firelens.evaluation.environment import run_logged as _run_logged_impl
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
from firelens.evaluation.specification import (
    load_benchmark_spec as _load_benchmark_spec_impl,
)
from firelens.evaluation.specification import (
    load_dataset_role_registry as _load_dataset_role_registry_impl,
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
    return _load_dataset_role_registry_impl(path, repository_root=ROOT)


def load_spec(path: Path) -> BenchmarkSpec:
    return _load_benchmark_spec_impl(
        path,
        repository_root=ROOT,
        seal_path_resolver=_spec_seal_path,
    )


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


def _run_logged(command: list[str], log_path: Path) -> dict[str, Any]:
    return _run_logged_impl(command, log_path, repository_root=ROOT)


def _command_version(command: list[str]) -> str:
    return _command_version_impl(command, repository_root=ROOT)


def _cpu_model() -> str:
    return _cpu_model_impl(
        _command_version,
        processor_reader=platform.processor,
        uname_processor_reader=lambda: platform.uname().processor,
        system_reader=platform.system,
    )


def _execution_environment() -> dict[str, str | int]:
    return _execution_environment_impl(
        repository_root=ROOT,
        command_version_reader=_command_version,
        cpu_model_reader=_cpu_model,
    )


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
    """Run capture through the package implementation with script test seams."""

    return capture_benchmark(
        args,
        CaptureDependencies(
            root=ROOT,
            semantic_development_registry=SEMANTIC_DEVELOPMENT_REGISTRY,
            semantic_holdout_manifest=SEMANTIC_HOLDOUT_MANIFEST,
            load_spec=load_spec,
            tracked_dirty=_tracked_dirty,
            relevant_untracked_paths=_relevant_untracked_paths,
            verify_tracked_before_snapshot_seal=_verify_tracked_before_snapshot_seal,
            current_git_commit=_current_git_commit,
            resolve_before_snapshot_ancestry=_resolve_before_snapshot_ancestry,
            run_logged=_run_logged,
            read_report=_read_report,
            execution_environment=_execution_environment,
            capture_frontend_surface=_capture_frontend_surface,
            git=_git,
            validate_frontend_manual_review=validate_frontend_manual_review,
        ),
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
