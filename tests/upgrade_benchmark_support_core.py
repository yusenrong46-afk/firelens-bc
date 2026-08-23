from __future__ import annotations

# ruff: noqa: F401
import gzip
import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import scripts.upgrade_benchmark as upgrade_benchmark
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from scripts.upgrade_benchmark import (
    _assert_recomputed_summary_matches,
    _build_before_snapshot_seal,
    _capture_frontend_surface,
    _deployment,
    _development_retrieval,
    _frontend_bundle,
    _frontend_manual_review_protocol,
    _frontend_surface,
    _hard_probe,
    _live,
    _preview,
    _relevant_untracked_paths,
    _retrieval_qualification,
    _review,
    _semantic_holdout,
    _ux,
    _verify_before_snapshot_seal_payload,
    capture,
    compare_snapshots,
    load_dataset_role_registry,
    load_spec,
    validate_frontend_manual_review,
    validate_semantic_holdout,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data/evaluation/upgrade_benchmark_v1_5_2.yaml"
V3_PROTOCOL_PATH = ROOT / "data/evaluation/benchmark_v1_5_2_sealed_retrieval_v3.protocol.yaml"


def _snapshot_sections(
    metrics: dict[str, object],
    ux_sampling: dict[str, object],
    runtime_artifact: dict[str, object] | None = None,
) -> dict[str, object]:
    semantic_status = (
        "complete"
        if metrics["semantic_review_unsupported_or_unclear"] is not None
        else "not_run"
    )
    return {
        "verification": {"passed": metrics["verification_passed"]},
        "hard_probe_offline": {
            "pass_rate": metrics["offline_hard_probe_pass_rate"],
            "critical_failures": metrics["offline_hard_probe_critical_failures"],
            "p95_latency_ms": metrics["offline_hard_probe_p95_ms"],
        },
        "hard_probe_qualified": {
            "pass_rate": metrics["qualified_hard_probe_pass_rate"],
            "cost_usd": metrics["qualified_hard_probe_cost_usd"],
        },
        "live": {
            "qualified": metrics["live_qualified"],
            "cached_p95_ms": metrics["live_cached_p95_ms"],
        },
        "frontend_bundle": {
            "initial_js_gzip_bytes": metrics["frontend_initial_route_js_gzip_bytes"],
            "lazy_js_gzip_bytes": metrics["frontend_lazy_js_gzip_bytes"],
            "initial_css_gzip_bytes": metrics["frontend_initial_css_gzip_bytes"],
            "lazy_css_gzip_bytes": metrics["frontend_lazy_css_gzip_bytes"],
            "server_js_gzip_bytes": metrics["frontend_server_js_gzip_bytes"],
            "font_bytes": metrics["frontend_font_bytes"],
            "image_bytes": metrics["frontend_image_bytes"],
            "deployment_metadata_bytes": metrics["frontend_deployment_metadata_bytes"],
            "other_bytes": metrics["frontend_other_bytes"],
            "total_emitted_bytes": metrics["frontend_total_emitted_bytes"],
            "unclassified_bytes": metrics["frontend_unclassified_output_bytes"],
        },
        "frontend_surface": {
            "qualified": metrics["frontend_surface_qualified"],
            "visual_matrix_pass_rate": metrics["frontend_visual_matrix_pass_rate"],
            "css_layout_violation_count": metrics["frontend_css_layout_violation_count"],
            "axe_wcag_a_aa_finding_count": metrics["frontend_axe_wcag_a_aa_finding_count"],
            "runtime_violation_count": metrics["frontend_runtime_violation_count"],
            "keyboard_journey_passed": metrics["frontend_keyboard_journey_passed"],
            "map_list_parity": metrics["frontend_map_list_parity"],
            "map_detail_integrity": metrics["frontend_map_detail_integrity"],
            "map_marker_placement_sanity": metrics["frontend_map_marker_placement_sanity"],
            "direct_third_party_tile_request_count": metrics[
                "frontend_direct_third_party_tile_request_count"
            ],
            "worst_profile_p75": {
                "lcp_ms": metrics["frontend_worst_p75_lcp_ms"],
                "cls": metrics["frontend_worst_p75_cls"],
                "inp_interaction_proxy_ms": metrics["frontend_worst_p75_inp_proxy_ms"],
                "map_ready_after_interaction_ms": metrics["frontend_worst_p75_map_ready_ms"],
            },
        },
        "frontend_manual_review": {
            "accessibility_qualified": metrics["frontend_manual_accessibility_qualified"],
            "product_safety_qualified": metrics["frontend_manual_product_safety_qualified"],
            "open_finding_count": metrics["frontend_manual_open_findings"],
        },
        "development_retrieval": {
            "recall_at_5": metrics["development_retrieval_recall_at_5"],
            "mrr_at_5": metrics["development_retrieval_mrr_at_5"],
            "ndcg_at_5": metrics["development_retrieval_ndcg_at_5"],
            "mean_source_coverage": metrics["development_retrieval_mean_source_coverage"],
            "reported_cost_usd": metrics["development_retrieval_cost_usd"],
        },
        "semantic_review": {
            "status": semantic_status,
            "qualified": metrics["semantic_review_qualified"],
            "approval_rate": metrics["semantic_review_approval_rate"],
            "unsupported_verified_claim_count": metrics[
                "semantic_review_unsupported_or_unclear"
            ],
            "unclear_claim_count": 0,
        },
        "semantic_holdout": {
            "qualified": metrics["semantic_holdout_qualified"],
            "unsupported_or_unclear": metrics["semantic_holdout_unsupported_or_unclear"],
            "dangerous_omission_count": metrics["semantic_holdout_dangerous_omissions"],
        },
        "retrieval_review": {
            "qualified": metrics["retrieval_review_qualified"],
            "approval_rate": metrics["retrieval_review_approval_rate"],
        },
        "retrieval_qualification": {
            "qualified": metrics["sealed_retrieval_qualified"],
            "repetitions": metrics["sealed_retrieval_repetitions"],
            "min_recall_at_5": metrics["sealed_retrieval_min_recall_at_5"],
        },
        "ux": {
            **ux_sampling,
            "participant_count": metrics["ux_participant_count"],
            "task_completion_rate": metrics["ux_task_completion_rate"],
            "min_task_completion_rate": metrics["ux_min_task_completion_rate"],
            "critical_error_count": metrics["ux_critical_error_count"],
            "near_me_median_seconds": metrics["ux_near_me_median_seconds"],
            "median_seq_score": metrics["ux_median_seq_score"],
            "evidence_comprehension_rate": metrics["ux_evidence_comprehension_rate"],
            "freshness_comprehension_rate": metrics["ux_freshness_comprehension_rate"],
            "official_source_open_rate": metrics["ux_official_source_open_rate"],
            "accessibility_coverage": metrics["ux_access_method_sampling_coverage"],
        },
        "preview": {"qualified": metrics["preview_qualified"]},
        "deployment": {
            "distributed_rate_limit_verified": metrics["distributed_rate_limit_verified"],
            "rollback_rehearsal_passed": metrics["rollback_rehearsal_passed"],
        },
        "runtime_artifact": runtime_artifact or {"status": "required_after_only"},
    }


def _set_snapshot_metric(snapshot: dict, key: str, value: object) -> None:
    sampling_keys = {
        "status",
        "cohort_counts",
        "cohort_shares",
        "device_class_counts",
        "device_class_shares",
        "access_method_counts",
        "access_method_shares",
    }
    ux_sampling = {
        sampling_key: snapshot["ux"][sampling_key]
        for sampling_key in sampling_keys
        if sampling_key in snapshot["ux"]
    }
    snapshot["metrics"][key] = value
    snapshot.update(
        _snapshot_sections(snapshot["metrics"], ux_sampling, snapshot.get("runtime_artifact"))
    )


def _runtime_artifact_snapshot_fixture(identity: dict[str, object]) -> dict[str, object]:
    contract_path = ROOT / "config/runtime_artifact_allowlist.v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    candidate = {
        "schema_version": "firelens.runtime_candidate.v3",
        "candidate_id": identity["candidate_id"],
        "release_version": identity["release_version"],
        "build_commit": identity["commit"],
        "corpus_version": identity["corpus_version"],
        "embedding_model": identity["configuration"]["embedding_model"],
        "retrieval_text_strategy": identity["configuration"]["retrieval_text_strategy"],
        "rerank_model": identity["configuration"]["rerank_model"],
        "generation_model": identity["configuration"]["generation_model"],
        "data_collection": identity["configuration"]["data_collection"],
        "allow_fallbacks": identity["configuration"]["allow_fallbacks"],
        "require_parameters": identity["configuration"]["require_parameters"],
        "embedding_zdr": identity["configuration"]["embedding_zdr"],
        "reranking_zdr": identity["configuration"]["reranking_zdr"],
        "generation_zdr": identity["configuration"]["generation_zdr"],
    }
    candidate_raw = json.dumps(candidate, sort_keys=True)
    candidate_sha256 = hashlib.sha256(candidate_raw.encode()).hexdigest()
    logical_paths = set(contract["required_files"])
    conditional = contract["conditional_files"][0]
    if candidate["retrieval_text_strategy"] == conditional["required_value"]:
        logical_paths.add(conditional["logical_path"])

    def inventory(platform: str, platform_root: str) -> dict[str, object]:
        rows = []
        for logical_path in sorted(logical_paths):
            if logical_path == "config/runtime_artifact_allowlist.v1.json":
                size_bytes = contract_path.stat().st_size
                sha256 = contract_sha256
            elif logical_path == "config/runtime_candidate.v1.json":
                size_bytes = len(candidate_raw.encode())
                sha256 = candidate_sha256
            else:
                size_bytes = len(logical_path)
                sha256 = hashlib.sha256(logical_path.encode()).hexdigest()
            rows.append(
                {
                    "logical_path": logical_path,
                    "platform_path": f"{platform_root}/{logical_path}",
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                }
            )
        report: dict[str, object] = {
            "schema_version": "firelens.runtime_artifact_inventory.v3",
            "assurance": {
                "scope": "staged_logical_bundle",
                "platform_export_provenance_verified": False,
                "runtime_candidate_identity_observed": False,
            },
            "contract": {
                "schema_version": "firelens.runtime_artifact_allowlist.v1",
                "contract_id": contract["contract_id"],
                "logical_path": "config/runtime_artifact_allowlist.v1.json",
                "sha256": contract_sha256,
            },
            "identity": {
                "platform": platform,
                "platform_root": platform_root,
                "artifact_id": f"{platform}-artifact-test",
                "candidate_id": candidate["candidate_id"],
                "release_version": candidate["release_version"],
                "build_commit": candidate["build_commit"],
            },
            "runtime_configuration": {
                "logical_path": "config/runtime_candidate.v1.json",
                "sha256": candidate_sha256,
                "corpus_version": candidate["corpus_version"],
                "embedding_model": candidate["embedding_model"],
                "retrieval_text_strategy": candidate["retrieval_text_strategy"],
                "rerank_model": candidate["rerank_model"],
                "generation_model": candidate["generation_model"],
                "data_collection": candidate["data_collection"],
                "allow_fallbacks": candidate["allow_fallbacks"],
                "require_parameters": candidate["require_parameters"],
                "embedding_zdr": candidate["embedding_zdr"],
                "reranking_zdr": candidate["reranking_zdr"],
                "generation_zdr": candidate["generation_zdr"],
            },
            "file_count": len(rows),
            "total_size_bytes": sum(row["size_bytes"] for row in rows),
            "files": rows,
        }
        report["inventory_sha256"] = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return report

    inventories = {
        "vercel": inventory("vercel", "/var/task"),
        "docker": inventory("docker", "/app"),
    }
    comparison = upgrade_benchmark.compare_runtime_inventories(
        inventories["vercel"], inventories["docker"]
    )
    hashes = {platform: report["inventory_sha256"] for platform, report in inventories.items()}
    candidate_evidence = {
        "logical_path": "config/runtime_candidate.v1.json",
        "raw_json": candidate_raw,
        "sha256": candidate_sha256,
        "size_bytes": len(candidate_raw.encode()),
    }
    return {
        "status": "complete",
        "capture_method": "capture_owned_build_runtime_inventory.v1",
        "contract": {
            "path": "config/runtime_artifact_allowlist.v1.json",
            "sha256": contract_sha256,
        },
        "inventories": inventories,
        "candidate_configurations": {
            "vercel": candidate_evidence,
            "docker": dict(candidate_evidence),
        },
        "comparison": comparison,
        "capture_sequence": {
            "pre_command_inventory_sha256": hashes,
            "post_command_inventory_sha256": hashes,
            "unchanged": True,
        },
    }


def _rehash_runtime_artifact_section(section: dict[str, object]) -> None:
    inventories = section["inventories"]
    for inventory in inventories.values():
        inventory["files"] = sorted(inventory["files"], key=lambda row: row["logical_path"])
        inventory["file_count"] = len(inventory["files"])
        inventory["total_size_bytes"] = sum(row["size_bytes"] for row in inventory["files"])
        unsigned = dict(inventory)
        unsigned.pop("inventory_sha256", None)
        inventory["inventory_sha256"] = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    section["comparison"] = upgrade_benchmark.compare_runtime_inventories(
        inventories["vercel"], inventories["docker"]
    )
    hashes = {
        platform: inventory["inventory_sha256"] for platform, inventory in inventories.items()
    }
    section["capture_sequence"] = {
        "pre_command_inventory_sha256": hashes,
        "post_command_inventory_sha256": hashes,
        "unchanged": True,
    }


def _sync_runtime_artifact_commitments(snapshot: dict[str, object]) -> None:
    section = snapshot["runtime_artifact"]
    artifacts = snapshot["artifacts"]
    artifacts["runtime_artifact_vercel_inventory"]["sha256"] = (
        upgrade_benchmark._rendered_json_sha256(section["inventories"]["vercel"])
    )
    artifacts["runtime_artifact_docker_inventory"]["sha256"] = (
        upgrade_benchmark._rendered_json_sha256(section["inventories"]["docker"])
    )
    artifacts["runtime_artifact_comparison"]["sha256"] = (
        upgrade_benchmark._rendered_json_sha256(section["comparison"])
    )
    artifacts["runtime_artifact_vercel_candidate"]["sha256"] = section[
        "candidate_configurations"
    ]["vercel"]["sha256"]
    artifacts["runtime_artifact_docker_candidate"]["sha256"] = section[
        "candidate_configurations"
    ]["docker"]["sha256"]


def _passing_snapshots() -> tuple[dict, dict]:
    spec = load_spec(SPEC_PATH)
    before_metrics: dict[str, object] = {}
    after_metrics: dict[str, object] = {}

    for metric in spec.comparison_metrics:
        if metric.value_type == "boolean":
            value: object = metric.gate_value if type(metric.gate_value) is bool else True
        elif metric.value_type == "integer":
            value = metric.gate_value if metric.gate_value is not None else 1
        else:
            value = float(metric.gate_value) if metric.gate_value is not None else 1.0

        before_metrics[metric.key] = None if metric.comparison_mode == "after_only" else value
        after_metrics[metric.key] = value

    # This metric has a ratified 25% minimum improvement requirement, so equal
    # synthetic values would intentionally fail the otherwise-passing fixture.
    before_metrics["ux_near_me_median_seconds"] = 60.0
    after_metrics["ux_near_me_median_seconds"] = 40.0

    contract_sha256 = hashlib.sha256(
        (ROOT / "config/runtime_artifact_allowlist.v1.json").read_bytes()
    ).hexdigest()
    identity = {
        "spec_sha256": "a" * 64,
        "identity_input_sha256": {
            "dataset.yaml": "b" * 64,
            "config/runtime_artifact_allowlist.v1.json": contract_sha256,
        },
        "harness_input_sha256": {"harness.py": "c" * 64},
        "release_version": "1.5.2-test.1",
        "corpus_version": "corpus.test.v1",
        "configuration": {
            "embedding_model": "provider/embedding-test",
            "retrieval_text_strategy": "metadata_context_v1",
            "rerank_model": "provider/rerank-test",
            "generation_model": "provider/generation-test",
            **APPROVED_PRODUCTION_PRIVACY.candidate_fields(),
        },
        "execution_environment": {
            "os": "Darwin",
            "os_release": "25.0.0",
            "architecture": "arm64",
            "cpu_model": "Apple M4",
            "logical_cpu_count": 10,
            "python_implementation": "CPython",
            "python_version": "3.13.5",
            "node_version": "v22.17.0",
            "npm_version": "10.9.2",
            "playwright_version": "1.62.0",
            "chromium_version": "Google Chrome for Testing 151.0.7922.34",
        },
    }
    ux_sampling = {
        "status": "complete",
        "participant_count": 12,
        "cohort_counts": {"novice_bc_resident": 6, "wildfire_aware": 6},
        "cohort_shares": {"novice_bc_resident": 0.5, "wildfire_aware": 0.5},
        "device_class_counts": {"desktop": 6, "mobile": 6},
        "device_class_shares": {"desktop": 0.5, "mobile": 0.5},
        "access_method_counts": {"keyboard": 1, "pointer": 10, "screen_reader": 1},
        "access_method_shares": {
            "keyboard": 1 / 12,
            "pointer": 10 / 12,
            "screen_reader": 1 / 12,
        },
    }
    before_commit = "a" * 40
    after_commit = "b" * 40
    before_identity = {
        **identity,
        "commit": before_commit,
        "candidate_id": f"firelens-v1-5-2:{before_commit}",
    }
    after_identity = {
        **identity,
        "commit": after_commit,
        "candidate_id": f"firelens-v1-5-2:{after_commit}",
    }
    before = {
        "schema_version": "firelens_upgrade_benchmark_snapshot.v2",
        "benchmark_id": spec.benchmark_id,
        "label": "before",
        "identity": before_identity,
        "metrics": before_metrics,
        **_snapshot_sections(before_metrics, ux_sampling),
    }
    after = {
        "schema_version": "firelens_upgrade_benchmark_snapshot.v2",
        "benchmark_id": spec.benchmark_id,
        "label": "after",
        "identity": after_identity,
        "metrics": after_metrics,
        **_snapshot_sections(
            after_metrics,
            ux_sampling,
            _runtime_artifact_snapshot_fixture(after_identity),
        ),
    }
    runtime_section = after["runtime_artifact"]
    after["artifacts"] = {
        "runtime_artifact_vercel_inventory": {
            "path": "output/vercel_inventory.json",
            "sha256": upgrade_benchmark._rendered_json_sha256(
                runtime_section["inventories"]["vercel"]
            ),
        },
        "runtime_artifact_docker_inventory": {
            "path": "output/docker_inventory.json",
            "sha256": upgrade_benchmark._rendered_json_sha256(
                runtime_section["inventories"]["docker"]
            ),
        },
        "runtime_artifact_comparison": {
            "path": "output/comparison.json",
            "sha256": upgrade_benchmark._rendered_json_sha256(runtime_section["comparison"]),
        },
        "runtime_artifact_vercel_candidate": {
            "path": "output/vercel_runtime_candidate.v1.json",
            "sha256": runtime_section["candidate_configurations"]["vercel"]["sha256"],
        },
        "runtime_artifact_docker_candidate": {
            "path": "output/docker_runtime_candidate.v1.json",
            "sha256": runtime_section["candidate_configurations"]["docker"]["sha256"],
        },
    }
    return before, after


def _seal_test_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, Path, dict, Path]:
    spec = load_spec(SPEC_PATH)
    before, _ = _passing_snapshots()
    monkeypatch.setattr(upgrade_benchmark, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    dataset_path = tmp_path / "data/dataset.yaml"
    harness_path = tmp_path / "harness.py"
    spec_path = tmp_path / "data/spec.yaml"
    dataset_path.write_text("dataset: frozen\n", encoding="utf-8")
    harness_path.write_text("# frozen harness\n", encoding="utf-8")
    spec_path.write_text("spec: frozen\n", encoding="utf-8")
    spec = spec.model_copy(
        update={
            "frozen_before_upgrade": True,
            "identity_inputs": ["data/dataset.yaml"],
            "harness_inputs": ["harness.py"],
            "before_snapshot_seal": "data/before-seal.json",
        }
    )
    before["capture_complete"] = True
    before["missing_required_metrics"] = []
    before["identity"].update(
        {
            "commit": "baseline-commit",
            "branch": "main",
            "candidate_id": "firelens-v1-5-2:baseline-commit",
            "release_version": "v1.5",
            "spec_sha256": upgrade_benchmark.file_sha256(spec_path),
            "identity_input_sha256": {
                "data/dataset.yaml": upgrade_benchmark.file_sha256(dataset_path)
            },
            "harness_input_sha256": {"harness.py": upgrade_benchmark.file_sha256(harness_path)},
            "corpus_sha256": "1" * 64,
            "vector_matrix_sha256": "2" * 64,
            "vector_manifest_sha256": "3" * 64,
            "document_context_sha256": None,
            "repairs_sha256": "4" * 64,
            "configuration_sha256": "5" * 64,
        }
    )
    before_path = tmp_path / "output/before.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    return spec, spec_path, before, before_path


def _repo_git(repo: Path, *args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    )
    return completed.stdout.strip()


def _init_ancestry_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[object, str]:
    spec = load_spec(SPEC_PATH).model_copy(
        update={"before_snapshot_seal": "data/before-seal.json"}
    )
    _repo_git(tmp_path, "init", "--quiet")
    _repo_git(tmp_path, "config", "user.name", "Benchmark Test")
    _repo_git(tmp_path, "config", "user.email", "benchmark@example.test")
    (tmp_path / "seed.txt").write_text("baseline\n", encoding="utf-8")
    _repo_git(tmp_path, "add", "seed.txt")
    _repo_git(tmp_path, "commit", "--quiet", "-m", "baseline")
    before_commit = _repo_git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.setattr(upgrade_benchmark, "ROOT", tmp_path)
    return spec, before_commit


def _commit_test_seal(repo: Path, before_commit: str) -> str:
    seal_path = repo / "data/before-seal.json"
    seal_path.parent.mkdir(parents=True, exist_ok=True)
    seal_path.write_text(
        json.dumps({"candidate_identity": {"commit": before_commit}}),
        encoding="utf-8",
    )
    _repo_git(repo, "add", "data/before-seal.json")
    _repo_git(repo, "commit", "--quiet", "-m", "seal baseline")
    return _repo_git(repo, "rev-parse", "HEAD")


def _commit_after_candidate(repo: Path, name: str = "after.txt") -> str:
    (repo / name).write_text("candidate\n", encoding="utf-8")
    _repo_git(repo, "add", name)
    _repo_git(repo, "commit", "--quiet", "-m", f"add {name}")
    return _repo_git(repo, "rev-parse", "HEAD")


__all__ = [name for name in globals() if not name.startswith("__")]
