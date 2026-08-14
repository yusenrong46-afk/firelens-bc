"""Aggregate frontend performance and qualification evidence capture."""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.common import (
    ROOT,
    file_sha256,
)
from firelens.evaluation.common import (
    read_report as _read_report,
)
from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    require_timestamp as _require_timestamp,
)
from firelens.evaluation.common import (
    run_logged as _run_logged,
)
from firelens.evaluation.common import (
    strict_number as _strict_number,
)
from firelens.evaluation.frontend_map import _frontend_surface_row
from firelens.evaluation.frontend_privacy import _frontend_functional_journeys
from firelens.evaluation.frontend_protocol import (
    _frontend_bundle,
    _frontend_p75,
    _frontend_surface_environment,
    _frontend_surface_protocol,
    _require_object_list,
)


def _frontend_performance(performance: Any, *, protocol: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(performance, dict):
        raise ValueError("frontend performance evidence must be an object")
    _require_exact_keys(
        performance,
        {"aggregation", "profiles", "qualified"},
        context="frontend performance evidence",
    )
    if performance.get("aggregation") != protocol["performance"]["aggregation"]:
        raise ValueError("frontend performance aggregation differs from the protocol")
    profiles = _require_object_list(
        performance.get("profiles"), context="frontend performance profiles"
    )
    expected_profile_ids = protocol["performance"]["profiles"]
    if len(profiles) != len(expected_profile_ids):
        raise ValueError("frontend performance profile roster is incomplete")
    profile_results: dict[str, dict[str, float]] = {}
    all_profiles_qualified = True
    metric_names = protocol["performance"]["metrics"]
    for profile, profile_id in zip(profiles, expected_profile_ids, strict=True):
        context = f"frontend performance profile {profile_id}"
        _require_exact_keys(
            profile,
            {
                "profile_id",
                "viewport",
                "throttling",
                "samples",
                "cold_p75",
                "thresholds",
                "checks",
                "qualified",
            },
            context=context,
        )
        if profile.get("profile_id") != profile_id:
            raise ValueError("frontend performance profile roster or order was altered")
        viewport = next(item for item in protocol["viewports"] if item["id"] == profile_id)
        if profile.get("viewport") != {
            "width": viewport["width"],
            "height": viewport["height"],
        }:
            raise ValueError(f"{context} viewport differs from the protocol")
        expected_throttling = {
            "cpu_rate": protocol["performance"]["cpu_throttling_rate"],
            "network": protocol["performance"]["network"],
            "cache_disabled": protocol["performance"]["cache_disabled_for_cold_samples"],
        }
        if profile.get("throttling") != expected_throttling:
            raise ValueError(f"{context} throttling differs from the protocol")
        samples = _require_object_list(profile.get("samples"), context=f"{context} samples")
        expected_sample_roster = [("warmup", 1)] + [("cold", index) for index in range(1, 8)]
        if len(samples) != len(expected_sample_roster):
            raise ValueError(f"{context} must retain the exact 1+7 samples")
        cold_values: dict[str, list[float]] = {metric: [] for metric in metric_names}
        for sample, (expected_phase, expected_index) in zip(
            samples, expected_sample_roster, strict=True
        ):
            sample_context = f"{context} {expected_phase} sample {expected_index}"
            _require_exact_keys(
                sample,
                {
                    "phase",
                    "sample_index",
                    "lcp_ms",
                    "cls",
                    "inp_interaction_proxy_ms",
                    "map_ready_after_interaction_ms",
                    "status",
                    "error",
                },
                context=sample_context,
            )
            if (
                sample.get("phase") != expected_phase
                or sample.get("sample_index") != expected_index
            ):
                raise ValueError(f"{context} sample roster or order was altered")
            if sample.get("status") != "complete" or sample.get("error") is not None:
                raise ValueError(f"{sample_context} is incomplete")
            for metric in metric_names:
                value = _strict_number(sample, metric, sample_context, minimum=0)
                if expected_phase == "cold":
                    cold_values[metric].append(value)
        recomputed_p75 = {metric: _frontend_p75(cold_values[metric]) for metric in metric_names}
        reported_p75 = profile.get("cold_p75")
        if not isinstance(reported_p75, dict):
            raise ValueError(f"{context} cold_p75 must be an object")
        _require_exact_keys(reported_p75, set(metric_names), context=f"{context} cold_p75")
        for metric, expected_value in recomputed_p75.items():
            observed = _strict_number(reported_p75, metric, f"{context} cold_p75", minimum=0)
            if not math.isclose(observed, expected_value, rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{context} {metric} p75 differs from raw samples")
        thresholds = protocol["performance"]["thresholds"][profile_id]
        if profile.get("thresholds") != thresholds:
            raise ValueError(f"{context} thresholds differ from the protocol")
        expected_checks = {
            "exact_sample_count": True,
            "lcp_within_threshold": recomputed_p75["lcp_ms"] <= thresholds["lcp_ms_max"],
            "cls_within_threshold": recomputed_p75["cls"] <= thresholds["cls_max"],
            "inp_proxy_within_threshold": recomputed_p75["inp_interaction_proxy_ms"]
            <= thresholds["inp_interaction_proxy_ms_max"],
            "map_ready_within_threshold": recomputed_p75["map_ready_after_interaction_ms"]
            <= thresholds["map_ready_after_interaction_ms_max"],
        }
        if profile.get("checks") != expected_checks:
            raise ValueError(f"{context} checks differ from recomputed p75 values")
        qualified = all(expected_checks.values())
        if type(profile.get("qualified")) is not bool or profile["qualified"] != qualified:
            raise ValueError(f"{context} qualification differs from raw samples")
        all_profiles_qualified = all_profiles_qualified and qualified
        profile_results[profile_id] = recomputed_p75
    if (
        type(performance.get("qualified")) is not bool
        or performance["qualified"] != all_profiles_qualified
    ):
        raise ValueError("frontend performance qualification differs from raw profiles")
    return {
        "qualified": all_profiles_qualified,
        "profiles": profile_results,
        "worst_profile_p75": {
            metric: max(
                profile_results[profile_id][metric] for profile_id in expected_profile_ids
            )
            for metric in metric_names
        },
    }


def _frontend_surface(
    report_path: Path,
    *,
    protocol_path: Path,
    expected_commit: str,
    expected_environment: dict[str, str | int],
    frontend_bundle: dict[str, Any],
    client_root: Path | None = None,
) -> dict[str, Any]:
    report = _read_report(report_path)
    if report is None:
        raise ValueError("frontend surface report is missing")
    protocol = _frontend_surface_protocol(protocol_path)
    base_url, browser = _validated_surface_report_identity(report, protocol, protocol_path)
    environment = _frontend_surface_environment(
        report.get("execution_environment"),
        protocol=protocol,
        expected_environment=expected_environment,
        top_level_browser=browser,
    )

    client = client_root or ROOT / "apps/web/dist/client"
    _validate_surface_build(report.get("build"), client, expected_commit, frontend_bundle)

    rows = _require_object_list(report.get("surface_rows"), context="frontend surface rows")
    expected_pairs = [
        (state, viewport) for state in protocol["states"] for viewport in protocol["viewports"]
    ]
    if len(rows) != len(expected_pairs):
        raise ValueError("frontend surface report does not contain the exact 12x3 matrix")
    row_results = [
        _frontend_surface_row(
            row,
            state=state,
            viewport=viewport,
            protocol=protocol,
            report_path=report_path,
            base_url=base_url,
        )
        for row, (state, viewport) in zip(rows, expected_pairs, strict=True)
    ]
    journeys = _frontend_functional_journeys(
        report.get("functional_journeys"), protocol=protocol
    )
    performance = _frontend_performance(report.get("performance"), protocol=protocol)

    qualified_rows = sum(result["qualified"] for result in row_results)
    map_parity_values = [
        result["map_list_parity"]
        for result in row_results
        if result["map_list_parity"] is not None
    ]
    map_list_parity = bool(map_parity_values) and all(map_parity_values)
    map_detail_values = [
        result["map_detail_integrity"]
        for result in row_results
        if result["map_detail_integrity"] is not None
    ]
    map_detail_integrity = bool(map_detail_values) and all(map_detail_values)
    map_placement_values = [
        result["map_marker_placement_sanity"]
        for result in row_results
        if result["map_marker_placement_sanity"] is not None
    ]
    map_marker_placement_sanity = bool(map_placement_values) and all(map_placement_values)
    protocol_ratified = protocol["status"] == "ratified" and bool(protocol["frozen_at"])
    matrix_complete = len(row_results) == protocol["matrix"]["expected_rows"]
    surface_qualified = matrix_complete and qualified_rows == len(row_results)
    summary = {
        "protocol_ratified": protocol_ratified,
        "expected_surface_rows": protocol["matrix"]["expected_rows"],
        "executed_surface_rows": len(row_results),
        "matrix_complete": matrix_complete,
        "qualified_surface_rows": qualified_rows,
        "functional_journeys_qualified": journeys["qualified"],
        "performance_qualified": performance["qualified"],
        "structure_issues": [],
        "qualified": (
            protocol_ratified
            and surface_qualified
            and journeys["qualified"]
            and performance["qualified"]
        ),
    }
    if report.get("summary") != summary:
        raise ValueError("frontend surface summary differs from raw evidence")
    return {
        "status": "complete",
        "report_sha256": file_sha256(report_path),
        "generated_at": report["generated_at"],
        "commit": expected_commit,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": file_sha256(protocol_path),
        "protocol_status": protocol["status"],
        "protocol_frozen_at": protocol["frozen_at"],
        "execution_environment": environment,
        "qualified": summary["qualified"],
        "visual_matrix_pass_rate": qualified_rows / len(row_results),
        "css_layout_violation_count": sum(
            result["css_layout_violation_count"] for result in row_results
        ),
        "axe_wcag_a_aa_finding_count": sum(
            result["axe_finding_count"] for result in row_results
        ),
        "runtime_violation_count": sum(
            result["runtime_violation_count"] for result in row_results
        ),
        "keyboard_journey_passed": journeys["keyboard_journey_passed"],
        "map_list_parity": map_list_parity,
        "map_detail_integrity": map_detail_integrity,
        "map_marker_placement_sanity": map_marker_placement_sanity,
        "direct_third_party_tile_request_count": sum(
            result["direct_third_party_tile_request_count"] for result in row_results
        ),
        "worst_profile_p75": performance["worst_profile_p75"],
    }


def _validated_surface_report_identity(
    report: dict[str, Any], protocol: dict[str, Any], protocol_path: Path
) -> tuple[str, dict[str, Any]]:
    keys = {
        "schema_version",
        "generated_at",
        "protocol_id",
        "protocol_sha256",
        "protocol_status",
        "protocol_frozen_at",
        "base_url",
        "execution_environment",
        "browser",
        "build",
        "surface_rows",
        "functional_journeys",
        "performance",
        "summary",
    }
    _require_exact_keys(report, keys, context="frontend surface report")
    if report.get("schema_version") != "firelens.frontend_surface_report.v1":
        raise ValueError("frontend surface report uses an unsupported schema")
    _require_timestamp(
        report.get("generated_at"), context="frontend surface report generated_at"
    )
    if report.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("frontend surface report uses the wrong protocol_id")
    if report.get("protocol_sha256") != file_sha256(protocol_path):
        raise ValueError("frontend surface report uses the wrong protocol digest")
    if (
        report.get("protocol_status") != protocol["status"]
        or report.get("protocol_frozen_at") != protocol["frozen_at"]
    ):
        raise ValueError("frontend surface report protocol status is inconsistent")
    base_url = report.get("base_url")
    if base_url != protocol["surface_thresholds"]["allowed_request_origins"][0]:
        raise ValueError("frontend surface report uses the wrong local preview origin")
    browser = report.get("browser")
    if not isinstance(browser, dict):
        raise ValueError("frontend surface report browser identity must be an object")
    _require_exact_keys(
        browser, {"name", "version"}, context="frontend surface report browser identity"
    )
    return base_url, browser


def _validate_surface_build(
    value: Any, client: Path, expected_commit: str, frontend_bundle: dict[str, Any]
) -> None:
    if not isinstance(value, dict):
        raise ValueError("frontend surface report build identity must be an object")
    _require_exact_keys(
        value,
        {"commit", "index_sha256", "manifest_sha256"},
        context="frontend surface report build identity",
    )
    if value.get("commit") != expected_commit:
        raise ValueError("frontend surface report commit differs from the capture commit")
    index_path = client / "index.html"
    if not index_path.is_file():
        raise ValueError("frontend surface build index is missing")
    if value.get("index_sha256") != file_sha256(index_path):
        raise ValueError("frontend surface report uses a different built index")
    if value.get("manifest_sha256") != frontend_bundle.get("manifest_sha256"):
        raise ValueError("frontend surface report uses a different build manifest")


def _capture_frontend_surface(
    *,
    output_dir: Path,
    expected_commit: str,
    expected_environment: dict[str, str | int],
    run_logged: Callable[[list[str], Path], dict[str, Any]] = _run_logged,
    bundle_builder: Callable[[], dict[str, Any]] = _frontend_bundle,
    surface_validator: Callable[..., dict[str, Any]] = _frontend_surface,
) -> dict[str, Any]:
    """Run and validate capture-owned frontend evidence in a fresh fixed directory."""

    resolved_output_dir = output_dir.resolve()
    surface_output_dir = (resolved_output_dir / "frontend_surface").resolve()
    if surface_output_dir.parent != resolved_output_dir:
        raise ValueError("frontend surface output directory escapes the benchmark output")
    if surface_output_dir.exists():
        shutil.rmtree(surface_output_dir)
    report_path = surface_output_dir / "report.json"
    protocol_path = ROOT / "data/evaluation/frontend_surface.v1.yaml"
    started_at = datetime.now(UTC)
    run = run_logged(
        [
            "npm",
            "--prefix",
            "apps/web",
            "run",
            "qualify:surface",
            "--",
            "--protocol",
            str(protocol_path),
            "--output-dir",
            str(surface_output_dir),
        ],
        resolved_output_dir / "frontend_surface.log",
    )
    finished_at = datetime.now(UTC)
    if run.get("exit_code") not in {0, 2}:
        raise RuntimeError(
            "frontend surface harness failed before producing eligible evidence; "
            "see its benchmark log"
        )
    if not report_path.is_file():
        raise RuntimeError("frontend surface harness did not create a fresh report")
    raw_report = _read_report(report_path)
    if not isinstance(raw_report, dict):
        raise ValueError("capture-owned frontend surface report is invalid")
    generated_value = _require_nonempty_string(
        raw_report.get("generated_at"),
        context="capture-owned frontend surface generated_at",
    )
    try:
        generated_at = datetime.fromisoformat(generated_value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("capture-owned frontend surface generated_at is invalid") from error
    if generated_at.tzinfo is None:
        raise ValueError("capture-owned frontend surface generated_at must include a timezone")
    generated_at = generated_at.astimezone(UTC)
    if not started_at <= generated_at <= finished_at:
        raise ValueError(
            "frontend surface report was not generated by the current capture-owned run"
        )

    frontend_bundle = bundle_builder()
    frontend_surface = surface_validator(
        report_path,
        protocol_path=protocol_path,
        expected_commit=expected_commit,
        expected_environment=expected_environment,
        frontend_bundle=frontend_bundle,
    )
    expected_exit_code = 0 if frontend_surface["qualified"] else 2
    if run["exit_code"] != expected_exit_code:
        raise ValueError(
            "frontend surface harness exit code disagrees with recomputed qualification"
        )
    return {
        "run": run,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "report_path": report_path,
        "bundle": frontend_bundle,
        "surface": frontend_surface,
    }
