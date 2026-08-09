"""Capture immutable before/after benchmark snapshots.

The capture workflow is intentionally dependency-injected.  The historical
``scripts.upgrade_benchmark`` facade passes its own helpers so characterization
tests can continue to replace Git and process boundaries without coupling this
production module to the executable script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.benchmark import benchmark_runtime_configuration
from firelens.config import FireLensConfig
from firelens.evaluation.common import (
    assert_recomputed_summary_matches as _assert_recomputed_summary_matches,
)
from firelens.evaluation.common import file_sha256
from firelens.evaluation.qualification_reports import _hard_probe, _live, _review
from firelens.evaluation.release_surfaces import (
    _deployment,
    _preview,
    _write_deployment_template,
    _write_ux_template,
)
from firelens.evaluation.retrieval import _development_retrieval, _retrieval_qualification
from firelens.evaluation.runtime_artifact import (
    _artifact,
    _build_runtime_artifact_pair,
    _finalize_runtime_artifact_pair,
    _runtime_candidate_id,
    _write_runtime_artifact_evidence,
)
from firelens.evaluation.semantic_holdout import _semantic_holdout, validate_semantic_holdout
from firelens.evaluation.snapshot import _check_report_identity, _metrics
from firelens.evaluation.spec_models import BenchmarkSpec
from firelens.evaluation.ux import _ux
from firelens.owner_review import validate_owner_review
from firelens.retrieval_review import validate_retrieval_owner_review
from firelens.review_workspace.qualification import verify_review_qualification_package
from firelens.storage import atomic_text_writer


@dataclass(frozen=True)
class CaptureDependencies:
    """Repository and process boundaries required by :func:`capture_benchmark`."""

    root: Path
    semantic_development_registry: Path
    semantic_holdout_manifest: Path
    load_spec: Callable[[Path], BenchmarkSpec]
    tracked_dirty: Callable[[], bool]
    relevant_untracked_paths: Callable[[], list[str]]
    verify_tracked_before_snapshot_seal: Callable[..., dict[str, Any]]
    current_git_commit: Callable[..., str]
    resolve_before_snapshot_ancestry: Callable[..., dict[str, Any]]
    run_logged: Callable[[list[str], Path], dict[str, Any]]
    read_report: Callable[[Path | None], dict[str, Any] | None]
    execution_environment: Callable[[], dict[str, str | int]]
    capture_frontend_surface: Callable[..., dict[str, Any]]
    git: Callable[..., str]
    validate_frontend_manual_review: Callable[..., dict[str, Any]]


def capture_benchmark(args: argparse.Namespace, dependencies: CaptureDependencies) -> int:
    spec_path = args.spec.resolve()
    spec = dependencies.load_spec(spec_path)
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
    if dependencies.tracked_dirty():
        raise ValueError("benchmark capture requires a clean tracked worktree")
    relevant_untracked = dependencies.relevant_untracked_paths()
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
        verified_before = dependencies.verify_tracked_before_snapshot_seal(
            spec=spec,
            spec_path=spec_path,
            before_path=before_snapshot.resolve(),
        )
        after_preflight_commit = dependencies.current_git_commit(
            context="after capture candidate"
        )
        before_snapshot_ancestry = dependencies.resolve_before_snapshot_ancestry(
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
        if not isinstance(semantic_holdout_report_path, Path) or not isinstance(
            semantic_holdout_review_bundle_path, Path
        ):
            raise TypeError("semantic holdout report and review bundle must be paths")
        semantic_holdout_prevalidated = validate_semantic_holdout(
            semantic_holdout_report_path,
            semantic_holdout_review_bundle_path,
            dependencies.semantic_holdout_manifest,
            dependencies.semantic_development_registry,
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
        frontend_manual_prevalidated = dependencies.validate_frontend_manual_review(
            frontend_manual_review_bundle_path,
            expected_commit=after_preflight_commit,
        )
    output_dir = args.output_dir.resolve()
    runtime_artifact_prevalidated: dict[str, Any] | None = None
    config = FireLensConfig.from_env(dependencies.root)
    corpus_manifest = dependencies.read_report(config.corpus_manifest_path)
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

    verification = dependencies.run_logged(["make", "verify"], output_dir / "verification.log")
    commit = dependencies.git("rev-parse", "HEAD")
    if after_preflight_commit is not None and commit != after_preflight_commit:
        raise ValueError(
            "after candidate commit changed during benchmark capture; rerun from a stable checkout"
        )
    if args.label == "after":
        frontend_manual_review = dependencies.validate_frontend_manual_review(
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
    execution_environment = dependencies.execution_environment()
    frontend_capture = dependencies.capture_frontend_surface(
        output_dir=output_dir,
        expected_commit=commit,
        expected_environment=execution_environment,
    )
    frontend_bundle = frontend_capture["bundle"]
    frontend_surface = frontend_capture["surface"]
    hard_path = output_dir / "hard_probe_offline.json"
    hard_path.unlink(missing_ok=True)
    hard_run = dependencies.run_logged(
        [
            str(dependencies.root / ".venv/bin/python"),
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
        live_run = dependencies.run_logged(
            [
                str(dependencies.root / ".venv/bin/python"),
                "scripts/run_live_qualification.py",
                "--output",
                str(live_path),
            ],
            output_dir / "live_qualification.log",
        )

    hard = _hard_probe(dependencies.read_report(hard_path), expected_mode="offline")
    live = _live(
        None
        if args.skip_live
        else dependencies.read_report(live_path)
        if live_path.is_file()
        else None
    )
    _check_report_identity("offline hard probe", hard.get("commit"), commit)
    _check_report_identity(
        "live qualification", live.get("commit"), commit, required=not args.skip_live
    )

    qualified_hard = _hard_probe(
        dependencies.read_report(args.qualified_hard_probe), expected_mode="qualified"
    )
    development_retrieval = _development_retrieval(
        dependencies.read_report(args.development_retrieval_report)
    )
    retrieval = _retrieval_qualification(dependencies.read_report(args.retrieval_qualification))
    submitted_semantic_summary = dependencies.read_report(args.semantic_review_summary)
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
        if not isinstance(semantic_holdout_report_path, Path) or not isinstance(
            semantic_holdout_review_bundle_path, Path
        ):
            raise TypeError("semantic holdout report and review bundle must be paths")
        semantic_holdout = validate_semantic_holdout(
            semantic_holdout_report_path,
            semantic_holdout_review_bundle_path,
            dependencies.semantic_holdout_manifest,
            dependencies.semantic_development_registry,
            semantic_holdout_summary_path,
        )
    else:
        semantic_holdout = _semantic_holdout(None)
    submitted_retrieval_review = dependencies.read_report(args.retrieval_review_summary)
    if submitted_retrieval_review is not None:
        recomputed_retrieval_review = validate_retrieval_owner_review(
            dependencies.root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
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
            source_path=dependencies.root
            / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
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
    preview = _preview(dependencies.read_report(args.preview_report))
    ux = _ux(dependencies.read_report(args.ux_report), spec)
    deployment = _deployment(
        dependencies.read_report(args.deployment_report),
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
    expected_dataset_sha256 = file_sha256(
        dependencies.root / "data/evaluation/hard_probe.v1.yaml"
    )
    expected_corpus_sha256 = file_sha256(config.corpus_path)
    expected_vector_sha256 = file_sha256(config.vector_matrix_path)
    expected_document_context_sha256 = (
        file_sha256(config.document_context_path)
        if config.document_context_path.is_file()
        else None
    )
    expected_repairs_sha256 = file_sha256(
        dependencies.root / "data/repairs/text_overrides.yaml"
    )

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
            dependencies.root / "data/evaluation/benchmark_v1.yaml"
        ):
            raise ValueError("development retrieval report uses the wrong dataset")
        if development_retrieval.get("relevance_addendum_sha256") != file_sha256(
            dependencies.root / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml"
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
            dependencies.root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
        ):
            raise ValueError("sealed retrieval report uses the wrong dataset")
        if retrieval.get("dataset_manifest_sha256") != file_sha256(
            dependencies.root / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
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
            dependencies.root / "data/evaluation/benchmark_v1_1_conversation.yaml"
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
            dependencies.root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
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
        final_frontend_manual_review = dependencies.validate_frontend_manual_review(
            frontend_manual_review_bundle_path,
            expected_commit=commit,
        )
        if final_frontend_manual_review != frontend_manual_review:
            raise ValueError("frontend manual review evidence changed during benchmark capture")
        frontend_manual_review = final_frontend_manual_review

    if dependencies.tracked_dirty() or dependencies.relevant_untracked_paths():
        raise ValueError(
            "benchmark commands changed the tracked or relevant untracked worktree"
        )
    if args.label == "after":
        if verified_before is None or before_snapshot_ancestry is None:
            raise ValueError("after capture lost its verified before-seal ancestry state")
        final_ancestry = dependencies.resolve_before_snapshot_ancestry(
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
        relative: file_sha256(dependencies.root / relative) for relative in spec.identity_inputs
    }
    harness_hashes = {
        relative: file_sha256(dependencies.root / relative) for relative in spec.harness_inputs
    }
    snapshot: dict[str, Any] = {
        "schema_version": "firelens_upgrade_benchmark_snapshot.v2",
        "benchmark_id": spec.benchmark_id,
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": {
            "commit": commit,
            "branch": dependencies.git("branch", "--show-current"),
            "candidate_id": _runtime_candidate_id(spec.benchmark_id, commit),
            "tracked_dirty": dependencies.tracked_dirty(),
            "untracked_paths": dependencies.git(
                "ls-files", "--others", "--exclude-standard"
            ).splitlines(),
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
                dependencies.semantic_holdout_manifest
                if semantic_holdout_report_path is not None
                else None
            ),
            "semantic_development_registry": _artifact(
                dependencies.semantic_development_registry
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
                "snapshot": str(output_path.relative_to(dependencies.root)),
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
