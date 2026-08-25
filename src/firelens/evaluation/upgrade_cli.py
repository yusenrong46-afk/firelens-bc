"""Tested CLI facade for immutable FireLens V1.5-2 benchmark snapshots."""

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
from firelens.evaluation.git_evidence import (
    current_git_commit as _current_git_commit_impl,
)
from firelens.evaluation.git_evidence import exact_git_commit as _exact_git_commit_impl
from firelens.evaluation.git_evidence import git as _git_impl
from firelens.evaluation.git_evidence import (
    git_evidence_command as _git_evidence_command_impl,
)
from firelens.evaluation.git_evidence import (
    path_is_tracked_and_unmodified as _path_is_tracked_and_unmodified_impl,
)
from firelens.evaluation.git_evidence import (
    relevant_untracked_paths as _relevant_untracked_paths_impl,
)
from firelens.evaluation.git_evidence import (
    repo_relative_path as _repo_relative_path_impl,
)
from firelens.evaluation.git_evidence import (
    resolve_before_snapshot_ancestry as _resolve_before_snapshot_ancestry_impl,
)
from firelens.evaluation.git_evidence import spec_seal_path as _spec_seal_path_impl
from firelens.evaluation.git_evidence import tracked_dirty as _tracked_dirty_impl
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
from firelens.evaluation.seal import SealDependencies
from firelens.evaluation.seal import (
    build_before_snapshot_seal as _build_before_snapshot_seal_impl,
)
from firelens.evaluation.seal import (
    create_before_snapshot_seal as _create_before_snapshot_seal_impl,
)
from firelens.evaluation.seal import (
    verify_before_snapshot_seal_payload as _verify_before_snapshot_seal_payload_impl,
)
from firelens.evaluation.seal import (
    verify_tracked_before_snapshot_seal as _verify_tracked_before_snapshot_seal_impl,
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

ROOT = Path(__file__).resolve().parents[3]
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
    return _git_impl(ROOT, *args)


def _tracked_dirty() -> bool:
    return _tracked_dirty_impl(ROOT)


def _relevant_untracked_paths() -> list[str]:
    return _relevant_untracked_paths_impl(git_reader=_git)


def _repo_relative_path(path: Path, *, context: str) -> tuple[Path, str]:
    return _repo_relative_path_impl(path, repository_root=ROOT, context=context)


def _spec_seal_path(spec: BenchmarkSpec) -> tuple[Path, str]:
    return _spec_seal_path_impl(spec, repository_root=ROOT)


def _path_is_tracked_and_unmodified(path: Path) -> bool:
    return _path_is_tracked_and_unmodified_impl(
        path,
        repository_root=ROOT,
        command=_git_evidence_command,
    )


def _git_evidence_command(
    args: list[str],
    *,
    context: str,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    return _git_evidence_command_impl(
        args,
        repository_root=ROOT,
        context=context,
        allowed_returncodes=allowed_returncodes,
    )


def _exact_git_commit(commitish: str, *, context: str) -> str:
    return _exact_git_commit_impl(
        commitish,
        context=context,
        command=_git_evidence_command,
    )


def _current_git_commit(*, context: str) -> str:
    return _current_git_commit_impl(context=context, command=_git_evidence_command)


def _resolve_before_snapshot_ancestry(
    *,
    spec: BenchmarkSpec,
    before: dict[str, Any],
    after_commit: str,
) -> dict[str, Any]:
    return _resolve_before_snapshot_ancestry_impl(
        spec=spec,
        before=before,
        after_commit=after_commit,
        seal_path_resolver=_spec_seal_path,
        command=_git_evidence_command,
        report_reader=_read_report,
    )


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


def _seal_dependencies() -> SealDependencies:
    return SealDependencies(
        root=ROOT,
        load_spec=load_spec,
        tracked_dirty=_tracked_dirty,
        relevant_untracked_paths=_relevant_untracked_paths,
        spec_seal_path=_spec_seal_path,
        read_report=_read_report,
        git=_git,
        validate_before_snapshot=_validate_before_snapshot_contract,
        repository_path=_repo_relative_path,
        candidate_identity=_candidate_identity,
        path_is_tracked_and_unmodified=_path_is_tracked_and_unmodified,
    )


def _build_before_snapshot_seal(
    *,
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
    owner: str,
    sealed_at: str,
) -> dict[str, Any]:
    return _build_before_snapshot_seal_impl(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner=owner,
        sealed_at=sealed_at,
        repository_root=ROOT,
        validate_before_snapshot=_validate_before_snapshot_contract,
        repository_path=_repo_relative_path,
        candidate_identity=_candidate_identity,
    )


def _verify_before_snapshot_seal_payload(
    *,
    seal: dict[str, Any],
    before: dict[str, Any],
    before_path: Path,
    spec: BenchmarkSpec,
    spec_path: Path,
) -> None:
    _verify_before_snapshot_seal_payload_impl(
        seal=seal,
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        repository_root=ROOT,
        validate_before_snapshot=_validate_before_snapshot_contract,
        repository_path=_repo_relative_path,
        candidate_identity=_candidate_identity,
    )


def _verify_tracked_before_snapshot_seal(
    *, spec: BenchmarkSpec, spec_path: Path, before_path: Path
) -> dict[str, Any]:
    return _verify_tracked_before_snapshot_seal_impl(
        spec=spec,
        spec_path=spec_path,
        before_path=before_path,
        dependencies=_seal_dependencies(),
    )


def seal_before(args: argparse.Namespace) -> int:
    return _create_before_snapshot_seal_impl(args, _seal_dependencies())


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
    after_commit = after_identity.get("commit")
    if not isinstance(after_commit, str):
        raise ValueError("after snapshot has no candidate commit")
    ancestry = _resolve_before_snapshot_ancestry(
        spec=spec,
        before=before,
        after_commit=after_commit,
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
        "semantic-review-attestation",
        "semantic-holdout-report",
        "semantic-holdout-review-bundle",
        "semantic-holdout-summary",
        "frontend-manual-review-bundle",
        "retrieval-review-summary",
        "retrieval-review-sidecar",
        "retrieval-review-qualification",
        "retrieval-review-attestation",
        "ux-report",
        "preview-report",
        "preview-raw-evidence",
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
