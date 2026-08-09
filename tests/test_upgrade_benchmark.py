from __future__ import annotations

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


def test_v3_authoring_protocol_freezes_required_case_mix() -> None:
    protocol = yaml.safe_load(V3_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert protocol["status"] == "authoring_not_started"
    assert protocol["case_count"] == 47
    assert protocol["composition"] == {
        "single_source": 24,
        "multi_source_or_aspect": 8,
        "negation_or_false_premise": 5,
        "authority_temporal_or_freshness": 5,
        "paraphrase_quantity_or_condition": 5,
    }
    assert sum(protocol["composition"].values()) == protocol["case_count"]
    assert protocol["minimum_safety_sensitive_cases"] == 16
    assert len(protocol["required_source_families"]) == 6
    assert protocol["review"] == {
        "independent_reviewers": 2,
        "adjudicator_required": True,
        "review_must_finish_before_ranking": True,
        "external_hash_anchor_required": True,
    }
    assert protocol["qualification"]["repetitions"] == 3


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
        "schema_version": "firelens.runtime_candidate.v1",
        "candidate_id": identity["candidate_id"],
        "release_version": identity["release_version"],
        "build_commit": identity["commit"],
        "corpus_version": identity["corpus_version"],
        "embedding_model": identity["configuration"]["embedding_model"],
        "retrieval_text_strategy": identity["configuration"]["retrieval_text_strategy"],
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
            "schema_version": "firelens.runtime_artifact_inventory.v1",
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


def _write_manifest_fixture(client: Path, *, include_orphan: bool = False) -> None:
    dist = client.parent
    assets = client / "assets"
    manifest_dir = client / ".vite"
    assets.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    (assets / "app.js").write_text("const app = true;", encoding="utf-8")
    (assets / "shared.js").write_text("export const shared = true;", encoding="utf-8")
    (assets / "map.js").write_text("export const map = true;", encoding="utf-8")
    (assets / "app.css").write_text("body{color:#111}", encoding="utf-8")
    (assets / "map.css").write_text(".map{display:block}", encoding="utf-8")
    (assets / "brand.woff2").write_bytes(b"font-bytes")
    (assets / "logo.png").write_bytes(b"image-bytes")
    (client / "index.html").write_text("<main>FireLens</main>", encoding="utf-8")
    (dist / "server").mkdir(parents=True)
    (dist / "server/index.js").write_text("export default {};", encoding="utf-8")
    (dist / ".openai").mkdir(parents=True)
    (dist / ".openai/hosting.json").write_text("{}", encoding="utf-8")
    if include_orphan:
        (assets / "orphan.js").write_text("export const orphan = true;", encoding="utf-8")
    manifest = {
        "src/main.tsx": {
            "file": "assets/app.js",
            "isEntry": True,
            "imports": ["_shared.js"],
            "dynamicImports": ["src/map.tsx"],
            "css": ["assets/app.css"],
            "assets": ["assets/brand.woff2", "assets/logo.png"],
        },
        "_shared.js": {"file": "assets/shared.js"},
        "src/map.tsx": {
            "file": "assets/map.js",
            "imports": ["_shared.js"],
            "css": ["assets/map.css"],
        },
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_frontend_surface_fixture(
    tmp_path: Path, *, truncate_live_list: bool = False
) -> tuple[Path, dict, dict[str, str | int], dict, Path]:
    protocol_path = ROOT / "data/evaluation/frontend_surface.v1.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client)
    bundle = _frontend_bundle(dist)
    report_path = tmp_path / "report.json"
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    commit = "a" * 40
    browser_version = "151.0.7922.34"
    expected_environment: dict[str, str | int] = {
        "os": "Darwin",
        "os_release": "25.0.0",
        "architecture": "arm64",
        "cpu_model": "Apple M5",
        "logical_cpu_count": 10,
        "python_implementation": "CPython",
        "python_version": "3.14.5",
        "node_version": "v22.17.0",
        "npm_version": "10.9.2",
        "playwright_version": "1.62.0",
        "chromium_version": f"Google Chrome for Testing {browser_version}",
    }

    def execution_profile(viewport: dict) -> dict:
        return {
            "viewport_id": viewport["id"],
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "device_scale_factor": viewport["device_scale_factor"],
            "is_mobile": viewport["is_mobile"],
            "color_scheme": protocol["execution_environment"]["color_scheme"],
            "reduced_motion": protocol["execution_environment"]["reduced_motion"],
            "locale": protocol["execution_environment"]["locale"],
            "timezone_id": protocol["execution_environment"]["timezone_id"],
        }

    def unthrottled_profile(viewport: dict) -> dict:
        return {
            **execution_profile(viewport),
            "cpu_throttling": {"mode": "none", "rate": 1},
            "network": {
                "mode": "local_preview_with_deterministic_routes",
                "cache_policy": "fresh_browser_context_default",
            },
        }

    viewport_by_id = {viewport["id"]: viewport for viewport in protocol["viewports"]}
    desktop = viewport_by_id["desktop"]
    run_profiles = {
        "surface_matrix": [unthrottled_profile(viewport) for viewport in protocol["viewports"]],
        "functional_journeys": [
            {"journey_id": journey["id"], **unthrottled_profile(desktop)}
            for journey in protocol["functional_journeys"]
        ],
        "performance": [
            {
                "profile_id": profile_id,
                **execution_profile(viewport_by_id[profile_id]),
                "cpu_throttling": {
                    "mode": "cdp_emulation",
                    "rate": protocol["performance"]["cpu_throttling_rate"],
                },
                "network": {
                    "mode": "cdp_emulation",
                    **protocol["performance"]["network"],
                    "cache_disabled": protocol["performance"][
                        "cache_disabled_for_cold_samples"
                    ],
                },
            }
            for profile_id in protocol["performance"]["profiles"]
        ],
    }
    report_environment = {
        "os": {
            "name": "darwin",
            "release": expected_environment["os_release"],
            "architecture": expected_environment["architecture"],
            "cpu_model": expected_environment["cpu_model"],
            "logical_cpu_count": expected_environment["logical_cpu_count"],
        },
        "runtime": {
            "node_version": str(expected_environment["node_version"]).removeprefix("v"),
            "npm_version": expected_environment["npm_version"],
            "playwright_package_version": expected_environment["playwright_version"],
        },
        "browser": {
            "name": protocol["execution_environment"]["browser_name"],
            "version": browser_version,
            "headless": protocol["execution_environment"]["headless"],
            "locale": protocol["execution_environment"]["locale"],
            "timezone_id": protocol["execution_environment"]["timezone_id"],
        },
        "run_profiles": run_profiles,
    }

    def expected_map_ids(state_id: str) -> list[str]:
        if state_id == "live":
            return [f"incident:surface-{index:02d}" for index in range(1, 11)]
        if state_id in {"mixed", "stale", "partial_layer"}:
            return ["incident:surface-7"]
        return []

    def expected_map_record(state_id: str, record_id: str) -> dict[str, str]:
        if state_id == "live":
            suffix = record_id.rsplit("-", 1)[1]
            return {
                "name": f"Surface Test Fire {suffix}",
                "source_url": f"https://example.test/incidents/surface-{suffix}",
                "geometry_type": "Point",
            }
        return {
            "name": "Surface Test Fire",
            "source_url": "https://example.test/incidents/surface-7",
            "geometry_type": "Point",
        }

    surface_rows = []
    for state in protocol["states"]:
        for viewport in protocol["viewports"]:
            screenshot_path = screenshots / f"{state['id']}--{viewport['id']}.png"
            Image.new(
                "RGB",
                (
                    viewport["width"] * viewport["device_scale_factor"],
                    viewport["height"] * viewport["device_scale_factor"],
                ),
                (12, 24, 36),
            ).save(screenshot_path, format="PNG")
            applicable = state["id"] in protocol["map_parity"]["applicable_state_ids"]
            map_parity: bool | None = None
            if applicable:
                expected_ids = expected_map_ids(state["id"])
                list_ids = (
                    expected_ids[:8]
                    if truncate_live_list and state["id"] == "live"
                    else expected_ids
                )
                list_records = [
                    {
                        "dom_index": index,
                        "rendered_name": expected_map_record(state["id"], record_id)["name"],
                        "rendered_source_url": expected_map_record(state["id"], record_id)[
                            "source_url"
                        ],
                        "record_id": record_id,
                        "geometry_type": "Point",
                        "resolution": "unique_name_and_source",
                    }
                    for index, record_id in enumerate(list_ids)
                ]
                map_records = [
                    {
                        "dom_index": index,
                        "rendered_popup_name": expected_map_record(state["id"], record_id)[
                            "name"
                        ],
                        "element_tag": "path",
                        "record_id": record_id,
                        "geometry_type": "Point",
                        "canonical_source_url": expected_map_record(state["id"], record_id)[
                            "source_url"
                        ],
                        "source_url_observed_in_popup": False,
                        "observed_visible": True,
                        "observed_center_css_px": {
                            "x": float(100 + index),
                            "y": float(200 + index),
                        },
                        "resolution": "unique_popup_name",
                    }
                    for index, record_id in enumerate(expected_ids)
                ]
                map_parity = list_ids == expected_ids
                map_evidence = {
                    "applicability": "applicable",
                    "reason": None,
                    "collection_status": "complete",
                    "pagination": {
                        "mode": protocol["map_parity"]["pagination_mode"],
                        "response_complete_roster": protocol["map_parity"][
                            "response_complete_roster"
                        ],
                        "rendered_complete_roster_required": True,
                        "map_surface_required": bool(expected_ids),
                        "expected_total_records": len(expected_ids),
                    },
                    "map_surface_present": bool(expected_ids),
                    "expected_response_record_ids": expected_ids,
                    "rendered_accessible_list_record_ids": list_ids,
                    "rendered_map_feature_or_marker_record_ids": expected_ids,
                    "rendered_accessible_list_records": list_records,
                    "rendered_map_feature_or_marker_records": map_records,
                    "unresolved_accessible_list_entries": [],
                    "unresolved_map_feature_or_marker_entries": [],
                    "detail_integrity": True,
                    "marker_placement_sanity": {
                        "scope": ("css_pixel_center_uniqueness_only_not_geospatial_accuracy"),
                        "observed_visible_marker_count": len(expected_ids),
                        "observed_unique_visible_center_count": len(expected_ids),
                        "expected_rendered_marker_count": len(expected_ids),
                        "sanity_passed": True,
                    },
                    "map_list_parity": map_parity,
                }
            else:
                map_evidence = {
                    "applicability": "not_applicable",
                    "reason": "state_not_in_map_parity_roster",
                    "collection_status": "not_applicable",
                    "pagination": None,
                    "map_surface_present": None,
                    "expected_response_record_ids": None,
                    "rendered_accessible_list_record_ids": None,
                    "rendered_map_feature_or_marker_record_ids": None,
                    "rendered_accessible_list_records": None,
                    "rendered_map_feature_or_marker_records": None,
                    "unresolved_accessible_list_entries": None,
                    "unresolved_map_feature_or_marker_entries": None,
                    "detail_integrity": None,
                    "marker_placement_sanity": None,
                    "map_list_parity": None,
                }
            expected_failure = (
                [
                    {
                        "url": "http://127.0.0.1:4175/api/v1/ask",
                        "status": 503,
                        "question": "surface:unavailable",
                    }
                ]
                if state["id"] == "provider_failure"
                else []
            )
            console_errors = (
                [
                    {
                        "text": (
                            "Failed to load resource: the server responded with a status "
                            "of 503 (Service Unavailable)"
                        ),
                        "location": {
                            "url": "http://127.0.0.1:4175/api/v1/ask",
                            "line": 0,
                            "column": 0,
                            "lineNumber": 0,
                            "columnNumber": 0,
                        },
                    }
                ]
                if expected_failure
                else []
            )
            expected_console_errors = (
                [
                    {
                        "event": console_errors[0],
                        "expected_http_failure": expected_failure[0],
                    }
                ]
                if expected_failure
                else []
            )
            request_events = [
                {
                    "sequence_index": 0,
                    "method": "GET",
                    "url": "http://127.0.0.1:4175/",
                    "origin": "http://127.0.0.1:4175",
                    "resource_type": "document",
                    "response_status": 200,
                    "failure": None,
                }
            ]
            if state["question"]:
                request_events.append(
                    {
                        "sequence_index": 1,
                        "method": "POST",
                        "url": "http://127.0.0.1:4175/api/v1/ask",
                        "origin": "http://127.0.0.1:4175",
                        "resource_type": "fetch",
                        "response_status": 503 if expected_failure else 200,
                        "failure": None,
                    }
                )
            request_derived = {
                "request_origins": ["http://127.0.0.1:4175"],
                "unexpected_request_origins": [],
                "failed_requests": [],
                "unallowlisted_failed_requests": [],
                "stylesheet_load_failures": [],
                "direct_third_party_tile_requests": [],
            }
            runtime = {
                "console_errors": console_errors,
                "expected_console_errors": expected_console_errors,
                "unexpected_console_errors": [],
                "expected_http_failures": expected_failure,
                "page_errors": [],
                "request_events": request_events,
                "request_derived": request_derived,
            }
            checks = {
                "axe_engine_version_bound": True,
                "axe_wcag_a_aa_findings_within_limit": True,
                "no_document_horizontal_overflow": True,
                "clipped_text_within_limit": True,
                "stylesheets_accessible": True,
                "stylesheets_loaded": True,
                "interactive_elements_styled": True,
                "interactive_targets_sized": True,
                "text_sizes_within_protocol": True,
                "console_clean": True,
                "page_errors_clean": True,
                "request_origins_allowed": True,
                "no_unallowlisted_failed_requests": True,
                "no_direct_third_party_tile_requests": True,
                "map_list_parity": map_parity if applicable else "not_applicable",
                "map_detail_integrity": True if applicable else "not_applicable",
                "map_marker_placement_sanity": (True if applicable else "not_applicable"),
            }
            surface_rows.append(
                {
                    "state_id": state["id"],
                    "viewport_id": viewport["id"],
                    "viewport": {
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "device_scale_factor": viewport["device_scale_factor"],
                        "is_mobile": viewport["is_mobile"],
                    },
                    "status": "complete",
                    "screenshot": {
                        "path": f"screenshots/{state['id']}--{viewport['id']}.png",
                        "sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
                        "bytes": screenshot_path.stat().st_size,
                        "format": "png",
                        "signature_hex": "89504e470d0a1a0a",
                        "width_px": viewport["width"] * viewport["device_scale_factor"],
                        "height_px": viewport["height"] * viewport["device_scale_factor"],
                    },
                    "axe": {
                        "engine_version": "4.12.1",
                        "installed_package_version": "4.12.1",
                        "engine_version_matches_installed_package": True,
                        "finding_count": 0,
                        "impact_counts": {
                            "critical": 0,
                            "serious": 0,
                            "moderate": 0,
                            "minor": 0,
                            "unknown": 0,
                        },
                        "findings": [],
                    },
                    "layout": {
                        "document_horizontal_overflow_px": 0,
                        "clipped_text_elements": [],
                        "undersized_text_elements": [],
                        "stylesheet_count": 2,
                        "css_rule_count": 10,
                        "inaccessible_stylesheets": [],
                        "undersized_interactive_elements": [],
                        "unstyled_interactive_elements": [],
                        "app_font_family": "Inter",
                    },
                    "map_evidence": map_evidence,
                    "runtime": runtime,
                    "checks": checks,
                    "qualified": all(
                        value is True or value == "not_applicable" for value in checks.values()
                    ),
                }
            )

    privacy_bodies = [
        {"history": [], "question": "surface:grounded"},
        {
            "history": [
                {"content": "surface:grounded", "role": "user"},
                {"content": "Grounded answer", "role": "assistant"},
            ],
            "location": {"latitude": 49.28, "longitude": -123.12, "radius_km": 50},
            "question": "surface:live-fresh",
        },
    ]
    privacy_api_roster = []
    for index, body in enumerate(privacy_bodies):
        body_sha256 = hashlib.sha256(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        privacy_api_roster.append(
            {
                "sequence_index": index,
                "method": "POST",
                "url": "http://127.0.0.1:4175/api/v1/ask",
                "origin": "http://127.0.0.1:4175",
                "resource_type": "fetch",
                "body": body,
                "body_sha256": body_sha256,
                "response_status": 200,
            }
        )
    privacy_network_events = [
        {
            "sequence_index": index,
            "method": "POST",
            "url": "http://127.0.0.1:4175/api/v1/ask",
            "origin": "http://127.0.0.1:4175",
            "resource_type": "fetch",
            "response_status": 200,
            "failure": None,
        }
        for index in range(2)
    ]
    privacy_network_derived = {
        "request_origins": ["http://127.0.0.1:4175"],
        "unexpected_request_origins": [],
        "failed_requests": [],
        "unallowlisted_failed_requests": [],
        "stylesheet_load_failures": [],
        "direct_third_party_tile_requests": [],
    }
    privacy_browser_surfaces = {
        "current_url": "http://127.0.0.1:4175/",
        "current_url_token_matches": [],
        "history": {
            "length": 2,
            "state_type": "null",
            "state_serialized_length": 4,
            "state_token_matches": [],
        },
        "local_storage": [],
        "session_storage": [],
        "cookies": [],
        "indexed_db": {"supported": True, "databases": []},
        "cache_storage": {"supported": True, "caches": []},
        "service_workers": {"supported": True, "registrations": []},
    }
    privacy_derived = {
        "geolocation_not_called_before_opt_in": True,
        "geolocation_called_once_after_opt_in": True,
        "coordinates_rounded_to_two_decimals": True,
        "location_sent_only_with_live_request": True,
        "location_not_persisted_in_browser_storage": True,
        "no_cookie_written": True,
        "canonical_request_roster_valid": True,
        "api_request_issues": [],
        "network_request_derivation_matches": True,
        "unexpected_network_entries": [],
        "body_token_leak_findings": [],
        "browser_token_leak_findings": [],
        "no_unexpected_request_or_body_leakage": True,
        "url_history_clean": True,
        "both_coordinate_tokens_absent_outside_allowed_request": True,
        "browser_storage_surfaces_clean": True,
    }
    privacy_evidence = {
        "fixture_data_only": True,
        "persistence_probe_tokens": protocol["privacy_evidence"]["persistence_probe_tokens"],
        "geolocation_calls": {"before_opt_in": 0, "after_opt_in": 1},
        "api_request_roster": privacy_api_roster,
        "network_request_events": privacy_network_events,
        "network_request_derived": privacy_network_derived,
        "browser_surfaces": privacy_browser_surfaces,
        "derived": privacy_derived,
    }
    functional_journeys = []
    for journey in protocol["functional_journeys"]:
        row = {
            "id": journey["id"],
            "checks": {key: True for key in journey["required_checks"]},
            "errors": [],
            "qualified": True,
        }
        if journey["id"] == "location_privacy_boundary":
            row["evidence"] = privacy_evidence
        functional_journeys.append(row)
    profiles = []
    p75 = {
        "lcp_ms": 1000.0,
        "cls": 0.01,
        "inp_interaction_proxy_ms": 100.0,
        "map_ready_after_interaction_ms": 500.0,
    }
    for profile_id in protocol["performance"]["profiles"]:
        samples = []
        for phase, sample_index in [("warmup", 1)] + [("cold", index) for index in range(1, 8)]:
            samples.append(
                {
                    "phase": phase,
                    "sample_index": sample_index,
                    **p75,
                    "status": "complete",
                    "error": None,
                }
            )
        profiles.append(
            {
                "profile_id": profile_id,
                "viewport": {
                    "width": viewport_by_id[profile_id]["width"],
                    "height": viewport_by_id[profile_id]["height"],
                },
                "throttling": {
                    "cpu_rate": protocol["performance"]["cpu_throttling_rate"],
                    "network": protocol["performance"]["network"],
                    "cache_disabled": protocol["performance"][
                        "cache_disabled_for_cold_samples"
                    ],
                },
                "samples": samples,
                "cold_p75": p75,
                "thresholds": protocol["performance"]["thresholds"][profile_id],
                "checks": {
                    "exact_sample_count": True,
                    "lcp_within_threshold": True,
                    "cls_within_threshold": True,
                    "inp_proxy_within_threshold": True,
                    "map_ready_within_threshold": True,
                },
                "qualified": True,
            }
        )
    qualified_rows = sum(row["qualified"] for row in surface_rows)
    protocol_ratified = protocol["status"] == "ratified" and bool(protocol["frozen_at"])
    summary = {
        "protocol_ratified": protocol_ratified,
        "expected_surface_rows": 30,
        "executed_surface_rows": 30,
        "matrix_complete": True,
        "qualified_surface_rows": qualified_rows,
        "functional_journeys_qualified": True,
        "performance_qualified": True,
        "structure_issues": [],
        "qualified": protocol_ratified and qualified_rows == 30,
    }
    report = {
        "schema_version": "firelens.frontend_surface_report.v1",
        "generated_at": "2026-08-06T12:00:00+00:00",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "protocol_status": protocol["status"],
        "protocol_frozen_at": protocol["frozen_at"],
        "base_url": "http://127.0.0.1:4175",
        "execution_environment": report_environment,
        "browser": {"name": "chromium", "version": browser_version},
        "build": {
            "commit": commit,
            "index_sha256": hashlib.sha256((client / "index.html").read_bytes()).hexdigest(),
            "manifest_sha256": bundle["manifest_sha256"],
        },
        "surface_rows": surface_rows,
        "functional_journeys": functional_journeys,
        "performance": {
            "aggregation": "p75_nearest_rank",
            "profiles": profiles,
            "qualified": True,
        },
        "summary": summary,
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path, report, expected_environment, bundle, client


def _hard_probe_report(*, mode: str = "qualified") -> dict:
    dataset = yaml.safe_load(
        (ROOT / "data/evaluation/hard_probe.v1.yaml").read_text(encoding="utf-8")
    )
    rows = [
        {
            "id": case["id"],
            "priority": case["priority"],
            "passed": True,
            "latency_ms": 10.0,
        }
        for case in dataset["cases"]
    ]
    return {
        "schema_version": "firelens_hard_probe_report.v1",
        "manifest": {
            "mode": mode,
            "provider_boundary": "openrouter" if mode == "qualified" else "offline_double",
            "commit": "a" * 40,
            "dataset_sha256": "b" * 64,
            "corpus_sha256": "c" * 64,
            "vector_matrix_sha256": "d" * 64,
            "document_context_sha256": None,
            "repairs_sha256": "e" * 64,
            "configuration_sha256": "f" * 64,
            "runtime_configuration": {},
            "models": {},
        },
        "summary": {
            "executed": 105,
            "passed": 105,
            "failed": 0,
            "cost_usd": 0.5 if mode == "qualified" else 0.0,
        },
        "results": rows,
    }


def _live_report() -> dict:
    generated_at = "2026-08-06T10:00:00+00:00"
    source_urls = {
        "incident": "https://official.example.test/incident",
        "perimeter": "https://official.example.test/perimeter",
        "evacuation": "https://official.example.test/evacuation",
    }
    cold_records = [
        {
            "result_id": f"{kind}:1",
            "kind": kind,
            "authority": "BC Wildfire Service",
            "source_url": f"https://official.example.test/{kind}",
            "source_updated_at": generated_at,
            "retrieved_at": generated_at,
            "status": "Active",
        }
        for kind in ("incident", "perimeter", "evacuation")
    ]
    chat_records = [{"result_id": "incident:1", "status": "Active"}]
    map_records = [
        {"result_id": "incident:1", "status": "Active"},
        {"result_id": "incident:2", "status": "Being Held"},
    ]
    map_pairs = sorted((row["result_id"], row["status"]) for row in map_records)
    map_digest = hashlib.sha256(
        json.dumps(map_pairs, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cached_requests = [
        {
            "request_id": f"cached-{concurrency}-{request_index:02d}",
            "method": "GET",
            "path": "/api/v1/live/map",
            "layers": ["incidents", "perimeters", "evacuations"],
            "concurrency": concurrency,
            "request_index": request_index,
            "status_code": 200,
            "latency_ms": float(len(previous) + request_index),
            "result_count": 3,
        }
        for concurrency, previous in ((1, []), (5, [None]), (20, [None] * 6))
        for request_index in range(1, concurrency + 1)
    ]
    cached_p95 = upgrade_benchmark._p95([float(row["latency_ms"]) for row in cached_requests])
    assert cached_p95 is not None
    by_concurrency = {}
    for concurrency in (1, 5, 20):
        rows = [row for row in cached_requests if row["concurrency"] == concurrency]
        by_concurrency[str(concurrency)] = {
            "request_count": len(rows),
            "status_codes": [200],
            "p95_latency_ms": upgrade_benchmark._p95(
                [float(row["latency_ms"]) for row in rows]
            ),
        }
    checks = {
        "all_official_layers_available": True,
        "metadata_complete": True,
        "chat_map_records_match": True,
        "all_api_requests_succeeded": True,
        "cached_p95_within_target": True,
        "near_me_contract_valid": True,
    }
    return {
        "report_version": "firelens.live_qualification.v2",
        "evidence_schema_version": "firelens.live_qualification.evidence.v2",
        "generated_at": generated_at,
        "commit": "a" * 40,
        "source_urls": source_urls,
        "qualified": True,
        "checks": checks,
        "cold": {
            "latency_ms": 100.0,
            "result_count": 3,
            "requested_layers": ["incident", "perimeter", "evacuation"],
            "unavailable_layers": [],
            "records": cold_records,
            "metadata_complete": True,
        },
        "cached_api": {
            "p95_target_ms": 4_000.0,
            "p95_latency_ms": cached_p95,
            "request_count": 26,
            "requests": cached_requests,
            "by_concurrency": by_concurrency,
        },
        "chat_map": {
            "chat_request": {
                "method": "POST",
                "path": "/api/v1/ask",
                "question": "Are there active wildfires in BC currently?",
            },
            "map_request": {
                "method": "GET",
                "path": "/api/v1/live/map",
                "layers": ["incidents"],
            },
            "chat_status_code": 200,
            "map_status_code": 200,
            "chat_record_count": 1,
            "map_record_count": 2,
            "chat_records": chat_records,
            "map_records": map_records,
            "matching_ids_and_statuses": True,
            "map_records_sha256": map_digest,
        },
        "near_me": {
            "request": {
                "method": "POST",
                "path": "/api/v1/live/nearby",
                "body": {
                    "location": {
                        "latitude": 49.28,
                        "longitude": -123.12,
                        "radius_km": 50.0,
                    },
                    "layers": ["incident", "perimeter", "evacuation"],
                    "page": 1,
                    "page_size": 200,
                },
            },
            "status_code": 200,
            "requested_radius_km": 50.0,
            "requested_layers": ["incident", "perimeter", "evacuation"],
            "resolved_location": {"latitude": 49.28, "longitude": -123.12},
            "viewport": {
                "west": -123.8,
                "south": 48.8,
                "east": -122.4,
                "north": 49.8,
            },
            "pagination": {
                "page": 1,
                "page_size": 200,
                "total_results": 1,
                "total_pages": 1,
                "returned_results": 1,
                "has_previous": False,
                "has_next": False,
            },
            "result_count": 1,
            "records": chat_records,
            "unavailable_layers": [],
            "layer_statuses": [
                {
                    "kind": kind,
                    "authority": "BC Wildfire Service",
                    "source_url": source_urls[kind],
                    "available": True,
                    "source_updated_at": generated_at,
                    "retrieved_at": generated_at,
                    "freshness": "fresh",
                    "matching_result_count": 1 if kind == "incident" else 0,
                }
                for kind in ("incident", "perimeter", "evacuation")
            ],
            "official_fallback_urls": ["https://official.example.test/map"],
        },
        "elapsed_seconds": 1.0,
    }


def _sealed_report() -> dict:
    dataset = upgrade_benchmark.load_benchmark(
        ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
        require_release_shape=False,
    )
    cases = [
        case for case in dataset.cases if case.split == "holdout" and case.acceptable_evidence
    ]
    config = upgrade_benchmark.FireLensConfig.from_env(ROOT)
    chunks = {
        chunk.chunk_id: chunk
        for chunk in upgrade_benchmark.load_chunk_records(config.corpus_path)
    }
    ranking_by_case: dict[str, list[str]] = {}
    for case in cases:
        matching = next(
            (
                chunk_id
                for chunk_id in chunks
                if upgrade_benchmark._ranking_metrics([chunk_id], case, chunks)["hit"] == 1
            ),
            None,
        )
        assert matching is not None
        ranking_by_case[case.id] = [matching]
    cost_per_case = 0.5 / (3 * len(cases))
    repetition_reports = []
    total_cost = 0.0
    for repetition in range(1, 4):
        rows = []
        for index, case in enumerate(cases):
            ranking = [] if index == 0 else ranking_by_case[case.id]
            metrics = upgrade_benchmark._ranking_metrics(ranking, case, chunks)
            rows.append(
                {
                    "id": case.id,
                    "complete": True,
                    "reranked_chunk_ids": ranking,
                    "metrics": metrics,
                    "reported_cost_usd": cost_per_case,
                }
            )
            total_cost += cost_per_case
        repetition_reports.append(
            {
                "repetition": repetition,
                "complete": True,
                "case_count": len(rows),
                "recall_at_5": sum(float(row["metrics"]["hit"]) for row in rows) / len(rows),
                "mrr_at_5": sum(float(row["metrics"]["reciprocal_rank"]) for row in rows)
                / len(rows),
                "ndcg_at_5": sum(float(row["metrics"]["ndcg"]) for row in rows) / len(rows),
                "mean_source_coverage": sum(
                    float(row["metrics"]["source_coverage"]) for row in rows
                )
                / len(rows),
                "rows": rows,
            }
        )
    return {
        "report_version": "firelens_frozen_retrieval_qualification.v1",
        "evaluation_role": "sealed_release_qualification",
        "baseline_policy": "required_after_only",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "configuration_sha256": "d" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "e" * 64,
        "dataset_sha256": "f" * 64,
        "dataset_manifest_sha256": "0" * 64,
        "split": "holdout",
        "tuning_allowed": False,
        "relevance_addendum_used": False,
        "owner_approved": True,
        "repetitions": 3,
        "case_count_per_repetition": 47,
        "cost_budget_usd": 0.75,
        "cost_budget_exceeded": False,
        "reported_cost_usd": total_cost,
        "repeated_rankings_match": True,
        "qualified": True,
        "repetition_reports": repetition_reports,
    }


def _development_retrieval_report() -> dict:
    dataset_path = ROOT / "data/evaluation/benchmark_v1.yaml"
    dataset = upgrade_benchmark.load_benchmark(dataset_path)
    dataset = upgrade_benchmark.apply_relevance_addendum(
        dataset,
        upgrade_benchmark.load_relevance_addendum(
            ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml",
            dataset_path=dataset_path,
        ),
    )
    cases = [
        case
        for case in dataset.cases
        if case.split == "development" and case.acceptable_evidence
    ]
    config = upgrade_benchmark.FireLensConfig.from_env(ROOT)
    chunks = {
        chunk.chunk_id: chunk
        for chunk in upgrade_benchmark.load_chunk_records(config.corpus_path)
    }
    rows = []
    for case in cases:
        matching = next(
            chunk_id
            for chunk_id in chunks
            if upgrade_benchmark._ranking_metrics([chunk_id], case, chunks)["hit"] == 1
        )
        rankings = {stage: [matching] for stage in ("bm25", "vector", "fused", "reranked")}
        rows.append(
            {
                "id": case.id,
                "retrieval_eligible": True,
                "complete": True,
                "rankings": rankings,
                "stage_metrics": {
                    stage: upgrade_benchmark._ranking_metrics(ranking, case, chunks)
                    for stage, ranking in rankings.items()
                },
                "reported_cost_usd": 0.001,
            }
        )
    summary = upgrade_benchmark._candidate_summary(rows)
    return {
        "report_version": "firelens_retrieval_comparison.v2",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "d" * 64,
        "dataset_sha256": "e" * 64,
        "relevance_addendum_sha256": "f" * 64,
        "split": "development",
        "holdout_opened": False,
        "development_case_roster": [case.id for case in cases],
        "candidates": {"current": {"configuration": {}, **summary}},
        "details": {"current": rows},
    }


def _semantic_development_registry_payload() -> dict:
    datasets = [
        {
            "dataset_id": "development-conversation-v1",
            "dataset_sha256": "a" * 64,
            "source_id_sha256s": sorted(
                hashlib.sha256(value.encode()).hexdigest()
                for value in ("dev-source-a", "dev-source-b")
            ),
            "question_family_ids": [
                "dev-adjacent",
                "dev-capability",
                "dev-followup",
                "dev-safety",
                "dev-tangent",
            ],
        }
    ]
    sources = sorted(
        {source for dataset in datasets for source in dataset["source_id_sha256s"]}
    )
    families = sorted(
        {family for dataset in datasets for family in dataset["question_family_ids"]}
    )
    return {
        "registry_version": "firelens_semantic_development_exposure_registry.v1",
        "registry_id": "firelens-v1-5-2-development-exposure",
        "frozen_at": "2026-08-06T08:00:00+00:00",
        "dataset_roster_sha256": upgrade_benchmark._sha256_json(datasets),
        "datasets": datasets,
        "source_id_sha256s": sources,
        "source_roster_sha256": upgrade_benchmark._sha256_json(sources),
        "question_family_ids": families,
        "question_family_roster_sha256": upgrade_benchmark._sha256_json(families),
    }


def _write_frontend_manual_review_fixture(
    tmp_path: Path, *, commit: str = "a" * 40
) -> tuple[Path, dict, dict[tuple[str, str], str]]:
    protocol_path = ROOT / "data/evaluation/frontend_manual_review.v1.yaml"
    protocol = _frontend_manual_review_protocol(protocol_path)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    candidate_id = f"firelens-v1-5-2:{commit}"
    target_url = "https://candidate.example.test/"
    captured_at = "2026-08-06T09:10:00+00:00"
    evidence_rows: list[dict] = []
    evidence_by_pair: dict[tuple[str, str], str] = {}

    index = 0
    for profile in protocol["test_profiles"]:
        for state_id in protocol["state_roster"]:
            index += 1
            evidence_id = f"EV-{index:03d}"
            if index == 1:
                relative_path = "evidence/candidate-identity.json"
                payload = {
                    "schema_version": "firelens.frontend_candidate_identity_evidence.v1",
                    "captured_at": captured_at,
                    "request": {
                        "method": "GET",
                        "url": "https://candidate.example.test/api/v1/health/ready",
                    },
                    "response": {
                        "status_code": 200,
                        "content_type": "application/json",
                        "candidate_id": candidate_id,
                        "build_commit": commit,
                    },
                }
                content = json.dumps(payload, sort_keys=True).encode()
                media_type = "application/json"
            else:
                relative_path = f"evidence/{profile['id']}--{state_id}.txt"
                content = f"manual evidence {profile['id']} {state_id} {index}\n".encode()
                media_type = "text/plain"
            evidence_path = tmp_path / relative_path
            evidence_path.write_bytes(content)
            evidence_rows.append(
                {
                    "evidence_id": evidence_id,
                    "path": relative_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                    "media_type": media_type,
                    "captured_at": captured_at,
                    "description": f"Retained {profile['id']} evidence for {state_id}.",
                    "profile_ids": [profile["id"]],
                    "state_ids": [state_id],
                }
            )
            evidence_by_pair[(profile["id"], state_id)] = evidence_id

    assignments = [
        {
            "role": "accessibility_specialist",
            "reviewer_id": "reviewer-a11y-001",
            "reviewer_name": "Alex Morgan",
            "credentials": "Accessibility specialist experienced with VoiceOver and WCAG 2.2.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T09:40:00+00:00",
            "attestation": "I performed and verified every assigned accessibility check.",
        },
        {
            "role": "wildfire_product_safety_reviewer",
            "reviewer_id": "reviewer-safety-001",
            "reviewer_name": "Jordan Chen",
            "credentials": "Wildfire public-information and product-safety reviewer.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T09:40:00+00:00",
            "attestation": "I performed and verified every assigned product-safety check.",
        },
        {
            "role": "release_adjudicator",
            "reviewer_id": "reviewer-release-001",
            "reviewer_name": "Taylor Singh",
            "credentials": "Independent release adjudicator for evidence-bound qualification.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T10:05:00+00:00",
            "attestation": "I independently reconciled the complete retained review evidence.",
        },
    ]
    assignment_by_role = {row["role"]: row for row in assignments}
    environments = [
        {
            "profile_id": profile["id"],
            "reviewer_id": assignment_by_role[profile["required_role"]]["reviewer_id"],
            "os_name": profile["os_name"],
            "os_version": "test-os-1.0",
            "browser_name": profile["browser_name"],
            "browser_version": "test-browser-1.0",
            "assistive_technology": profile["assistive_technology"],
            "assistive_technology_version": (
                None if profile["assistive_technology"] == "none" else "test-at-1.0"
            ),
            "input_methods": profile["input_methods"],
            "viewport": profile["viewport"],
            "zoom_percentages": profile["zoom_percentages"],
            "reflow_widths_css_px": profile["reflow_widths_css_px"],
            "reduced_motion": profile["reduced_motion"],
            "verified_at": "2026-08-06T09:05:00+00:00",
        }
        for profile in protocol["test_profiles"]
    ]
    coverage = [
        {
            "profile_id": profile["id"],
            "state_id": state_id,
            "status": "pass",
            "reviewer_id": assignment_by_role[profile["required_role"]]["reviewer_id"],
            "observed_at": "2026-08-06T09:20:00+00:00",
            "evidence_ids": [evidence_by_pair[(profile["id"], state_id)]],
            "notes": f"Reviewed {state_id} under {profile['id']}.",
        }
        for profile in protocol["test_profiles"]
        for state_id in protocol["state_roster"]
    ]
    criteria = []
    atomic_ids: list[str] = []
    for criterion in protocol["criteria"]:
        checks = []
        for check in criterion["atomic_checks"]:
            check_id = check["id"]
            atomic_ids.append(check_id)
            required_profiles = protocol["atomic_check_requirements"][check_id][
                "required_profile_ids"
            ]
            role = criterion["required_role"]
            checks.append(
                {
                    "check_id": check_id,
                    "status": "pass",
                    "reviewer_id": assignment_by_role[role]["reviewer_id"],
                    "reviewed_at": "2026-08-06T09:30:00+00:00",
                    "evidence_ids": [
                        evidence_by_pair[(profile_id, "idle")]
                        for profile_id in required_profiles
                    ],
                    "notes": f"Completed frozen atomic check {check_id}.",
                }
            )
        criteria.append({"criterion_id": criterion["id"], "atomic_checks": checks})

    coverage_ids = [
        f"{profile['id']}/{state_id}"
        for profile in protocol["test_profiles"]
        for state_id in protocol["state_roster"]
    ]
    bundle = {
        "schema_version": "firelens.frontend_manual_review_bundle.v1",
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": upgrade_benchmark.file_sha256(protocol_path),
        },
        "candidate": {
            "candidate_id": candidate_id,
            "commit": commit,
            "target_url": target_url,
            "build_verified_at": "2026-08-06T08:00:00+00:00",
            "identity_evidence_id": "EV-001",
        },
        "review_window": {
            "started_at": "2026-08-06T09:00:00+00:00",
            "completed_at": "2026-08-06T09:45:00+00:00",
        },
        "role_assignments": assignments,
        "test_environments": environments,
        "evidence": evidence_rows,
        "coverage": coverage,
        "criteria": criteria,
        "findings": [],
        "adjudication": {
            "adjudicator_id": "reviewer-release-001",
            "decision": "qualified",
            "decided_at": "2026-08-06T10:00:00+00:00",
            "accessibility_qualified": True,
            "product_safety_qualified": True,
            "open_finding_count": 0,
            "criterion_ids": [criterion["id"] for criterion in protocol["criteria"]],
            "atomic_check_ids": atomic_ids,
            "test_profile_ids": [profile["id"] for profile in protocol["test_profiles"]],
            "state_ids": protocol["state_roster"],
            "coverage_ids": coverage_ids,
            "evidence_ids": [row["evidence_id"] for row in evidence_rows],
            "attestation": "All frozen criteria, environments, states, and retained evidence were reconciled.",
        },
        "generated_at": "2026-08-06T10:10:00+00:00",
    }
    bundle_path = tmp_path / "frontend-manual-review.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle_path, bundle, evidence_by_pair


def _semantic_holdout_manifest_payload(*, development_registry_sha256: str = "4" * 64) -> dict:
    family_ids = ["evidence", "evacuation", "limitations", "location", "status"]
    roster = [
        {
            "case_id": f"SH{index:03d}",
            "input_sha256": hashlib.sha256(f"private-input-{index}".encode()).hexdigest(),
            "source_id_sha256s": [
                hashlib.sha256(f"holdout-source-{((index - 1) % 5) + 1}".encode()).hexdigest()
            ],
            "question_family_id": family_ids[(index - 1) % len(family_ids)],
        }
        for index in range(1, 26)
    ]
    source_roster = sorted({source for row in roster for source in row["source_id_sha256s"]})
    question_family_roster = sorted({row["question_family_id"] for row in roster})
    family_distribution = {
        family: sum(row["question_family_id"] == family for row in roster)
        for family in question_family_roster
    }
    development_registry = _semantic_development_registry_payload()
    return {
        "manifest_version": "firelens_semantic_holdout_manifest.v3",
        "dataset_sha256": "f" * 64,
        "case_roster_sha256": upgrade_benchmark._sha256_json(roster),
        "case_count": 25,
        "case_roster": roster,
        "source_id_sha256s": source_roster,
        "source_roster_sha256": upgrade_benchmark._sha256_json(source_roster),
        "question_family_ids": question_family_roster,
        "question_family_roster_sha256": upgrade_benchmark._sha256_json(question_family_roster),
        "question_family_distribution": family_distribution,
        "development_registry_id": development_registry["registry_id"],
        "development_registry_sha256": development_registry_sha256,
        "disjointness_audit": {
            "audit_version": "firelens_semantic_disjointness_audit.v1",
            "audited_at": "2026-08-06T09:00:00+00:00",
            "development_registry_sha256": development_registry_sha256,
            "development_source_roster_sha256": development_registry["source_roster_sha256"],
            "development_question_family_roster_sha256": development_registry[
                "question_family_roster_sha256"
            ],
            "holdout_source_roster_sha256": upgrade_benchmark._sha256_json(source_roster),
            "holdout_question_family_roster_sha256": upgrade_benchmark._sha256_json(
                question_family_roster
            ),
            "source_overlap_id_sha256s": [],
            "question_family_overlap_ids": [],
            "source_disjoint_from_development": True,
            "question_family_disjoint_from_development": True,
        },
        "frozen_before_candidate": True,
        "double_review_required": True,
        "frozen_at": "2026-08-06T09:30:00+00:00",
    }


def _semantic_holdout_candidate_report(
    manifest: dict, *, manifest_sha256: str = "0" * 64
) -> dict:
    cases = []
    for roster_row in manifest["case_roster"]:
        case_id = roster_row["case_id"]
        response = f"Grounded response for {case_id}."
        claim = f"Supported claim for {case_id}."
        cases.append(
            {
                "case_id": case_id,
                "input_sha256": roster_row["input_sha256"],
                "response": response,
                "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": claim,
                        "text_sha256": hashlib.sha256(claim.encode()).hexdigest(),
                    }
                ],
            }
        )
    candidate_identity = {
        "candidate_id": "candidate-v1-5-2",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "d" * 64,
        "configuration_sha256": "9" * 64,
    }
    return {
        "report_version": "firelens_semantic_holdout_report.v1",
        **candidate_identity,
        "candidate_identity_sha256": upgrade_benchmark._sha256_json(candidate_identity),
        "generated_at": "2026-08-06T10:00:00+00:00",
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha256,
        "case_count": manifest["case_count"],
        "cases": cases,
    }


def _semantic_holdout_review_bundle(
    report: dict,
    *,
    candidate_report_sha256: str = "1" * 64,
    manifest_sha256: str = "0" * 64,
    development_registry_sha256: str = "4" * 64,
) -> dict:
    case_ids = [case["case_id"] for case in report["cases"]]
    report_cases = {case["case_id"]: case for case in report["cases"]}
    reviewer_registry = [
        {"reviewer_id": "reviewer-a", "name": "Domain Expert A"},
        {"reviewer_id": "reviewer-b", "name": "Domain Expert B"},
    ]
    adjudicator = {
        "adjudicator_id": "adjudicator-a",
        "name": "Domain Adjudicator",
    }
    randomization_context = upgrade_benchmark._semantic_randomization_context_sha256(
        candidate_report_sha256=candidate_report_sha256,
        candidate_identity_sha256=report["candidate_identity_sha256"],
        dataset_manifest_sha256=manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    actors = [("reviewer", reviewer["reviewer_id"]) for reviewer in reviewer_registry] + [
        ("adjudicator", adjudicator["adjudicator_id"])
    ]
    actor_orders = []
    order_by_actor = {}
    for actor_role, actor_id in actors:
        order = upgrade_benchmark._semantic_actor_case_order(
            case_ids,
            randomization_context_sha256=randomization_context,
            actor_role=actor_role,
            actor_id=actor_id,
        )
        order_by_actor[(actor_role, actor_id)] = order
        actor_orders.append(
            {
                "actor_role": actor_role,
                "actor_id": actor_id,
                "case_ids": order,
                "case_order_sha256": upgrade_benchmark._sha256_json(order),
            }
        )

    case_reviews = {}
    for case_id in case_ids:
        claim_ids = [claim["claim_id"] for claim in report_cases[case_id]["claims"]]
        independent_reviews = [
            {
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "presentation_event_sha256": None,
                "independent": True,
                "blinded_to_candidate_identity": True,
                "blinded_to_other_review": True,
                "claim_labels": [
                    {"claim_id": claim_id, "label": "supported"} for claim_id in claim_ids
                ],
                "dangerous_omission": False,
                "case_decision": "approved",
            }
            for reviewer_id, reviewed_at in (
                ("reviewer-a", "2026-08-06T11:00:00+00:00"),
                ("reviewer-b", "2026-08-06T11:05:00+00:00"),
            )
        ]
        case_reviews[case_id] = {
            "case_id": case_id,
            "independent_reviews": independent_reviews,
            "adjudication": None,
        }

    events = []
    prior_digest = None

    def append_event(
        *,
        actor_role: str,
        actor_id: str,
        case_id: str,
        case_position: int,
        presented_at: datetime,
        review_material_sha256: str | None,
    ) -> str:
        candidate_case = report_cases[case_id]
        event = {
            "sequence": len(events) + 1,
            "event_id": f"PE{len(events) + 1:06d}",
            "event_type": (
                "independent_review_presentation"
                if actor_role == "reviewer"
                else "adjudication_presentation"
            ),
            "actor_role": actor_role,
            "actor_id": actor_id,
            "case_id": case_id,
            "case_position": case_position,
            "blinded_candidate_label": "Candidate A",
            "candidate_position": 1,
            "candidate_identity_sha256": report["candidate_identity_sha256"],
            "candidate_report_sha256": candidate_report_sha256,
            "input_sha256": candidate_case["input_sha256"],
            "response_sha256": candidate_case["response_sha256"],
            "claim_roster_sha256": upgrade_benchmark._semantic_claim_roster_sha256(
                candidate_case
            ),
            "review_material_sha256": review_material_sha256,
            "displayed_payload_sha256": None,
            "presented_at": presented_at.isoformat(),
            "previous_event_sha256": prior_digest,
        }
        event["displayed_payload_sha256"] = (
            upgrade_benchmark._semantic_displayed_payload_sha256(event)
        )
        event["event_sha256"] = upgrade_benchmark._semantic_presentation_event_sha256(event)
        events.append(event)
        return event["event_sha256"]

    reviewer_event_time = datetime(2026, 8, 6, 10, 1, tzinfo=UTC)
    for reviewer_index, reviewer in enumerate(reviewer_registry):
        reviewer_id = reviewer["reviewer_id"]
        for position, case_id in enumerate(order_by_actor[("reviewer", reviewer_id)], start=1):
            prior_digest = append_event(
                actor_role="reviewer",
                actor_id=reviewer_id,
                case_id=case_id,
                case_position=position,
                presented_at=reviewer_event_time,
                review_material_sha256=None,
            )
            reviewer_event_time += timedelta(seconds=1)
            case_reviews[case_id]["independent_reviews"][reviewer_index][
                "presentation_event_sha256"
            ] = prior_digest

    adjudication_event_time = datetime(2026, 8, 6, 11, 10, tzinfo=UTC)
    for position, case_id in enumerate(
        order_by_actor[("adjudicator", adjudicator["adjudicator_id"])], start=1
    ):
        independent_reviews = case_reviews[case_id]["independent_reviews"]
        review_digest = upgrade_benchmark._sha256_json(independent_reviews)
        prior_digest = append_event(
            actor_role="adjudicator",
            actor_id=adjudicator["adjudicator_id"],
            case_id=case_id,
            case_position=position,
            presented_at=adjudication_event_time,
            review_material_sha256=review_digest,
        )
        adjudication_event_time += timedelta(seconds=1)
        claim_ids = [claim["claim_id"] for claim in report_cases[case_id]["claims"]]
        case_reviews[case_id]["adjudication"] = {
            "adjudicator_id": adjudicator["adjudicator_id"],
            "adjudicated_at": "2026-08-06T12:00:00+00:00",
            "presentation_event_sha256": prior_digest,
            "reviewer_decisions_locked": True,
            "independent_reviews_sha256": review_digest,
            "resolution_status": "resolved",
            "claim_labels": [
                {"claim_id": claim_id, "label": "supported"} for claim_id in claim_ids
            ],
            "dangerous_omission": False,
            "case_decision": "approved",
        }

    cases = [
        case_reviews[case_id]
        for case_id in order_by_actor[("adjudicator", adjudicator["adjudicator_id"])]
    ]
    presentation_log = {
        "log_version": "firelens_semantic_holdout_presentation_log.v1",
        "log_id": "semantic-holdout-presentation-fixture",
        "append_only": True,
        "created_at": "2026-08-06T10:00:30+00:00",
        "finalized_at": "2026-08-06T11:20:00+00:00",
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_manifest_sha256": manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "randomization_context_sha256": randomization_context,
        "event_count": len(events),
        "events": events,
        "head_event_sha256": prior_digest,
    }
    return {
        "bundle_version": "firelens_semantic_holdout_review_bundle.v2",
        "generated_at": "2026-08-06T13:00:00+00:00",
        "candidate_id": report["candidate_id"],
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_sha256": report["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "case_count": report["case_count"],
        "case_ids": [case["case_id"] for case in report["cases"]],
        "presentation": {
            "candidate_identity_blinded": True,
            "reviewers_blinded_to_each_other": True,
            "randomized": True,
            "randomization_algorithm": "sha256_identity_bound_sort.v1",
            "randomization_context_sha256": randomization_context,
            "blinded_candidate_label": "Candidate A",
            "actor_orders": actor_orders,
            "presentation_log_sha256": upgrade_benchmark._sha256_json(presentation_log),
        },
        "presentation_log": presentation_log,
        "reviewer_registry": reviewer_registry,
        "adjudicator": adjudicator,
        "cases": cases,
    }


def _semantic_holdout_evidence() -> tuple[dict, dict, dict]:
    manifest = _semantic_holdout_manifest_payload()
    report = _semantic_holdout_candidate_report(manifest)
    bundle = _semantic_holdout_review_bundle(report)
    return manifest, report, bundle


def _validate_semantic_holdout_payloads(
    manifest: dict, report: dict, bundle: dict, summary: dict | None = None
) -> dict:
    return _semantic_holdout(
        report,
        bundle,
        manifest=manifest,
        development_registry=_semantic_development_registry_payload(),
        candidate_report_sha256="1" * 64,
        review_bundle_sha256="3" * 64,
        dataset_manifest_sha256="0" * 64,
        development_registry_sha256="4" * 64,
        submitted_summary=summary,
    )


def _write_semantic_holdout_evidence(
    tmp_path: Path, *, include_summary: bool = False
) -> tuple[Path, Path, Path, Path, Path | None]:
    development_registry = _semantic_development_registry_payload()
    development_registry_path = tmp_path / "semantic-development-registry.json"
    development_registry_path.write_text(
        json.dumps(development_registry, indent=2), encoding="utf-8"
    )
    development_registry_sha256 = upgrade_benchmark.file_sha256(development_registry_path)
    manifest = _semantic_holdout_manifest_payload(
        development_registry_sha256=development_registry_sha256
    )
    manifest_path = tmp_path / "semantic-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest_sha256 = upgrade_benchmark.file_sha256(manifest_path)
    report = _semantic_holdout_candidate_report(manifest, manifest_sha256=manifest_sha256)
    report_path = tmp_path / "semantic-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bundle = _semantic_holdout_review_bundle(
        report,
        candidate_report_sha256=upgrade_benchmark.file_sha256(report_path),
        manifest_sha256=manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    bundle_path = tmp_path / "semantic-review-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    summary_path = None
    if include_summary:
        recomputed = validate_semantic_holdout(
            report_path,
            bundle_path,
            manifest_path,
            development_registry_path,
        )
        summary = {key: value for key, value in recomputed.items() if key != "status"}
        summary["generated_at"] = "2026-08-06T13:01:00+00:00"
        summary_path = tmp_path / "semantic-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return (
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    )


def _ux_report() -> dict:
    spec = load_spec(SPEC_PATH)
    participants = []
    for index in range(12):
        device_class = "mobile" if index % 2 == 0 else "desktop"
        access_methods = ["touch" if device_class == "mobile" else "pointer"]
        if index == 0:
            access_methods.append("keyboard")
        elif index == 1:
            access_methods.append("screen_reader")
        participants.append(
            {
                "participant_id": f"P{index + 1:02d}",
                "cohort": "novice_bc_resident" if index < 4 else "wildfire_aware",
                "device_class": device_class,
                "access_methods": access_methods,
            }
        )
    attempts = []
    for participant in participants:
        for task in spec.ux_tasks:
            row = {
                "participant_id": participant["participant_id"],
                "task_id": task.id,
                "criterion_results": {
                    criterion.id: True for criterion in task.completion_criteria
                },
                "critical_error_codes": [],
                "critical_error_notes": {},
                "duration_seconds": 30.0,
                "seq_score": 6,
                "confidence": 6,
                "observed_outcome": "Completed using the expected evidence path.",
            }
            attempts.append(row)
    return {
        "schema_version": "firelens_ux_benchmark_report.v3",
        "label": "before",
        "protocol_id": spec.benchmark_id,
        "commit": "a" * 40,
        "deployment_id": "local-before",
        "moderator": "Morgan Lee",
        "observed_at": "2026-08-06T12:00:00+00:00",
        "participant_count": 12,
        "recruitment_constraint": "Twelve participants complete the frozen baseline round.",
        "participants": participants,
        "attempts": attempts,
        "task_reference": [task.model_dump() for task in spec.ux_tasks],
    }


def _preview_report() -> dict:
    commit = "a" * 40
    version = "1.5.2"
    generated_at = "2026-08-06T10:00:00+00:00"
    quote = "Keep water"
    primary_text = "Keep water in an emergency kit."
    quote_digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()

    def support_proof() -> dict:
        return {
            "claims": [
                {
                    "claim_id": "C1",
                    "supports": [
                        {
                            "evidence_id": "E1",
                            "quote_sha256": quote_digest,
                            "quote_length": len(quote),
                            "match_start": 0,
                            "match_end": len(quote),
                            "matched_slice_sha256": quote_digest,
                        }
                    ],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "E1",
                    "primary_text_sha256": hashlib.sha256(
                        primary_text.encode("utf-8")
                    ).hexdigest(),
                    "primary_text_length": len(primary_text),
                }
            ],
        }

    live_record = {
        "result_id": "incident:1",
        "authority": "BC Wildfire Service",
        "source_url": "https://official.example.test/incident",
        "source_updated_at": generated_at,
        "retrieved_at": generated_at,
        "status": "Active",
    }
    protocol = [
        ("homepage", "GET", "/", {}, {}),
        ("liveness", "GET", "/api/v1/health/live", {}, {"status": "alive"}),
        (
            "readiness",
            "GET",
            "/api/v1/health/ready",
            {},
            {
                "status": "ready",
                "release_version": version,
                "build_commit": commit,
                "deployment_id": "preview-1",
                "rate_limit_scope": "instance_local",
            },
        ),
        (
            "static",
            "POST",
            "/api/v1/ask",
            {"question": "What belongs in an emergency kit?"},
            {
                "status": "answer",
                "response_mode": "grounded",
                "claim_count": 1,
                "evidence_count": 1,
                "live_result_count": 0,
                "exact_support": support_proof(),
            },
        ),
        (
            "unsupported",
            "POST",
            "/api/v1/ask",
            {"question": ("What is the current air quality in Vancouver from wildfire smoke?")},
            {
                "status": "abstention",
                "response_mode": "abstention",
                "claim_count": 0,
                "evidence_count": 0,
                "live_result_count": 0,
            },
        ),
        (
            "live",
            "POST",
            "/api/v1/ask",
            {"question": "Are there active wildfires in BC currently?"},
            {
                "status": "answer",
                "response_mode": "live",
                "claim_count": 0,
                "evidence_count": 0,
                "live_result_count": 1,
                "live_records": [live_record],
            },
        ),
        (
            "mixed",
            "POST",
            "/api/v1/ask",
            {
                "question": (
                    "Are there active wildfires in BC currently, and what belongs in an "
                    "emergency kit?"
                )
            },
            {
                "status": "answer",
                "response_mode": "mixed",
                "claim_count": 1,
                "evidence_count": 1,
                "live_result_count": 1,
                "exact_support": support_proof(),
                "live_records": [live_record],
            },
        ),
        (
            "map",
            "GET",
            "/api/v1/live/map",
            {"layers": ["incidents"]},
            {"record_count": 1, "records": [live_record]},
        ),
    ]
    requests = []
    for case_id, method, path, request_payload, response in protocol:
        response_payload = json.dumps(response, separators=(",", ":"), sort_keys=True)
        requests.append(
            {
                "case_id": case_id,
                "method": method,
                "path": path,
                "request": request_payload,
                "request_body_sha256": (
                    upgrade_benchmark._sha256_json(request_payload)
                    if method == "POST"
                    else None
                ),
                "status_code": 200,
                "latency_ms": 10.0,
                "response_content_type": (
                    "text/html; charset=utf-8" if case_id == "homepage" else "application/json"
                ),
                "response_content_length_bytes": len(response_payload.encode("utf-8")),
                "response_body_sha256": hashlib.sha256(
                    response_payload.encode("utf-8")
                ).hexdigest(),
                "response": response,
            }
        )
    checks = {
        "homepage_anonymous": True,
        "liveness": True,
        "readiness": True,
        "release_identity": True,
        "static_grounded": True,
        "unsupported_fails_closed": True,
        "live_metadata_complete": True,
        "mixed_separates_sources": True,
        "chat_map_records_match": True,
        "static_p95_within_target": True,
    }
    return {
        "report_version": "firelens.preview_qualification.v1",
        "evidence_schema_version": "firelens.preview_qualification.evidence.v1",
        "generated_at": generated_at,
        "base_url": "https://preview.example.test",
        "expected": {"release_version": version, "build_commit": commit},
        "observed": {
            "release_version": version,
            "build_commit": commit,
            "deployment_id": "preview-1",
            "rate_limit_scope": "instance_local",
        },
        "requests": requests,
        "ask_p95_ms": 10.0,
        "p95_target_ms": 4_000.0,
        "checks": checks,
        "qualified": True,
        "elapsed_seconds": 1.0,
        "not_executed": [
            (
                "forced official-source outage requires an approved preview failure-injection "
                "mechanism"
            ),
            "screen-reader and mobile interaction require browser verification",
            "distributed firewall enforcement requires owner review and publication",
        ],
    }


def _deployment_report() -> dict:
    return {
        "schema_version": "firelens_deployment_benchmark_report.v2",
        "label": "after",
        "commit": "a" * 40,
        "reviewed_by": "Release Owner",
        "reviewed_at": "2026-08-06T12:00:00+00:00",
        "distributed_rate_limit_verified": True,
        "rollback_rehearsal_passed": True,
        "rate_limit_evidence": {
            "platform": "vercel_firewall",
            "rule_id": "firewall-rule-1",
            "candidate_deployment_id": "candidate-a",
            "shared_key_sha256": "c" * 64,
            "configured_limit": 5,
            "first_rejected_combined_ordinal": 6,
            "observations": [
                {
                    "client_id": "client-a",
                    "region": "iad1",
                    "observed_at": "2026-08-06T12:00:00+00:00",
                    "combined_ordinal": 1,
                    "status_code": 200,
                },
                {
                    "client_id": "client-b",
                    "region": "sfo1",
                    "observed_at": "2026-08-06T12:00:01+00:00",
                    "combined_ordinal": 6,
                    "status_code": 429,
                },
            ],
        },
        "rollback_evidence": {
            "candidate_deployment_id": "candidate-a",
            "candidate_commit": "a" * 40,
            "restored_deployment_id": "previous-a",
            "restored_commit": "b" * 40,
            "verified_at": "2026-08-06T12:05:00+00:00",
            "checks": {
                "readiness_restored": True,
                "homepage_anonymous": True,
                "release_identity_restored": True,
                "grounded_smoke_passed": True,
                "live_smoke_passed": True,
            },
        },
        "notes": "",
    }


def _write_deployment_evidence(tmp_path: Path, report: dict) -> tuple[Path, Path]:
    rate_limit_path = tmp_path / "rate-limit-evidence.json"
    rollback_path = tmp_path / "rollback-evidence.json"
    rate_limit_path.write_text(
        json.dumps(report["rate_limit_evidence"], sort_keys=True), encoding="utf-8"
    )
    rollback_path.write_text(
        json.dumps(report["rollback_evidence"], sort_keys=True), encoding="utf-8"
    )
    report["rate_limit_artifact_sha256"] = upgrade_benchmark.file_sha256(rate_limit_path)
    report["rollback_artifact_sha256"] = upgrade_benchmark.file_sha256(rollback_path)
    return rate_limit_path, rollback_path


def test_frontend_manual_protocol_freezes_thresholds_standards_and_matrix() -> None:
    protocol = _frontend_manual_review_protocol(
        ROOT / "data/evaluation/frontend_manual_review.v1.yaml"
    )

    assert protocol["status"] == "frozen"
    assert protocol["standards"]["wcag_version"] == "2.2"
    assert protocol["standards"]["conformance_level"] == "AA"
    assert protocol["manual_thresholds"] == {
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
    assert len(protocol["test_profiles"]) == 5
    assert len(protocol["state_roster"]) == 10
    assert len(protocol["atomic_check_requirements"]) == 30
    assert all(
        requirement["required_profile_ids"]
        for requirement in protocol["atomic_check_requirements"].values()
    )


def test_frontend_manual_review_recomputes_complete_bundle(tmp_path: Path) -> None:
    bundle_path, _, _ = _write_frontend_manual_review_fixture(tmp_path)

    result = validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    assert result["status"] == "complete"
    assert result["candidate_id"] == f"firelens-v1-5-2:{'a' * 40}"
    assert result["test_profile_count"] == 5
    assert result["state_count"] == 10
    assert result["coverage_count"] == 50
    assert result["atomic_check_count"] == 30
    assert result["accessibility_qualified"] is True
    assert result["product_safety_qualified"] is True
    assert result["open_finding_count"] == 0
    assert result["qualified"] is True


def test_frontend_manual_review_records_honest_open_finding(tmp_path: Path) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    first_check = bundle["criteria"][0]["atomic_checks"][0]
    first_check["status"] = "fail"
    bundle["findings"] = [
        {
            "finding_id": "F-001",
            "target_type": "atomic_check",
            "target_id": first_check["check_id"],
            "severity": "high",
            "status": "open",
            "opened_at": "2026-08-06T09:25:00+00:00",
            "resolved_at": None,
            "owner_id": "reviewer-a11y-001",
            "resolution": None,
            "evidence_ids": [first_check["evidence_ids"][0]],
        }
    ]
    bundle["adjudication"].update(
        {
            "decision": "not_qualified",
            "accessibility_qualified": False,
            "open_finding_count": 1,
        }
    )
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    result = validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    assert result["accessibility_qualified"] is False
    assert result["product_safety_qualified"] is True
    assert result["open_finding_count"] == 1
    assert result["qualified"] is False


def test_frontend_manual_review_rejects_non_distinct_or_placeholder_roles(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["role_assignments"][1]["reviewer_name"] = bundle["role_assignments"][0][
        "reviewer_name"
    ]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="distinct people"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle["role_assignments"][1]["reviewer_name"] = "Reviewer"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="named human"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_sparse_matrix_or_check_evidence(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["coverage"].pop()
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage roster is incomplete"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    screen_reader_check = bundle["criteria"][1]["atomic_checks"][0]
    screen_reader_check["evidence_ids"] = screen_reader_check["evidence_ids"][:1]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="omits required test profiles"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_wrong_candidate_url_or_commit(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)

    with pytest.raises(ValueError, match="wrong candidate commit"):
        validate_frontend_manual_review(bundle_path, expected_commit="b" * 40)

    bundle["candidate"]["target_url"] = "https://other.example.test/"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="identity request targets the wrong URL"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_tampered_or_unsafe_retained_evidence(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    evidence_path = tmp_path / bundle["evidence"][1]["path"]
    evidence_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="digest does not match"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["evidence"][1]["path"] = "../outside.txt"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical relative path"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_timestamp_or_adjudication_tampering(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["role_assignments"][0]["attested_at"] = "2026-08-06T09:15:00+00:00"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="attestation chain"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["adjudication"]["open_finding_count"] = 1
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="summary differs"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_protocol_rejects_weakened_threshold(tmp_path: Path) -> None:
    protocol = yaml.safe_load(
        (ROOT / "data/evaluation/frontend_manual_review.v1.yaml").read_text(encoding="utf-8")
    )
    protocol["manual_thresholds"]["target_width_css_px_min"] = 20
    path = tmp_path / "weakened-protocol.yaml"
    path.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="thresholds are not canonical"):
        _frontend_manual_review_protocol(path)


def test_spec_is_v2_provisional_and_registry_roles_are_valid() -> None:
    spec = load_spec(SPEC_PATH)
    registry = load_dataset_role_registry(ROOT / spec.dataset_role_registry)

    assert spec.schema_version == "firelens_upgrade_benchmark_spec.v2"
    assert spec.frozen_before_upgrade is False
    assert spec.dataset_role_registry in spec.identity_inputs
    assert "data/evaluation/frontend_surface.v1.yaml" in spec.identity_inputs
    assert "data/evaluation/frontend_manual_review.v1.yaml" in spec.identity_inputs
    assert "config/runtime_artifact_allowlist.v1.json" in spec.identity_inputs
    assert "scripts/upgrade_benchmark.py" in spec.harness_inputs
    assert {
        "src/firelens/evaluation/common.py",
        "src/firelens/evaluation/frontend_browser.py",
        "src/firelens/evaluation/frontend_map.py",
        "src/firelens/evaluation/frontend_privacy.py",
        "src/firelens/evaluation/frontend_protocol.py",
        "src/firelens/evaluation/frontend_qualification.py",
        "src/firelens/evaluation/frontend_surface.py",
        "src/firelens/evaluation/qualification_reports.py",
        "src/firelens/evaluation/runtime_artifact.py",
    }.issubset(spec.harness_inputs)
    assert {
        "src/firelens/benchmark.py",
        "src/firelens/benchmark_contracts.py",
        "src/firelens/benchmark_retrieval.py",
        "src/firelens/benchmark_support.py",
    }.issubset(spec.harness_inputs)
    assert "src/firelens/review_workspace/input_common.py" in spec.harness_inputs
    assert {
        "src/firelens/review_workspace/session.py",
        "src/firelens/review_workspace/session_common.py",
        "src/firelens/review_workspace/session_evidence.py",
        "src/firelens/review_workspace/session_journal.py",
    }.issubset(spec.harness_inputs)
    assert "src/firelens/runtime_artifact.py" in spec.harness_inputs
    assert {
        "src/firelens/runtime_artifact_closure.py",
        "src/firelens/runtime_artifact_common.py",
        "src/firelens/runtime_artifact_comparison.py",
        "src/firelens/runtime_artifact_files.py",
    }.issubset(spec.harness_inputs)
    assert "tests/test_runtime_artifact.py" in spec.harness_inputs
    assert "tests/test_upgrade_benchmark.py" in spec.harness_inputs
    assert "apps/web/scripts/qualify-frontend-surface.mjs" in spec.harness_inputs
    assert len(spec.comparison_metrics) == len(
        {metric.key for metric in spec.comparison_metrics}
    )
    assert {task.id for task in spec.ux_tasks} == {
        "UX01",
        "UX02",
        "UX03",
        "UX04",
        "UX05",
    }
    manual_metrics = {
        metric.key: metric
        for metric in spec.comparison_metrics
        if metric.key.startswith("frontend_manual_")
    }
    assert set(manual_metrics) == {
        "frontend_manual_accessibility_qualified",
        "frontend_manual_product_safety_qualified",
        "frontend_manual_open_findings",
    }
    assert all(metric.comparison_mode == "after_only" for metric in manual_metrics.values())
    runtime_metrics = {
        metric.key: metric
        for metric in spec.comparison_metrics
        if metric.key.startswith("runtime_artifact_")
    }
    assert set(runtime_metrics) == {
        "runtime_artifact_qualified",
        "runtime_artifact_missing_required_count",
        "runtime_artifact_prohibited_count",
        "runtime_artifact_identity_match",
        "runtime_artifact_candidate_commit_match",
    }
    assert all(metric.comparison_mode == "after_only" for metric in runtime_metrics.values())

    sealed = [
        dataset
        for dataset in registry.datasets
        if dataset.role == "sealed_release_qualification"
    ]
    assert sealed == []
    v2 = next(dataset for dataset in registry.datasets if dataset.id.endswith("v2"))
    assert v2.role == "permanent_regression"
    assert v2.baseline_policy == "paired"
    v3 = next(dataset for dataset in registry.datasets if dataset.id.endswith("v3"))
    assert v3.role == "planned_sealed_qualification"
    assert v3.status == "planned"
    assert all(
        (ROOT / relative).is_file()
        for dataset in registry.datasets
        if dataset.status == "available"
        for relative in dataset.inputs
    )


def test_runtime_artifact_metrics_are_recomputed_from_retained_inventories() -> None:
    _, after = _passing_snapshots()

    values = upgrade_benchmark._runtime_artifact_metric_values(after)

    assert values == {
        "runtime_artifact_qualified": True,
        "runtime_artifact_missing_required_count": 0,
        "runtime_artifact_prohibited_count": 0,
        "runtime_artifact_identity_match": True,
        "runtime_artifact_candidate_commit_match": True,
    }

    after["runtime_artifact"]["comparison"]["qualified"] = False
    with pytest.raises(ValueError, match="differs from recomputed"):
        upgrade_benchmark._runtime_artifact_metric_values(after)


def test_runtime_artifact_metrics_detect_missing_and_prohibited_files() -> None:
    _, missing = _passing_snapshots()
    for inventory in missing["runtime_artifact"]["inventories"].values():
        inventory["files"] = [
            row for row in inventory["files"] if row["logical_path"] != "requirements.lock"
        ]
    _rehash_runtime_artifact_section(missing["runtime_artifact"])
    _sync_runtime_artifact_commitments(missing)

    missing_values = upgrade_benchmark._runtime_artifact_metric_values(missing)
    assert missing_values["runtime_artifact_missing_required_count"] == 2
    assert missing_values["runtime_artifact_qualified"] is False

    _, prohibited = _passing_snapshots()
    logical_path = "data/evaluation/sealed-leak.json"
    content_sha256 = hashlib.sha256(b"leak").hexdigest()
    for _platform_name, inventory in prohibited["runtime_artifact"]["inventories"].items():
        platform_root = inventory["identity"]["platform_root"]
        inventory["files"].append(
            {
                "logical_path": logical_path,
                "platform_path": f"{platform_root}/{logical_path}",
                "size_bytes": 4,
                "sha256": content_sha256,
            }
        )
    _rehash_runtime_artifact_section(prohibited["runtime_artifact"])
    _sync_runtime_artifact_commitments(prohibited)

    prohibited_values = upgrade_benchmark._runtime_artifact_metric_values(prohibited)
    assert prohibited_values["runtime_artifact_prohibited_count"] == 2
    assert prohibited_values["runtime_artifact_qualified"] is False


def test_runtime_artifact_metrics_detect_candidate_commit_substitution() -> None:
    _, after = _passing_snapshots()
    substituted_commit = "c" * 40
    section = after["runtime_artifact"]
    for platform_name, inventory in section["inventories"].items():
        evidence = section["candidate_configurations"][platform_name]
        document = json.loads(evidence["raw_json"])
        document["build_commit"] = substituted_commit
        raw_json = json.dumps(document, sort_keys=True)
        raw = raw_json.encode()
        evidence.update(
            {
                "raw_json": raw_json,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
        inventory["identity"]["build_commit"] = substituted_commit
        inventory["runtime_configuration"]["sha256"] = evidence["sha256"]
        candidate_entry = next(
            row
            for row in inventory["files"]
            if row["logical_path"] == "config/runtime_candidate.v1.json"
        )
        candidate_entry["sha256"] = evidence["sha256"]
        candidate_entry["size_bytes"] = evidence["size_bytes"]
    _rehash_runtime_artifact_section(section)
    _sync_runtime_artifact_commitments(after)

    values = upgrade_benchmark._runtime_artifact_metric_values(after)
    assert values["runtime_artifact_candidate_commit_match"] is False
    assert values["runtime_artifact_identity_match"] is False
    assert values["runtime_artifact_qualified"] is False


def test_runtime_artifact_capture_sequence_rejects_artifact_mutation() -> None:
    _, after = _passing_snapshots()
    pre_command = {
        key: value
        for key, value in after["runtime_artifact"].items()
        if key != "capture_sequence"
    }
    post_command = json.loads(json.dumps(pre_command))
    post_command["inventories"]["docker"]["identity"]["artifact_id"] = "docker-mutated"

    with pytest.raises(ValueError, match="changed during benchmark capture"):
        upgrade_benchmark._finalize_runtime_artifact_pair(pre_command, post_command)


def test_registry_rejects_unsafe_sealed_policy(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    sealed = next(
        dataset
        for dataset in source["datasets"]
        if dataset["id"] == "benchmark_v1_5_2_sealed_retrieval_v3"
    )
    sealed["role"] = "sealed_release_qualification"
    sealed["status"] = "available"
    sealed["inputs"] = [
        "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
        "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json",
    ]
    sealed["prohibited_uses"].remove("tuning")
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required prohibitions"):
        load_dataset_role_registry(path)


def test_registry_rejects_planned_sealed_status_only_promotion(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    planned = next(
        dataset
        for dataset in source["datasets"]
        if dataset["role"] == "planned_sealed_qualification"
    )
    planned["status"] = "available"
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot become available without role conversion"):
        load_dataset_role_registry(path)


def test_registry_rejects_after_only_data_disguised_as_development(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    sealed = next(
        dataset
        for dataset in source["datasets"]
        if dataset["id"] == "benchmark_v1_5_2_sealed_retrieval_v3"
    )
    sealed["status"] = "available"
    sealed["role"] = "development"
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="must use the sealed release role"):
        load_dataset_role_registry(path)


def test_spec_requires_registry_in_frozen_identity(tmp_path: Path) -> None:
    source = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    source["identity_inputs"].remove(source["dataset_role_registry"])
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a frozen identity input"):
        load_spec(path)


def test_spec_rejects_missing_harness_input(tmp_path: Path) -> None:
    source = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    source["harness_inputs"].append("scripts/does_not_exist.py")
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="benchmark input does not exist"):
        load_spec(path)


def test_passing_v2_snapshots_pass_the_benchmark_gate() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()

    comparison = compare_snapshots(before, after, spec)

    assert comparison["schema_version"] == "firelens_upgrade_benchmark_comparison.v2"
    assert comparison["summary"]["benchmark_gate_passed"] is True
    assert comparison["summary"]["missing_required_before"] == []
    assert comparison["summary"]["missing_required_after"] == []
    assert comparison["summary"]["comparability_failures"] == []
    assert comparison["comparability"]["execution_environment"]["passed"] is True
    assert comparison["comparability"]["ux_sampling"]["passed"] is True


def test_compare_recomputes_and_records_before_seal_ancestry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    before, after = _passing_snapshots()
    before["identity"]["spec_sha256"] = upgrade_benchmark.file_sha256(SPEC_PATH)
    before["identity"]["identity_input_sha256"] = {
        relative: upgrade_benchmark.file_sha256(ROOT / relative)
        for relative in spec.identity_inputs
    }
    before["identity"]["harness_input_sha256"] = {
        relative: upgrade_benchmark.file_sha256(ROOT / relative)
        for relative in spec.harness_inputs
    }
    after["identity"] = {
        **before["identity"],
        "commit": "c" * 40,
        "candidate_id": f"firelens-v1-5-2:{'c' * 40}",
    }
    after["runtime_artifact"] = _runtime_artifact_snapshot_fixture(after["identity"])
    _sync_runtime_artifact_commitments(after)
    ancestry = {
        "status": "verified",
        "seal_path": spec.before_snapshot_seal,
        "seal_sha256": "d" * 64,
        "before_candidate_commit": "a" * 40,
        "seal_introducing_commit": "b" * 40,
        "after_candidate_commit": "c" * 40,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }
    after["before_snapshot_ancestry"] = ancestry
    after_path = tmp_path / "after.json"
    output_json = tmp_path / "comparison.json"
    output_markdown = tmp_path / "comparison.md"
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: spec)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: before,
    )
    monkeypatch.setattr(upgrade_benchmark, "_read_report", lambda path: after)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: ancestry,
    )

    result = upgrade_benchmark.compare(
        SimpleNamespace(
            spec=SPEC_PATH,
            before=tmp_path / "before.json",
            after=after_path,
            output_json=output_json,
            output_markdown=output_markdown,
        )
    )

    assert result == 0
    persisted = json.loads(output_json.read_text(encoding="utf-8"))
    assert persisted["before_snapshot_ancestry"] == ancestry
    assert ancestry["seal_introducing_commit"] in output_markdown.read_text(encoding="utf-8")


def test_compare_rejects_tampered_after_ancestry_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    before, after = _passing_snapshots()
    after["before_snapshot_ancestry"] = {"seal_introducing_commit": "wrong"}
    recomputed = {"seal_introducing_commit": "b" * 40}
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: spec)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: before,
    )
    monkeypatch.setattr(upgrade_benchmark, "_read_report", lambda path: after)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: recomputed,
    )

    with pytest.raises(ValueError, match="differs from recomputed Git history"):
        upgrade_benchmark.compare(
            SimpleNamespace(
                spec=SPEC_PATH,
                before=tmp_path / "before.json",
                after=tmp_path / "after.json",
                output_json=tmp_path / "comparison.json",
                output_markdown=tmp_path / "comparison.md",
            )
        )


def test_paired_tolerance_boundary_is_inclusive_and_beyond_is_regression() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "frontend_initial_route_js_gzip_bytes"
    _set_snapshot_metric(before, key, 70_000)
    _set_snapshot_metric(after, key, 72_100)

    at_boundary = compare_snapshots(before, after, spec)
    boundary_row = next(row for row in at_boundary["metrics"] if row["key"] == key)
    assert boundary_row["verdict"] == "within_tolerance"
    assert boundary_row["comparison_requirement_passed"] is True

    _set_snapshot_metric(after, key, 72_101)
    beyond = compare_snapshots(before, after, spec)
    beyond_row = next(row for row in beyond["metrics"] if row["key"] == key)
    assert beyond_row["verdict"] == "regressed"
    assert beyond_row["comparison_requirement_passed"] is False
    assert key in beyond["summary"]["regressions"]
    assert beyond["summary"]["benchmark_gate_passed"] is False


def test_exact_ratified_required_improvement_counts_as_improved() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "ux_near_me_median_seconds"
    _set_snapshot_metric(before, key, 40.0)
    _set_snapshot_metric(after, key, 30.0)

    comparison = compare_snapshots(before, after, spec)
    row = next(row for row in comparison["metrics"] if row["key"] == key)

    assert row["verdict"] == "improved"
    assert row["comparison_requirement_passed"] is True
    assert key not in comparison["summary"]["insufficient_improvement"]


def test_missing_paired_before_value_fails_closed() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "development_retrieval_recall_at_5"
    _set_snapshot_metric(before, key, None)

    comparison = compare_snapshots(before, after, spec)
    row = next(row for row in comparison["metrics"] if row["key"] == key)

    assert row["verdict"] == "not_measured"
    assert row["comparison_requirement_passed"] is False
    assert comparison["summary"]["missing_required_before"] == [key]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_after_only_metric_forbids_any_before_value() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(before, "sealed_retrieval_qualified", False)

    with pytest.raises(
        ValueError,
        match="after-only metric sealed_retrieval_qualified must not have a before value",
    ):
        compare_snapshots(before, after, spec)


@pytest.mark.parametrize(
    ("key", "invalid", "message"),
    [
        ("verification_passed", 1, "strict boolean"),
        ("offline_hard_probe_critical_failures", 0.0, "must be an integer"),
        ("offline_hard_probe_pass_rate", "1.0", "must be numeric"),
        ("offline_hard_probe_pass_rate", math.nan, "must be finite"),
    ],
)
def test_metric_values_are_strictly_typed(key: str, invalid: object, message: str) -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["metrics"][key] = invalid

    with pytest.raises(ValueError, match=message):
        compare_snapshots(before, after, spec)


def test_comparison_recomputes_metrics_and_rejects_stored_divergence() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["metrics"]["offline_hard_probe_pass_rate"] = 0.5

    with pytest.raises(ValueError, match="diverges from its detailed evidence"):
        compare_snapshots(before, after, spec)


def test_missing_review_is_not_misreported_as_zero_approval() -> None:
    summary = _review(
        None,
        expected_cases=50,
        expected_summary_version="firelens_owner_semantic_review_summary.v1",
    )

    assert summary == {
        "status": "missing",
        "case_count": 50,
        "approved_case_count": None,
        "approval_rate": None,
        "qualified": None,
    }


def test_recomputed_review_summary_rejects_aggregate_substitution() -> None:
    recomputed = {
        "summary_version": "firelens_owner_semantic_review_summary.v1",
        "generated_at": "2026-08-06T01:00:00+00:00",
        "case_count": 50,
        "approved_case_count": 49,
        "qualified": False,
        "cases": [{"case_id": "case-1", "approved": False}],
    }
    submitted = {
        **recomputed,
        "generated_at": "2026-08-06T02:00:00+00:00",
        "approved_case_count": 50,
        "qualified": True,
    }

    with pytest.raises(ValueError, match="differs from raw validated evidence"):
        _assert_recomputed_summary_matches(submitted, recomputed, context="semantic review")

    submitted = {**recomputed, "generated_at": "2026-08-06T02:00:00+00:00"}
    _assert_recomputed_summary_matches(submitted, recomputed, context="semantic review")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("summary_version", "wrong.v1", "unsupported summary_version"),
        ("case_count", 49, "exactly 50 cases"),
        ("expected_case_count_present", False, "exactly 50 cases"),
        ("reviewer_present", False, "named reviewer and review timestamp"),
        ("reviewed_at_present", False, "named reviewer and review timestamp"),
        ("qualified", 1, "strict boolean"),
    ],
)
def test_partial_review_summary_is_rejected(field: str, value: object, message: str) -> None:
    report = {
        "summary_version": "firelens_owner_semantic_review_summary.v1",
        "case_count": 50,
        "approved_case_count": 50,
        "expected_case_count_present": True,
        "reviewer_present": True,
        "reviewed_at_present": True,
        "qualified": True,
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
    }
    report[field] = value

    with pytest.raises(ValueError, match=message):
        _review(
            report,
            expected_cases=50,
            expected_summary_version="firelens_owner_semantic_review_summary.v1",
        )


def test_frontend_bundle_classifies_manifest_graph_initial_and_lazy(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client)

    bundle = _frontend_bundle(dist)
    by_name = {row["name"]: row for row in bundle["assets"]}

    assert {name: row["scope"] for name, row in by_name.items() if row["category"] == "js"} == {
        "client/assets/app.js": "initial",
        "client/assets/map.js": "lazy",
        "client/assets/shared.js": "initial",
        "server/index.js": "server",
    }
    initial_content = [
        (client / "assets/app.js").read_bytes(),
        (client / "assets/shared.js").read_bytes(),
    ]
    assert bundle["initial_js_bytes"] == sum(map(len, initial_content))
    assert bundle["initial_js_gzip_bytes"] == sum(
        len(gzip.compress(content, compresslevel=9, mtime=0)) for content in initial_content
    )
    map_content = (client / "assets/map.js").read_bytes()
    assert bundle["lazy_js_bytes"] == len(map_content)
    assert bundle["lazy_js_gzip_bytes"] == len(
        gzip.compress(map_content, compresslevel=9, mtime=0)
    )
    assert bundle["total_js_bytes"] == (
        bundle["initial_js_bytes"] + bundle["lazy_js_bytes"] + bundle["server_js_bytes"]
    )
    assert by_name["client/assets/app.css"]["scope"] == "initial"
    assert by_name["client/assets/map.css"]["scope"] == "lazy"
    assert bundle["initial_css_gzip_bytes"] == len(
        gzip.compress((client / "assets/app.css").read_bytes(), compresslevel=9, mtime=0)
    )
    assert bundle["lazy_css_gzip_bytes"] == len(
        gzip.compress((client / "assets/map.css").read_bytes(), compresslevel=9, mtime=0)
    )
    assert bundle["font_bytes"] == len((client / "assets/brand.woff2").read_bytes())
    assert bundle["image_bytes"] == len((client / "assets/logo.png").read_bytes())
    assert bundle["server_js_bytes"] == len((dist / "server/index.js").read_bytes())
    assert bundle["deployment_metadata_bytes"] == len(
        (dist / ".openai/hosting.json").read_bytes()
    )
    assert bundle["unclassified_files"] == []
    assert bundle["unclassified_bytes"] == 0
    assert {row["name"] for row in bundle["assets"]} == {
        path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()
    }


def test_frontend_bundle_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Vite manifest is missing"):
        _frontend_bundle(tmp_path / "dist")


def test_frontend_bundle_rejects_unclassified_emitted_javascript(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client, include_orphan=True)

    with pytest.raises(ValueError, match="classification mismatch"):
        _frontend_bundle(dist)


@pytest.mark.parametrize("relative", ["server/index.js", ".openai/hosting.json"])
def test_frontend_bundle_rejects_omitted_runtime_artifact(
    tmp_path: Path, relative: str
) -> None:
    dist = tmp_path / "dist"
    _write_manifest_fixture(dist / "client")
    (dist / relative).unlink()

    with pytest.raises(ValueError, match="missing required server/hosting artifacts"):
        _frontend_bundle(dist)


def test_frontend_surface_recomputes_complete_report(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["visual_matrix_pass_rate"] == 1.0
    assert result["map_list_parity"] is True
    assert result["worst_profile_p75"] == {
        "lcp_ms": 1000.0,
        "cls": 0.01,
        "inp_interaction_proxy_ms": 100.0,
        "map_ready_after_interaction_ms": 500.0,
    }
    assert result["qualified"] is report["summary"]["qualified"]


def test_frontend_surface_accepts_real_failing_map_roster(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(
        tmp_path, truncate_live_list=True
    )

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["map_list_parity"] is False
    assert result["visual_matrix_pass_rate"] == 27 / 30
    assert result["qualified"] is False


def test_frontend_surface_gates_moderate_wcag_a_aa_finding(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    row = report["surface_rows"][0]
    row["axe"] = {
        "engine_version": "4.12.1",
        "installed_package_version": "4.12.1",
        "engine_version_matches_installed_package": True,
        "finding_count": 1,
        "impact_counts": {
            "critical": 0,
            "serious": 0,
            "moderate": 1,
            "minor": 0,
            "unknown": 0,
        },
        "findings": [
            {
                "id": "color-contrast",
                "impact": "moderate",
                "tags": ["wcag2aa"],
                "help": "Elements must meet minimum color contrast ratio thresholds",
                "help_url": "https://dequeuniversity.com/rules/axe/color-contrast",
                "nodes": [
                    {
                        "target": [".secondary-copy"],
                        "failure_summary": "Contrast is below the required threshold.",
                    }
                ],
            }
        ],
    }
    row["checks"]["axe_wcag_a_aa_findings_within_limit"] = False
    row["qualified"] = False
    report["summary"]["qualified_surface_rows"] = 29
    report["summary"]["qualified"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["axe_wcag_a_aa_finding_count"] == 1
    assert result["visual_matrix_pass_rate"] == 29 / 30


def test_frontend_surface_accepts_but_fails_unallowlisted_request(
    tmp_path: Path,
) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    row = report["surface_rows"][0]
    event = {
        "sequence_index": len(row["runtime"]["request_events"]),
        "method": "GET",
        "url": "https://unexpected.example.test/failure",
        "origin": "https://unexpected.example.test",
        "resource_type": "image",
        "response_status": None,
        "failure": "net::ERR_FAILED",
    }
    row["runtime"]["request_events"].append(event)
    row["runtime"]["request_derived"] = {
        "request_origins": [
            "http://127.0.0.1:4175",
            "https://unexpected.example.test",
        ],
        "unexpected_request_origins": ["https://unexpected.example.test"],
        "failed_requests": [event],
        "unallowlisted_failed_requests": [event],
        "stylesheet_load_failures": [],
        "direct_third_party_tile_requests": [],
    }
    row["checks"]["request_origins_allowed"] = False
    row["checks"]["no_unallowlisted_failed_requests"] = False
    row["qualified"] = False
    report["summary"]["qualified_surface_rows"] = 29
    report["summary"]["qualified"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["runtime_violation_count"] == 2
    assert result["visual_matrix_pass_rate"] == 29 / 30


@pytest.mark.parametrize(
    "mutation",
    [
        "unexpected_top_key",
        "surface_roster_order",
        "summary_aggregate",
        "screenshot_digest",
        "performance_sample",
        "performance_p75",
        "environment_identity",
        "build_identity",
        "map_parity_aggregate",
        "map_dom_partition",
        "map_canonical_detail",
        "marker_placement_aggregate",
        "runtime_derived",
        "console_blank_url",
        "axe_version",
        "axe_impact_aggregate",
        "privacy_derived",
        "privacy_request_body_digest",
    ],
)
def test_frontend_surface_rejects_tampered_evidence(tmp_path: Path, mutation: str) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    if mutation == "unexpected_top_key":
        report["synthetic_override"] = True
    elif mutation == "surface_roster_order":
        report["surface_rows"][0], report["surface_rows"][1] = (
            report["surface_rows"][1],
            report["surface_rows"][0],
        )
    elif mutation == "summary_aggregate":
        report["summary"]["qualified_surface_rows"] = 0
    elif mutation == "screenshot_digest":
        report["surface_rows"][0]["screenshot"]["sha256"] = "f" * 64
    elif mutation == "performance_sample":
        report["performance"]["profiles"][0]["samples"].pop()
    elif mutation == "performance_p75":
        report["performance"]["profiles"][0]["cold_p75"]["lcp_ms"] = 1.0
    elif mutation == "environment_identity":
        report["execution_environment"]["os"]["cpu_model"] = "Different CPU"
    elif mutation == "build_identity":
        report["build"]["manifest_sha256"] = "f" * 64
    elif mutation == "map_parity_aggregate":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["map_list_parity"] = False
    elif mutation == "map_dom_partition":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["rendered_accessible_list_records"][0]["dom_index"] = 4
    elif mutation == "map_canonical_detail":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["rendered_accessible_list_records"][0][
            "rendered_source_url"
        ] = "https://example.test/wrong"
    elif mutation == "marker_placement_aggregate":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["marker_placement_sanity"]["observed_visible_marker_count"] = 0
    elif mutation == "runtime_derived":
        report["surface_rows"][0]["runtime"]["request_derived"]["request_origins"] = []
    elif mutation == "console_blank_url":
        provider_row = next(
            row for row in report["surface_rows"] if row["state_id"] == "provider_failure"
        )
        provider_row["runtime"]["console_errors"][0]["location"]["url"] = ""
    elif mutation == "axe_version":
        report["surface_rows"][0]["axe"]["installed_package_version"] = "4.11.0"
    elif mutation == "axe_impact_aggregate":
        report["surface_rows"][0]["axe"]["impact_counts"]["moderate"] = 1
    elif mutation == "privacy_derived":
        privacy = next(
            row
            for row in report["functional_journeys"]
            if row["id"] == "location_privacy_boundary"
        )
        privacy["evidence"]["derived"]["url_history_clean"] = False
    elif mutation == "privacy_request_body_digest":
        privacy = next(
            row
            for row in report["functional_journeys"]
            if row["id"] == "location_privacy_boundary"
        )
        privacy["evidence"]["api_request_roster"][0]["body_sha256"] = "f" * 64
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


def test_frontend_surface_rejects_missing_screenshot_file(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    (report_path.parent / report["surface_rows"][0]["screenshot"]["path"]).unlink()

    with pytest.raises(ValueError, match="screenshot file is missing"):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


def test_frontend_surface_accepts_bounded_full_page_screenshot(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    screenshot = report["surface_rows"][0]["screenshot"]
    screenshot_path = report_path.parent / screenshot["path"]
    Image.new("RGB", (390, 1688), (0, 0, 0)).save(screenshot_path, format="PNG")
    screenshot["bytes"] = screenshot_path.stat().st_size
    screenshot["sha256"] = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    screenshot["height_px"] = 1688
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["visual_matrix_pass_rate"] == 1.0


@pytest.mark.parametrize(
    "mutation", ["invalid_png", "wrong_dimensions", "absurd_height", "symlink"]
)
def test_frontend_surface_rejects_ineligible_screenshot_artifact(
    tmp_path: Path, mutation: str
) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    screenshot = report["surface_rows"][0]["screenshot"]
    screenshot_path = report_path.parent / screenshot["path"]
    if mutation == "invalid_png":
        screenshot_path.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"truncated")
    elif mutation == "wrong_dimensions":
        Image.new("RGB", (2, 2), (0, 0, 0)).save(screenshot_path, format="PNG")
        screenshot["width_px"] = 2
        screenshot["height_px"] = 2
    elif mutation == "absurd_height":
        Image.new("RGB", (390, 844 * 21), (0, 0, 0)).save(screenshot_path, format="PNG")
        screenshot["height_px"] = 844 * 21
    else:
        target = tmp_path / "external.png"
        Image.new("RGB", (390, 844), (0, 0, 0)).save(target, format="PNG")
        screenshot_path.unlink()
        screenshot_path.symlink_to(target)
    screenshot["bytes"] = screenshot_path.stat().st_size
    screenshot["sha256"] = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="screenshot"):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


def test_capture_owned_frontend_run_discards_external_synthetic_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "benchmark"
    stale_directory = output_dir / "frontend_surface"
    stale_directory.mkdir(parents=True)
    stale_report = stale_directory / "report.json"
    stale_report.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-01T00:00:00+00:00",
                "summary": {"qualified": True},
                "external_synthetic": True,
            }
        ),
        encoding="utf-8",
    )
    (stale_directory / "stale.png").write_bytes(b"synthetic")

    def run_fresh(command: list[str], log_path: Path) -> dict:
        assert not stale_directory.exists()
        assert command[-2:] == ["--output-dir", str(stale_directory)]
        stale_directory.mkdir()
        stale_report.write_text(
            json.dumps(
                {
                    "generated_at": upgrade_benchmark.datetime.now(
                        upgrade_benchmark.UTC
                    ).isoformat()
                }
            ),
            encoding="utf-8",
        )
        return {"exit_code": 2, "passed": False, "log_path": str(log_path)}

    monkeypatch.setattr(upgrade_benchmark, "_run_logged", run_fresh)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_frontend_bundle",
        lambda: {"manifest_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_frontend_surface",
        lambda *args, **kwargs: {"qualified": False},
    )

    result = _capture_frontend_surface(
        output_dir=output_dir,
        expected_commit="a" * 40,
        expected_environment={},
    )

    assert result["run"]["exit_code"] == 2
    assert not (stale_directory / "stale.png").exists()
    assert "external_synthetic" not in json.loads(stale_report.read_text(encoding="utf-8"))


def test_capture_owned_frontend_run_rejects_stale_generated_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "benchmark"

    def write_stale(command: list[str], log_path: Path) -> dict:
        report_path = Path(command[-1]) / "report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(
            json.dumps({"generated_at": "2026-08-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        return {"exit_code": 2, "passed": False, "log_path": str(log_path)}

    monkeypatch.setattr(upgrade_benchmark, "_run_logged", write_stale)

    with pytest.raises(ValueError, match="current capture-owned run"):
        _capture_frontend_surface(
            output_dir=output_dir,
            expected_commit="a" * 40,
            expected_environment={},
        )


def test_cpu_identity_prefers_the_same_node_source_as_frontend_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upgrade_benchmark.platform, "processor", lambda: "arm")
    monkeypatch.setattr(
        upgrade_benchmark,
        "_command_version",
        lambda command: "Apple M5" if command[0] == "node" else "unavailable",
    )

    assert upgrade_benchmark._cpu_model() == "Apple M5"


def test_comparison_fails_closed_on_changed_frozen_inputs() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["identity"]["identity_input_sha256"] = {"dataset.yaml": "d" * 64}

    with pytest.raises(ValueError, match="different frozen evaluation inputs"):
        compare_snapshots(before, after, spec)


def test_comparison_fails_closed_on_changed_harness_hashes() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["identity"]["harness_input_sha256"] = {"harness.py": "d" * 64}

    with pytest.raises(ValueError, match="different benchmark harnesses"):
        compare_snapshots(before, after, spec)


def test_comparison_gate_requires_the_same_execution_environment() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after_environment = dict(after["identity"]["execution_environment"])
    after_environment["node_version"] = "v24.0.0"
    after["identity"]["execution_environment"] = after_environment

    comparison = compare_snapshots(before, after, spec)

    environment = comparison["comparability"]["execution_environment"]
    assert environment["passed"] is False
    assert environment["differing_fields"] == ["node_version"]
    assert comparison["summary"]["comparability_failures"] == ["execution_environment"]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_comparison_gate_requires_complete_environment_identity() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    before["identity"].pop("execution_environment")

    comparison = compare_snapshots(before, after, spec)

    assert comparison["comparability"]["execution_environment"]["passed"] is False
    assert "execution_environment" in comparison["summary"]["comparability_failures"]


def test_comparison_gate_rejects_placeholder_environment_identity() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    for snapshot in (before, after):
        environment = dict(snapshot["identity"]["execution_environment"])
        environment["npm_version"] = "unavailable"
        snapshot["identity"]["execution_environment"] = environment

    comparison = compare_snapshots(before, after, spec)

    environment = comparison["comparability"]["execution_environment"]
    assert environment["passed"] is False
    assert environment["differing_fields"] == []
    assert any("invalid" in issue for issue in environment["issues"])


def test_ux_sampling_share_delta_boundary_is_inclusive() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(before, "ux_participant_count", 20)
    _set_snapshot_metric(after, "ux_participant_count", 20)
    common = {
        "status": "complete",
        "participant_count": 20,
        "access_method_counts": {
            "keyboard": 1,
            "pointer": 18,
            "screen_reader": 1,
        },
        "access_method_shares": {
            "keyboard": 0.05,
            "pointer": 0.9,
            "screen_reader": 0.05,
        },
    }
    before["ux"] = {
        **before["ux"],
        **common,
        "cohort_counts": {"novice_bc_resident": 10, "wildfire_aware": 10},
        "cohort_shares": {"novice_bc_resident": 0.5, "wildfire_aware": 0.5},
        "device_class_counts": {"desktop": 10, "mobile": 10},
        "device_class_shares": {"desktop": 0.5, "mobile": 0.5},
    }
    after["ux"] = {
        **after["ux"],
        **common,
        "cohort_counts": {"novice_bc_resident": 13, "wildfire_aware": 7},
        "cohort_shares": {"novice_bc_resident": 0.65, "wildfire_aware": 0.35},
        "device_class_counts": {"desktop": 7, "mobile": 13},
        "device_class_shares": {"desktop": 0.35, "mobile": 0.65},
    }

    comparison = compare_snapshots(before, after, spec)

    sampling = comparison["comparability"]["ux_sampling"]
    assert sampling["maximum_observed_share_delta"] == pytest.approx(0.15)
    assert sampling["passed"] is True
    assert comparison["summary"]["benchmark_gate_passed"] is True


def test_ux_sampling_distribution_shift_fails_the_comparison_gate() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(after, "ux_participant_count", 12)
    after["ux"] = {
        **after["ux"],
        "cohort_counts": {"novice_bc_resident": 4, "wildfire_aware": 8},
        "cohort_shares": {"novice_bc_resident": 1 / 3, "wildfire_aware": 2 / 3},
        "device_class_counts": {"desktop": 6, "mobile": 6},
        "device_class_shares": {"desktop": 0.5, "mobile": 0.5},
        "access_method_counts": {
            "keyboard": 1,
            "pointer": 10,
            "screen_reader": 1,
        },
        "access_method_shares": {
            "keyboard": 1 / 12,
            "pointer": 10 / 12,
            "screen_reader": 1 / 12,
        },
        "participant_count": 12,
    }

    comparison = compare_snapshots(before, after, spec)

    sampling = comparison["comparability"]["ux_sampling"]
    assert sampling["passed"] is False
    assert sampling["maximum_observed_share_delta"] == pytest.approx(1 / 6)
    assert comparison["summary"]["comparability_failures"] == ["ux_sampling"]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_hard_probe_parser_accepts_the_complete_qualified_protocol() -> None:
    parsed = _hard_probe(_hard_probe_report(), expected_mode="qualified")

    assert parsed["status"] == "complete"
    assert parsed["executed"] == 105
    assert parsed["pass_rate"] == 1.0
    assert parsed["critical_failures"] == 0
    assert parsed["provider_boundary"] == "openrouter"


def test_hard_probe_parser_rejects_an_unknown_case_id() -> None:
    report = _hard_probe_report()
    report["results"][0]["id"] = "fabricated-case-id"

    with pytest.raises(ValueError, match="case IDs|dataset"):
        _hard_probe(report, expected_mode="qualified")


def test_hard_probe_parser_rejects_tampered_dataset_priority() -> None:
    report = _hard_probe_report()
    critical = next(row for row in report["results"] if row["priority"] == "CRITICAL")
    critical["priority"] = "LOW"

    with pytest.raises(ValueError, match="priorit|dataset"):
        _hard_probe(report, expected_mode="qualified")


def test_hard_probe_parser_rejects_wrong_boundary_and_incomplete_protocol() -> None:
    wrong_boundary = _hard_probe_report()
    wrong_boundary["manifest"]["provider_boundary"] = "offline_double"
    with pytest.raises(ValueError, match="wrong provider boundary"):
        _hard_probe(wrong_boundary, expected_mode="qualified")

    incomplete = _hard_probe_report()
    incomplete["results"].pop()
    incomplete["summary"].update({"executed": 104, "passed": 104})
    with pytest.raises(ValueError, match="exactly 105"):
        _hard_probe(incomplete, expected_mode="qualified")


def test_live_parser_accepts_the_frozen_protocol() -> None:
    parsed = _live(_live_report())

    assert parsed["status"] == "complete"
    assert parsed["qualified"] is True
    assert parsed["cached_p95_ms"] == 25.0
    assert parsed["chat_map_records_match"] is True


def test_live_parser_requires_the_exact_canonical_checks() -> None:
    report = _live_report()
    report["checks"].pop("metadata_complete")

    with pytest.raises(ValueError, match="canonical|checks"):
        _live(report)


def test_live_parser_rejects_incomplete_or_inconsistent_reports() -> None:
    incomplete = _live_report()
    incomplete["cached_api"]["request_count"] = 25
    with pytest.raises(ValueError, match="frozen 26"):
        _live(incomplete)

    inconsistent = _live_report()
    inconsistent["qualified"] = False
    with pytest.raises(ValueError, match="differs from raw"):
        _live(inconsistent)


def test_live_parser_recomputes_roster_latency_metadata_and_digests() -> None:
    wrong_roster = _live_report()
    wrong_roster["cached_api"]["requests"][1]["request_id"] = "cached-5-99"
    with pytest.raises(ValueError, match="request ID|roster"):
        _live(wrong_roster)

    wrong_p95 = _live_report()
    wrong_p95["cached_api"]["requests"][-2]["latency_ms"] = 9_000.0
    with pytest.raises(ValueError, match="p95 differs"):
        _live(wrong_p95)

    wrong_cold_count = _live_report()
    wrong_cold_count["cold"]["records"].pop()
    with pytest.raises(ValueError, match="result_count differs"):
        _live(wrong_cold_count)

    wrong_digest = _live_report()
    wrong_digest["chat_map"]["map_records_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest differs"):
        _live(wrong_digest)

    wrong_near_me_page = _live_report()
    wrong_near_me_page["near_me"]["pagination"]["returned_results"] = 0
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_near_me_page)

    missing_near_me_fallback = _live_report()
    missing_near_me_fallback["near_me"]["official_fallback_urls"] = []
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(missing_near_me_fallback)


def test_live_parser_rejects_raw_check_and_cost_mutations() -> None:
    wrong_availability = _live_report()
    wrong_availability["cold"]["unavailable_layers"] = ["incident"]
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_availability)

    wrong_check = _live_report()
    wrong_check["checks"]["metadata_complete"] = False
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_check)

    injected_cost = _live_report()
    injected_cost["reported_cost_usd"] = 0.0
    with pytest.raises(ValueError, match="canonical schema"):
        _live(injected_cost)


def test_sealed_parser_accepts_a_complete_required_after_only_report() -> None:
    parsed = _retrieval_qualification(_sealed_report())

    assert parsed["status"] == "complete"
    assert parsed["qualified"] is True
    assert parsed["repetitions"] == 3
    assert parsed["min_recall_at_5"] == pytest.approx(46 / 47)


def test_development_retrieval_recomputes_aggregates_from_ranking_ids() -> None:
    report = _development_retrieval_report()
    parsed = _development_retrieval(report)

    assert parsed["case_count"] == 50
    assert parsed["recall_at_5"] == 1.0
    report["candidates"]["current"]["stages"]["reranked"]["recall"] = 0.5
    with pytest.raises(ValueError, match="differs from case-level rankings"):
        _development_retrieval(report)


def test_sealed_parser_rejects_tampered_case_level_ranking_aggregate() -> None:
    report = _sealed_report()
    report["repetition_reports"][0]["recall_at_5"] = 1.0

    with pytest.raises(ValueError, match="differs from case-level rankings"):
        _retrieval_qualification(report)


def test_sealed_parser_rejects_unknown_or_duplicate_ranking_ids() -> None:
    unknown = _sealed_report()
    unknown["repetition_reports"][0]["rows"][0]["reranked_chunk_ids"] = ["invented-chunk"]
    with pytest.raises(ValueError, match="unknown ranking IDs"):
        _retrieval_qualification(unknown)

    duplicate = _sealed_report()
    ranking = duplicate["repetition_reports"][0]["rows"][1]["reranked_chunk_ids"]
    duplicate["repetition_reports"][0]["rows"][1]["reranked_chunk_ids"] = ranking * 2
    with pytest.raises(ValueError, match="repeats ranking IDs"):
        _retrieval_qualification(duplicate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tuning_allowed", True),
        ("relevance_addendum_used", True),
        ("cost_budget_exceeded", True),
        ("reported_cost_usd", 0.76),
    ],
)
def test_sealed_parser_rejects_protocol_or_budget_violations(field: str, value: object) -> None:
    report = _sealed_report()
    report[field] = value

    with pytest.raises(ValueError):
        _retrieval_qualification(report)


def test_semantic_holdout_recomputes_canonical_double_review() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["status"] == "complete"
    assert parsed["summary_version"] == "firelens_semantic_holdout_summary.v3"
    assert parsed["case_count"] == 25
    assert parsed["claim_count"] == 25
    assert parsed["independent_review_count"] == 50
    assert parsed["approved_case_count"] == 25
    assert parsed["reviewers"] == ["Domain Expert A", "Domain Expert B"]
    assert parsed["adjudicator"] == "Domain Adjudicator"
    assert parsed["claim_label_agreement_rate"] == 1.0
    assert parsed["claim_label_cohens_kappa"] == 1.0
    assert parsed["qualified"] is True
    assert parsed["unsupported_or_unclear"] == 0
    assert parsed["dangerous_omission_count"] == 0
    assert parsed["presentation_event_count"] == 75
    assert parsed["development_registry_sha256"] == "4" * 64


def test_semantic_holdout_validates_actual_artifact_hash_chain_and_optional_summary(
    tmp_path: Path,
) -> None:
    (
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    ) = _write_semantic_holdout_evidence(tmp_path, include_summary=True)

    parsed = validate_semantic_holdout(
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    )

    assert parsed["candidate_report_sha256"] == upgrade_benchmark.file_sha256(report_path)
    assert parsed["review_bundle_sha256"] == upgrade_benchmark.file_sha256(bundle_path)
    assert parsed["dataset_manifest_sha256"] == upgrade_benchmark.file_sha256(manifest_path)
    assert parsed["development_registry_sha256"] == upgrade_benchmark.file_sha256(
        development_registry_path
    )
    assert parsed["qualified"] is True


def test_semantic_holdout_rejects_candidate_report_tampered_after_review(
    tmp_path: Path,
) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["cases"][0]["response"] = "Substituted response."
    report["cases"][0]["response_sha256"] = hashlib.sha256(
        report["cases"][0]["response"].encode()
    ).hexdigest()
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the candidate report"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_rejects_manifest_roster_tampering(tmp_path: Path) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["case_roster"][0]["input_sha256"] = "a" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="case-roster digest"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_recomputes_source_and_family_disjointness() -> None:
    development_registry = _semantic_development_registry_payload()
    manifest = _semantic_holdout_manifest_payload()

    parsed = upgrade_benchmark._semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256="4" * 64,
    )

    assert parsed["disjointness_audit"]["source_overlap_id_sha256s"] == []
    assert parsed["disjointness_audit"]["question_family_overlap_ids"] == []


@pytest.mark.parametrize("overlap_kind", ["source", "question_family"])
def test_semantic_holdout_rejects_falsely_asserted_disjointness(
    overlap_kind: str,
) -> None:
    development_registry = _semantic_development_registry_payload()
    manifest = _semantic_holdout_manifest_payload()
    if overlap_kind == "source":
        manifest["case_roster"][0]["source_id_sha256s"] = [
            development_registry["source_id_sha256s"][0]
        ]
        source_roster = sorted(
            {source for row in manifest["case_roster"] for source in row["source_id_sha256s"]}
        )
        manifest["source_id_sha256s"] = source_roster
        manifest["source_roster_sha256"] = upgrade_benchmark._sha256_json(source_roster)
        manifest["disjointness_audit"]["holdout_source_roster_sha256"] = manifest[
            "source_roster_sha256"
        ]
        message = "source-overlap audit"
    else:
        manifest["case_roster"][0]["question_family_id"] = development_registry[
            "question_family_ids"
        ][0]
        family_roster = sorted({row["question_family_id"] for row in manifest["case_roster"]})
        manifest["question_family_ids"] = family_roster
        manifest["question_family_roster_sha256"] = upgrade_benchmark._sha256_json(
            family_roster
        )
        manifest["question_family_distribution"] = {
            family: sum(row["question_family_id"] == family for row in manifest["case_roster"])
            for family in family_roster
        }
        manifest["disjointness_audit"]["holdout_question_family_roster_sha256"] = manifest[
            "question_family_roster_sha256"
        ]
        message = "question-family-overlap audit"
    manifest["case_roster_sha256"] = upgrade_benchmark._sha256_json(manifest["case_roster"])

    with pytest.raises(ValueError, match=message):
        upgrade_benchmark._semantic_holdout_manifest_payload(
            manifest,
            development_registry=development_registry,
            development_registry_sha256="4" * 64,
        )


def test_semantic_holdout_rejects_rewritten_development_registry(tmp_path: Path) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    development_registry = json.loads(development_registry_path.read_text(encoding="utf-8"))
    development_registry["frozen_at"] = "2026-08-06T08:01:00+00:00"
    development_registry_path.write_text(
        json.dumps(development_registry, indent=2), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not bind the development registry"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_rejects_broken_presentation_hash_chain() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    event = bundle["presentation_log"]["events"][0]
    event["presented_at"] = "2026-08-06T10:01:00.500000+00:00"
    event["event_sha256"] = upgrade_benchmark._semantic_presentation_event_sha256(event)

    with pytest.raises(ValueError, match="presentation hash chain is broken"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_review_without_matching_presentation() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["cases"][0]["independent_reviews"][0]["presentation_event_sha256"] = "a" * 64

    with pytest.raises(ValueError, match="review is not bound to its presentation"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_incomplete_presentation_exposure_roster() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["presentation_log"]["events"].pop()
    bundle["presentation_log"]["event_count"] -= 1

    with pytest.raises(ValueError, match="incomplete event roster"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_candidate_identity_as_blinded_label() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["presentation"]["blinded_candidate_label"] = report["candidate_id"]

    with pytest.raises(ValueError, match="exposes the candidate identity"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("candidate_identity", "candidate identity"),
        ("unblinded", "requires candidate_identity_blinded"),
        ("unrandomized", "requires randomized"),
        ("presentation_roster", "actor presentation order"),
        ("duplicate_reviewers", "reviewer IDs must be unique"),
        ("late_review", "adjudicated before reviews"),
        ("unlocked_reviews", "reviewer decisions were not locked"),
        ("changed_review_after_lock", "independent-review digest"),
        ("missing_claim_label", "every exact claim"),
        ("unresolved", "remains unresolved"),
        ("wrong_adjudicator", "wrong adjudicator"),
    ],
)
def test_semantic_holdout_rejects_protocol_and_adjudication_mutations(
    mutation: str, message: str
) -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    case = bundle["cases"][0]
    if mutation == "candidate_identity":
        report["candidate_id"] = "substituted-candidate"
    elif mutation == "unblinded":
        bundle["presentation"]["candidate_identity_blinded"] = False
    elif mutation == "unrandomized":
        bundle["presentation"]["randomized"] = False
    elif mutation == "presentation_roster":
        bundle["presentation"]["actor_orders"][0]["case_ids"][0] = "unknown-case"
    elif mutation == "duplicate_reviewers":
        bundle["reviewer_registry"][1]["reviewer_id"] = "reviewer-a"
    elif mutation == "late_review":
        case["independent_reviews"][1]["reviewed_at"] = "2026-08-06T12:30:00+00:00"
        case["adjudication"]["independent_reviews_sha256"] = upgrade_benchmark._sha256_json(
            case["independent_reviews"]
        )
    elif mutation == "unlocked_reviews":
        case["adjudication"]["reviewer_decisions_locked"] = False
    elif mutation == "changed_review_after_lock":
        case["independent_reviews"][0]["claim_labels"][0]["label"] = "unclear"
        case["independent_reviews"][0]["case_decision"] = "rejected"
    elif mutation == "missing_claim_label":
        case["independent_reviews"][0]["claim_labels"] = []
        case["adjudication"]["independent_reviews_sha256"] = upgrade_benchmark._sha256_json(
            case["independent_reviews"]
        )
    elif mutation == "unresolved":
        case["adjudication"]["resolution_status"] = "unresolved"
    else:
        case["adjudication"]["adjudicator_id"] = "someone-else"

    with pytest.raises(ValueError, match=message):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


@pytest.mark.parametrize("final_label", ["unsupported", "unclear"])
def test_semantic_holdout_recomputes_failed_claim_findings(final_label: str) -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    adjudication = bundle["cases"][0]["adjudication"]
    adjudication["claim_labels"][0]["label"] = final_label
    adjudication["case_decision"] = "rejected"

    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["approved_case_count"] == 24
    assert parsed["unsupported_or_unclear"] == 1
    assert parsed["qualified"] is False


def test_semantic_holdout_recomputes_dangerous_omission_failure() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    adjudication = bundle["cases"][0]["adjudication"]
    adjudication["dangerous_omission"] = True
    adjudication["case_decision"] = "rejected"

    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["approved_case_count"] == 24
    assert parsed["dangerous_omission_count"] == 1
    assert parsed["qualified"] is False


def test_semantic_holdout_rejects_summary_that_differs_from_recomputation() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    recomputed = _validate_semantic_holdout_payloads(manifest, report, bundle)
    summary = {key: value for key, value in recomputed.items() if key != "status"}
    summary["approved_case_count"] = 24

    with pytest.raises(ValueError, match="summary differs from raw validated evidence"):
        _validate_semantic_holdout_payloads(manifest, report, bundle, summary)


def test_semantic_holdout_rejects_noncanonical_extra_fields() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    report["copied_aggregate"] = {"qualified": True}

    with pytest.raises(ValueError, match="canonical schema"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_ux_parser_accepts_complete_accessible_task_coverage() -> None:
    parsed = _ux(_ux_report(), load_spec(SPEC_PATH))

    assert parsed["status"] == "complete"
    assert parsed["participant_count"] == 12
    assert parsed["attempts"] == 60
    assert parsed["task_completion_rate"] == 1.0
    assert parsed["accessibility_coverage"] is True
    assert parsed["cohort_counts"] == {
        "novice_bc_resident": 4,
        "wildfire_aware": 8,
    }
    assert parsed["device_class_shares"] == {"desktop": 0.5, "mobile": 0.5}
    assert parsed["access_method_counts"] == {
        "keyboard": 1,
        "pointer": 6,
        "screen_reader": 1,
        "touch": 6,
    }
    assert parsed["completion_by_cohort"] == {
        "novice_bc_resident": 1.0,
        "wildfire_aware": 1.0,
    }
    assert parsed["completion_by_device_class"] == {"desktop": 1.0, "mobile": 1.0}
    assert parsed["completion_by_access_method"] == {
        "keyboard": 1.0,
        "pointer": 1.0,
        "screen_reader": 1.0,
        "touch": 1.0,
    }
    assert parsed["worst_core_cohort_completion_rate"] == 1.0
    assert parsed["worst_device_class_completion_rate"] == 1.0
    assert parsed["completion_wilson_95ci"]["lower"] < 1.0
    assert parsed["bootstrap"]["resamples"] == 2_000


def test_ux_template_is_reviewer_ready_without_fabricated_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "ux.template.yaml"
    upgrade_benchmark._write_ux_template(path, "before", load_spec(SPEC_PATH))
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert payload["participant_count"] == 12
    assert len(payload["participants"]) == 12
    assert len(payload["attempts"]) == 60
    assert {row["cohort"] for row in payload["participants"]} == {
        "novice_bc_resident",
        "wildfire_aware",
    }
    assert {row["device_class"] for row in payload["participants"]} == {
        "desktop",
        "mobile",
    }
    assert {"keyboard", "screen_reader"}.issubset(
        {method for row in payload["participants"] for method in row["access_methods"]}
    )
    assert all(
        all(value is None for value in row["criterion_results"].values())
        for row in payload["attempts"]
    )
    assert all(row["observed_outcome"] == "" for row in payload["attempts"])

    payload["commit"] = "a" * 40
    payload["deployment_id"] = "local-before"
    payload["moderator"] = "Morgan Lee"
    payload["observed_at"] = "2026-08-08T12:00:00+00:00"
    with pytest.raises(ValueError, match="strict booleans"):
        _ux(payload, load_spec(SPEC_PATH))


def test_ux_parser_rejects_an_eleven_person_pilot_even_with_a_constraint_note() -> None:
    report = _ux_report()
    removed_id = report["participants"].pop()["participant_id"]
    report["attempts"] = [
        row for row in report["attempts"] if row["participant_id"] != removed_id
    ]
    report["participant_count"] = 11
    report["recruitment_constraint"] = "One participant was unavailable."

    with pytest.raises(ValueError, match="at least 12"):
        _ux(report, load_spec(SPEC_PATH))

    participant_metric = next(
        metric
        for metric in load_spec(SPEC_PATH).comparison_metrics
        if metric.key == "ux_participant_count"
    )
    assert participant_metric.gate_value == 12


def test_ux_parser_requires_every_participant_task_pair() -> None:
    report = _ux_report()
    report["attempts"].pop()

    with pytest.raises(ValueError, match="every UX participant"):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_binds_the_report_to_the_frozen_task_wording() -> None:
    report = _ux_report()
    report["task_reference"][0]["name"] = "A substituted task"

    with pytest.raises(ValueError, match="task reference|frozen task"):
        _ux(report, load_spec(SPEC_PATH))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("moderator", "UX Researcher", "named human"),
        ("commit", "short-sha", "full lowercase Git SHA"),
        ("deployment_id", "", "deployment ID"),
        ("observed_at", "not-a-timestamp", "timestamp"),
    ],
)
def test_ux_parser_requires_attributable_exact_candidate_evidence(
    field: str, value: str, message: str
) -> None:
    report = _ux_report()
    report[field] = value

    with pytest.raises(ValueError, match=message):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_rejects_hidden_or_task_inapplicable_fields() -> None:
    report = _ux_report()
    report["copied_summary"] = {"task_completion_rate": 1.0}
    with pytest.raises(ValueError, match="canonical schema"):
        _ux(report, load_spec(SPEC_PATH))

    report = _ux_report()
    report["attempts"][2]["copied_completion"] = True
    with pytest.raises(ValueError, match="canonical schema"):
        _ux(report, load_spec(SPEC_PATH))


@pytest.mark.parametrize(
    ("participant_index", "field", "value", "message"),
    [
        (3, "cohort", "wildfire_aware", "four participants"),
        (0, "access_methods", ["touch"], "keyboard and screen-reader"),
    ],
)
def test_ux_parser_rejects_inadequate_sampling_coverage(
    participant_index: int, field: str, value: str, message: str
) -> None:
    report = _ux_report()
    report["participants"][participant_index][field] = value

    with pytest.raises(ValueError, match=message):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_requires_three_participants_per_core_device_class() -> None:
    report = _ux_report()
    report["participants"][4]["device_class"] = "desktop"
    report["participants"][6]["device_class"] = "desktop"
    report["participants"][8]["device_class"] = "desktop"
    report["participants"][10]["device_class"] = "desktop"

    with pytest.raises(ValueError, match="three mobile"):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_completion_is_derived_and_unsuccessful_near_me_uses_task_cap() -> None:
    report = _ux_report()
    for row in report["attempts"]:
        if row["task_id"] == "UX02":
            row["criterion_results"]["UX02-C01"] = False
            row["duration_seconds"] = 1.0

    parsed = _ux(report, load_spec(SPEC_PATH))

    assert parsed["completed"] == 48
    assert parsed["task_completion_rate"] == 0.8
    assert parsed["completion_by_task"]["UX02"] == 0.0
    assert parsed["near_me_median_seconds"] == 120.0


def test_ux_critical_error_codes_override_completed_criteria() -> None:
    report = _ux_report()
    row = report["attempts"][0]
    row["critical_error_codes"] = ["UX01-E01"]
    row["critical_error_notes"] = {
        "UX01-E01": "Participant treated unsupported wording as source-backed."
    }

    parsed = _ux(report, load_spec(SPEC_PATH))

    assert parsed["critical_error_count"] == 1
    assert parsed["completed"] == 59


def test_ux_comparison_reports_seeded_independent_cohort_effect_intervals() -> None:
    spec = load_spec(SPEC_PATH)
    before = _ux(_ux_report(), spec)
    after_report = _ux_report()
    after_report["label"] = "after"
    after_report["commit"] = "b" * 40
    for row in after_report["attempts"]:
        if row["task_id"] == "UX02":
            row["duration_seconds"] = 15.0
    after = _ux(after_report, spec)

    comparison = upgrade_benchmark._ux_distribution_comparability(before, after)
    effects = comparison["effect_intervals"]

    assert comparison["passed"] is True
    assert effects["status"] == "complete"
    assert effects["resamples"] == 5_000
    assert effects["near_me_improvement_established"] is True
    assert effects["near_me_seconds_improvement_95ci"] == {"lower": 15.0, "upper": 15.0}


def test_preview_parser_accepts_exact_canonical_evidence() -> None:
    parsed = _preview(_preview_report())

    assert parsed == {
        "status": "complete",
        "commit": "a" * 40,
        "deployment_id": "preview-1",
        "qualified": True,
        "checks": _preview_report()["checks"],
    }


def test_preview_parser_rejects_extra_checks_or_missing_deployment_identity() -> None:
    extra_check = _preview_report()
    extra_check["checks"]["self_attested_only"] = True
    with pytest.raises(ValueError, match="canonical checks"):
        _preview(extra_check)

    missing_identity = _preview_report()
    missing_identity["observed"]["deployment_id"] = ""
    with pytest.raises(ValueError, match="deployment identity"):
        _preview(missing_identity)


def test_preview_parser_requires_https_and_all_eight_requests() -> None:
    insecure = _preview_report()
    insecure["base_url"] = "http://preview.example.test"
    with pytest.raises(ValueError, match="HTTPS"):
        _preview(insecure)

    incomplete = _preview_report()
    incomplete["requests"].pop()
    with pytest.raises(ValueError, match="eight canonical requests"):
        _preview(incomplete)


def test_preview_parser_recomputes_roster_status_identity_and_p95() -> None:
    changed_prompt = _preview_report()
    static = next(row for row in changed_prompt["requests"] if row["case_id"] == "static")
    static["request"]["question"] = "A substituted prompt"
    with pytest.raises(ValueError, match="roster|canonical"):
        _preview(changed_prompt)

    wrong_content_type = _preview_report()
    homepage = next(
        row for row in wrong_content_type["requests"] if row["case_id"] == "homepage"
    )
    homepage["response_content_type"] = "application/json"
    with pytest.raises(ValueError, match="content type"):
        _preview(wrong_content_type)

    wrong_identity = _preview_report()
    readiness = next(row for row in wrong_identity["requests"] if row["case_id"] == "readiness")
    readiness["response"]["build_commit"] = "b" * 40
    with pytest.raises(ValueError, match="differs from readiness evidence"):
        _preview(wrong_identity)

    wrong_p95 = _preview_report()
    live = next(row for row in wrong_p95["requests"] if row["case_id"] == "live")
    live["latency_ms"] = 9_000.0
    with pytest.raises(ValueError, match="p95 differs"):
        _preview(wrong_p95)


def test_preview_parser_rejects_response_count_hash_and_support_mutations() -> None:
    wrong_count = _preview_report()
    live = next(row for row in wrong_count["requests"] if row["case_id"] == "live")
    live["response"]["claim_count"] = 1
    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(wrong_count)

    malformed_body_digest = _preview_report()
    malformed_body_digest["requests"][0]["response_body_sha256"] = "not-a-digest"
    with pytest.raises(ValueError, match="SHA-256"):
        _preview(malformed_body_digest)

    wrong_support_digest = _preview_report()
    static = next(row for row in wrong_support_digest["requests"] if row["case_id"] == "static")
    static["response"]["exact_support"]["claims"][0]["supports"][0]["quote_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digests differ"):
        _preview(wrong_support_digest)

    wrong_support_offset = _preview_report()
    static = next(row for row in wrong_support_offset["requests"] if row["case_id"] == "static")
    static["response"]["exact_support"]["claims"][0]["supports"][0]["match_end"] += 1
    with pytest.raises(ValueError, match="offsets differ"):
        _preview(wrong_support_offset)


def test_preview_parser_rejects_summary_flag_and_cost_mutations() -> None:
    wrong_check = _preview_report()
    wrong_check["checks"]["static_grounded"] = False
    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(wrong_check)

    wrong_qualified = _preview_report()
    wrong_qualified["qualified"] = False
    with pytest.raises(ValueError, match="qualified flag differs"):
        _preview(wrong_qualified)

    injected_cost = _preview_report()
    injected_cost["reported_cost_usd"] = 0.0
    with pytest.raises(ValueError, match="canonical schema"):
        _preview(injected_cost)


def test_deployment_parser_accepts_cross_region_rate_limit_and_rollback_proof(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    parsed = _deployment(
        report,
        rate_limit_artifact=rate_limit_path,
        rollback_artifact=rollback_path,
    )

    assert parsed["status"] == "complete"
    assert parsed["distributed_rate_limit_verified"] is True
    assert parsed["rollback_rehearsal_passed"] is True
    assert parsed["candidate_deployment_id"] == "candidate-a"
    assert parsed["restored_deployment_id"] == "previous-a"


def test_deployment_parser_rejects_same_deployment_rollback(tmp_path: Path) -> None:
    report = _deployment_report()
    report["rollback_evidence"]["restored_deployment_id"] = "candidate-a"
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="distinct deployment"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_rejects_single_client_rate_limit_attestation(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    report["rate_limit_evidence"]["observations"][1]["client_id"] = "client-a"
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="rate-limit proof is incomplete"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_requires_raw_artifacts_for_positive_proof() -> None:
    with pytest.raises(ValueError, match="raw artifact is required"):
        _deployment(_deployment_report())


def test_deployment_parser_rejects_tampered_or_unbound_raw_artifacts(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    rate_limit_path.write_text('{"tampered": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="digest does not match"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )

    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    report["rate_limit_evidence"]["rule_id"] = "substituted-after-hash"
    with pytest.raises(ValueError, match="does not match embedded evidence"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_prerequisites_do_not_require_before_measurement_but_gate_after() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    prerequisite_keys = {
        metric.key
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "prerequisite"
    }
    for key in prerequisite_keys:
        _set_snapshot_metric(before, key, None)

    passing = compare_snapshots(before, after, spec)
    prerequisite_rows = [row for row in passing["metrics"] if row["key"] in prerequisite_keys]
    assert prerequisite_keys
    assert all(row["verdict"] == "prerequisite" for row in prerequisite_rows)
    assert passing["summary"]["missing_required_before"] == []
    assert passing["summary"]["benchmark_gate_passed"] is True

    missing_key = next(iter(prerequisite_keys))
    _set_snapshot_metric(after, missing_key, None)
    missing = compare_snapshots(before, after, spec)
    assert missing_key in missing["summary"]["missing_required_after"]
    assert missing["summary"]["benchmark_gate_passed"] is False


def test_relevant_untracked_paths_ignore_only_ephemeral_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade_benchmark,
        "_git",
        lambda *args: "\n".join(
            [
                ".agents/local-note.md",
                "output/benchmark.json",
                "scripts/untracked_runtime.py",
                "data/evaluation/untracked.yaml",
            ]
        ),
    )

    assert _relevant_untracked_paths() == [
        "data/evaluation/untracked.yaml",
        "scripts/untracked_runtime.py",
    ]


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


def test_before_snapshot_seal_binds_snapshot_and_all_frozen_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )

    assert seal["before_snapshot"]["sha256"] == upgrade_benchmark.file_sha256(before_path)
    assert seal["candidate_identity"]["commit"] == "baseline-commit"
    assert seal["spec_identity"]["sha256"] == upgrade_benchmark.file_sha256(spec_path)
    assert (
        seal["dataset_identity"]["identity_input_sha256"]
        == before["identity"]["identity_input_sha256"]
    )
    assert (
        seal["harness_identity"]["harness_input_sha256"]
        == before["identity"]["harness_input_sha256"]
    )
    _verify_before_snapshot_seal_payload(
        seal=seal,
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
    )


def test_before_snapshot_seal_rejects_metric_or_snapshot_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )
    before["metrics"]["offline_hard_probe_pass_rate"] = 0.5
    with pytest.raises(ValueError, match="diverges from its detailed evidence"):
        _verify_before_snapshot_seal_payload(
            seal=seal,
            before=before,
            before_path=before_path,
            spec=spec,
            spec_path=spec_path,
        )

    before["metrics"]["offline_hard_probe_pass_rate"] = before["hard_probe_offline"][
        "pass_rate"
    ]
    before_path.write_text(json.dumps({**before, "tampered": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the supplied snapshot"):
        _verify_before_snapshot_seal_payload(
            seal=seal,
            before=before,
            before_path=before_path,
            spec=spec,
            spec_path=spec_path,
        )


def test_before_snapshot_seal_must_be_tracked_and_unmodified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )
    seal_path = tmp_path / spec.before_snapshot_seal
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    monkeypatch.setattr(
        upgrade_benchmark, "_path_is_tracked_and_unmodified", lambda path: False
    )

    with pytest.raises(ValueError, match="must be tracked and unmodified"):
        upgrade_benchmark._verify_tracked_before_snapshot_seal(
            spec=spec,
            spec_path=spec_path,
            before_path=before_path,
        )


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


def test_before_snapshot_ancestry_accepts_exact_committed_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    seal_commit = _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)

    evidence = upgrade_benchmark._resolve_before_snapshot_ancestry(
        spec=spec,
        before={"identity": {"commit": before_commit}},
        after_commit=after_commit,
    )

    assert evidence == {
        "status": "verified",
        "seal_path": "data/before-seal.json",
        "seal_sha256": upgrade_benchmark.file_sha256(tmp_path / "data/before-seal.json"),
        "before_candidate_commit": before_commit,
        "seal_introducing_commit": seal_commit,
        "after_candidate_commit": after_commit,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }


def test_before_snapshot_ancestry_rejects_unrelated_before_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, baseline_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    baseline_tree = _repo_git(tmp_path, "rev-parse", f"{baseline_commit}^{{tree}}")
    unrelated_before = _repo_git(
        tmp_path,
        "commit-tree",
        baseline_tree,
        "-m",
        "unrelated baseline",
    )
    _commit_test_seal(tmp_path, unrelated_before)
    after_commit = _commit_after_candidate(tmp_path)

    with pytest.raises(ValueError, match="before snapshot candidate is not an ancestor"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": unrelated_before}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_abbreviated_commit_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    abbreviated = before_commit[:12]
    _commit_test_seal(tmp_path, abbreviated)
    after_commit = _commit_after_candidate(tmp_path)

    with pytest.raises(ValueError, match="exact full Git commit ID"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": abbreviated}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_seal_on_side_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _repo_git(tmp_path, "switch", "--quiet", "-c", "seal-side")
    _commit_test_seal(tmp_path, before_commit)
    _repo_git(tmp_path, "switch", "--quiet", "-c", "after-side", before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    _repo_git(tmp_path, "switch", "--quiet", "seal-side")

    with pytest.raises(ValueError, match="after candidate does not contain"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_after_candidate_before_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)

    with pytest.raises(ValueError, match="after candidate does not contain"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=before_commit,
        )


def test_before_snapshot_ancestry_rejects_missing_or_untracked_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    before = {"identity": {"commit": before_commit}}

    with pytest.raises(ValueError, match="seal is missing"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before=before,
            after_commit=before_commit,
        )

    seal_path = tmp_path / "data/before-seal.json"
    seal_path.parent.mkdir(parents=True)
    seal_path.write_text(
        json.dumps({"candidate_identity": {"commit": before_commit}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="is untracked"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before=before,
            after_commit=before_commit,
        )


def test_before_snapshot_ancestry_rejects_mutable_or_ambiguous_seal_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    seal_path = tmp_path / "data/before-seal.json"
    seal_path.write_text(
        json.dumps({"candidate_identity": {"commit": before_commit}, "tampered": True}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unstaged modifications"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    _repo_git(tmp_path, "add", "data/before-seal.json")
    with pytest.raises(ValueError, match="staged modifications"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    _repo_git(tmp_path, "commit", "--quiet", "-m", "rewrite seal")
    rewritten_after = _repo_git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="ambiguous or mutable history"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=rewritten_after,
        )


def test_before_snapshot_ancestry_rejects_shallow_or_failed_git_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    real_command = upgrade_benchmark._git_evidence_command

    def shallow_command(args: list[str], **kwargs: object) -> object:
        if args == ["rev-parse", "--is-shallow-repository"]:
            return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")
        return real_command(args, **kwargs)

    monkeypatch.setattr(upgrade_benchmark, "_git_evidence_command", shallow_command)
    with pytest.raises(ValueError, match="shallow repository"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    monkeypatch.setattr(upgrade_benchmark, "_git_evidence_command", real_command)

    real_run = upgrade_benchmark.subprocess.run

    def git_failure(*args: object, **kwargs: object) -> object:
        return subprocess.CompletedProcess(args, 128, stdout="", stderr="fatal: broken repo")

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", git_failure)
    with pytest.raises(ValueError, match="failed with exit 128"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", real_run)

    def git_os_error(*args: object, **kwargs: object) -> object:
        raise OSError("git unavailable")

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", git_os_error)
    with pytest.raises(ValueError, match="Git could not run"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )


def test_capture_rejects_dirty_worktree_before_running_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: True)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before clean preflight"),
    )

    with pytest.raises(ValueError, match="clean tracked worktree"):
        capture(SimpleNamespace(spec=SPEC_PATH))


def test_after_capture_requires_the_sealed_before_snapshot_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before seal preflight"),
    )

    with pytest.raises(ValueError, match="requires the sealed before snapshot"):
        capture(
            SimpleNamespace(
                spec=SPEC_PATH,
                label="after",
                before_snapshot=None,
                rate_limit_evidence=None,
                rollback_evidence=None,
            )
        )


def test_after_capture_rejects_invalid_seal_ancestry_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: {"identity": {"commit": "a" * 40}},
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "c" * 40)

    def reject_ancestry(**kwargs: object) -> object:
        raise ValueError("seal-introducing commit is not an ancestor")

    monkeypatch.setattr(upgrade_benchmark, "_resolve_before_snapshot_ancestry", reject_ancestry)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before ancestry preflight"),
    )

    with pytest.raises(ValueError, match="seal-introducing commit"):
        capture(
            SimpleNamespace(
                spec=SPEC_PATH,
                label="after",
                before_snapshot=Path("before.json"),
            )
        )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "semantic_holdout_report",
        "semantic_holdout_review_bundle",
        "semantic_holdout_summary",
        "frontend_manual_review_bundle",
        "preview_report",
        "deployment_report",
        "rate_limit_evidence",
        "rollback_evidence",
        "vercel_artifact_root",
        "vercel_artifact_id",
        "vercel_platform_root",
        "docker_artifact_root",
        "docker_artifact_id",
        "docker_platform_root",
    ],
)
def test_before_capture_rejects_required_after_only_evidence(
    forbidden_field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    args = {
        "spec": SPEC_PATH,
        "label": "before",
        "retrieval_qualification": None,
        "semantic_holdout_report": None,
        "semantic_holdout_review_bundle": None,
        "semantic_holdout_summary": None,
        "frontend_manual_review_bundle": None,
        "preview_report": None,
        "deployment_report": None,
        "rate_limit_evidence": None,
        "rollback_evidence": None,
        "vercel_artifact_root": None,
        "vercel_artifact_id": None,
        "vercel_platform_root": None,
        "docker_artifact_root": None,
        "docker_artifact_id": None,
        "docker_platform_root": None,
    }
    args[forbidden_field] = Path("evidence.json")

    with pytest.raises(ValueError, match="required-after-only"):
        capture(SimpleNamespace(**args))


def test_after_capture_requires_frontend_manual_review_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail(
            "capture command ran before manual-review preflight"
        ),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=None,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match="requires the frontend manual review bundle"):
        capture(args)


@pytest.mark.parametrize(
    ("review_kind", "message"),
    [
        ("semantic", "blind-review qualification manifest"),
        ("retrieval", "blind-review qualification manifest"),
    ],
)
def test_capture_refuses_legacy_human_review_without_blind_qualification_manifest(
    review_kind: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    semantic = review_kind == "semantic"
    retrieval = review_kind == "retrieval"
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="before",
        before_snapshot=None,
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=None,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        vercel_artifact_root=None,
        vercel_artifact_id=None,
        vercel_platform_root=None,
        docker_artifact_root=None,
        docker_artifact_id=None,
        docker_platform_root=None,
        semantic_report=Path("report.json") if semantic else None,
        semantic_review_sidecar=Path("review.yaml") if semantic else None,
        semantic_review_summary=Path("summary.json") if semantic else None,
        semantic_review_qualification=None,
        retrieval_review_sidecar=Path("review.yaml") if retrieval else None,
        retrieval_review_summary=Path("summary.json") if retrieval else None,
        retrieval_review_qualification=None,
    )

    with pytest.raises(ValueError, match=message):
        capture(args)


def test_after_capture_requires_capture_owned_runtime_artifacts_before_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "validate_frontend_manual_review",
        lambda *args, **kwargs: {"status": "complete"},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail(
            "capture command ran before runtime artifact preflight"
        ),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        output_dir=tmp_path / "capture",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=tmp_path / "manual.json",
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match="capture-owned Vercel and Docker"):
        capture(args)


@pytest.mark.parametrize(
    ("holdout_report", "review_bundle", "summary", "message"),
    [
        (Path("report.json"), None, None, "requires both"),
        (None, Path("bundle.json"), None, "requires both"),
        (None, None, Path("summary.json"), "summary requires"),
    ],
)
def test_after_capture_rejects_incomplete_semantic_holdout_artifact_sets(
    holdout_report: Path | None,
    review_bundle: Path | None,
    summary: Path | None,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before artifact preflight"),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=holdout_report,
        semantic_holdout_review_bundle=review_bundle,
        semantic_holdout_summary=summary,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match=message):
        capture(args)
