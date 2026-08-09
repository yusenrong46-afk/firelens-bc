"""Build and verify the immutable before-snapshot benchmark seal."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.common import file_sha256, sha256_json
from firelens.evaluation.spec_models import BenchmarkSpec
from firelens.storage import atomic_text_writer

SnapshotMetrics = dict[str, float | bool | None]


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


def build_before_snapshot_seal(
    *,
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
    owner: str,
    sealed_at: str,
    repository_root: Path,
    validate_before_snapshot: Callable[[dict[str, Any], BenchmarkSpec, Path], SnapshotMetrics],
    repository_path: Callable[..., tuple[Path, str]],
    candidate_identity: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Create the canonical content of a before-snapshot seal."""

    metrics = validate_before_snapshot(before, spec, spec_path)
    normalized_owner = owner.strip()
    if not normalized_owner or normalized_owner.casefold() in {"owner", "unknown", "tbd"}:
        raise ValueError("before snapshot seal requires a named owner")
    _parse_attestation_timestamp(sealed_at)
    resolved_before, relative_before = repository_path(before_path, context="before snapshot")
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
        "candidate_identity": candidate_identity(before),
        "spec_identity": {
            "path": spec_path.resolve().relative_to(repository_root).as_posix(),
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
        "paired_metrics_sha256": sha256_json(paired_metrics),
    }


def verify_before_snapshot_seal_payload(
    *,
    seal: dict[str, Any],
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
    repository_root: Path,
    validate_before_snapshot: Callable[[dict[str, Any], BenchmarkSpec, Path], SnapshotMetrics],
    repository_path: Callable[..., tuple[Path, str]],
    candidate_identity: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Recompute and compare every content-bound seal field."""

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
    metrics = validate_before_snapshot(before, spec, spec_path)
    resolved_before, relative_before = repository_path(before_path, context="before snapshot")
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
        "candidate_identity": candidate_identity(before),
        "spec_identity": {
            "path": spec_path.resolve().relative_to(repository_root).as_posix(),
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
        "paired_metrics_sha256": sha256_json(expected_paired_metrics),
    }
    for key, value in expected.items():
        if seal.get(key) != value:
            raise ValueError(f"before snapshot seal has a mismatched {key}")


@dataclass(frozen=True)
class SealDependencies:
    root: Path
    load_spec: Callable[[Path], BenchmarkSpec]
    tracked_dirty: Callable[[], bool]
    relevant_untracked_paths: Callable[[], list[str]]
    spec_seal_path: Callable[[BenchmarkSpec], tuple[Path, str]]
    read_report: Callable[[Path | None], dict[str, Any] | None]
    git: Callable[..., str]
    validate_before_snapshot: Callable[[dict[str, Any], BenchmarkSpec, Path], SnapshotMetrics]
    repository_path: Callable[..., tuple[Path, str]]
    candidate_identity: Callable[[dict[str, Any]], dict[str, Any]]
    path_is_tracked_and_unmodified: Callable[[Path], bool]


def verify_tracked_before_snapshot_seal(
    *,
    spec: BenchmarkSpec,
    spec_path: Path,
    before_path: Path,
    dependencies: SealDependencies,
) -> dict[str, Any]:
    seal_path, _ = dependencies.spec_seal_path(spec)
    if not seal_path.is_file():
        raise ValueError("tracked before snapshot seal is missing")
    if not dependencies.path_is_tracked_and_unmodified(seal_path):
        raise ValueError("before snapshot seal must be tracked and unmodified")
    seal = dependencies.read_report(seal_path)
    before = dependencies.read_report(before_path)
    if seal is None or before is None:
        raise ValueError("before snapshot seal and snapshot must both be readable")
    verify_before_snapshot_seal_payload(
        seal=seal,
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        repository_root=dependencies.root,
        validate_before_snapshot=dependencies.validate_before_snapshot,
        repository_path=dependencies.repository_path,
        candidate_identity=dependencies.candidate_identity,
    )
    return before


def create_before_snapshot_seal(
    args: argparse.Namespace,
    dependencies: SealDependencies,
) -> int:
    """Validate and write a new untracked seal that must be committed uniquely."""

    spec_path = args.spec.resolve()
    spec = dependencies.load_spec(spec_path)
    if not spec.frozen_before_upgrade:
        raise ValueError("benchmark specification is not frozen")
    if dependencies.tracked_dirty() or dependencies.relevant_untracked_paths():
        raise ValueError("before sealing requires a clean, fully tracked benchmark worktree")
    seal_path, relative_seal = dependencies.spec_seal_path(spec)
    if seal_path.exists():
        raise FileExistsError(f"refusing to overwrite before snapshot seal: {relative_seal}")
    before_path = args.before.resolve()
    before = dependencies.read_report(before_path)
    if before is None:
        raise ValueError("before snapshot is required")
    identity = before.get("identity") or {}
    if identity.get("commit") != dependencies.git("rev-parse", "HEAD"):
        raise ValueError("before snapshot commit is not the current baseline commit")
    seal = build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner=args.owner,
        sealed_at=datetime.now(UTC).isoformat(),
        repository_root=dependencies.root,
        validate_before_snapshot=dependencies.validate_before_snapshot,
        repository_path=dependencies.repository_path,
        candidate_identity=dependencies.candidate_identity,
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
