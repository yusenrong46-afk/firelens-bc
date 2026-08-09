"""Canonical frontend evaluation protocol and environment validation."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from firelens.evaluation.common import (
    ROOT,
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
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)
from firelens.evaluation.common import (
    strict_number as _strict_number,
)
from firelens.evaluation.frontend_bundle import measure_frontend_bundle


def _frontend_bundle(dist_root: Path | None = None) -> dict[str, Any]:
    return measure_frontend_bundle(dist_root or ROOT / "apps/web/dist", repository_root=ROOT)


def _frontend_surface_protocol(path: Path) -> dict[str, Any]:
    protocol = _read_report(path)
    if protocol is None:
        raise ValueError("frontend surface protocol is missing")
    _require_exact_keys(
        protocol,
        {
            "schema_version",
            "protocol_id",
            "status",
            "frozen_at",
            "description",
            "matrix",
            "states",
            "viewports",
            "execution_environment",
            "map_parity",
            "surface_thresholds",
            "functional_journeys",
            "privacy_evidence",
            "performance",
        },
        context="frontend surface protocol",
    )
    if protocol.get("schema_version") != "firelens.frontend_surface_protocol.v1":
        raise ValueError("frontend surface protocol uses an unsupported schema")
    _require_nonempty_string(
        protocol.get("protocol_id"), context="frontend surface protocol_id"
    )
    status = protocol.get("status")
    if status not in {"provisional", "ratified"}:
        raise ValueError("frontend surface protocol status is invalid")
    if status == "ratified":
        _require_timestamp(
            protocol.get("frozen_at"), context="frontend surface protocol frozen_at"
        )
    elif protocol.get("frozen_at") is not None:
        raise ValueError("provisional frontend surface protocol cannot declare frozen_at")
    _require_nonempty_string(
        protocol.get("description"), context="frontend surface protocol description"
    )

    matrix = protocol.get("matrix")
    if not isinstance(matrix, dict):
        raise ValueError("frontend surface matrix must be an object")
    _require_exact_keys(
        matrix,
        {"expected_rows", "require_every_state_viewport_pair_once"},
        context="frontend surface matrix",
    )
    if _strict_int(
        matrix, "expected_rows", "frontend surface matrix", minimum=0
    ) != 30 or not _strict_bool(
        matrix,
        "require_every_state_viewport_pair_once",
        "frontend surface matrix",
    ):
        raise ValueError("frontend surface matrix must freeze the exact 10x3 roster")

    states = protocol.get("states")
    expected_state_ids = [
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
    if not isinstance(states, list) or len(states) != 10:
        raise ValueError("frontend surface protocol requires exactly ten states")
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            raise ValueError(f"frontend surface state {index} must be an object")
        _require_exact_keys(
            state,
            {"id", "question", "ready_text"},
            context=f"frontend surface state {index}",
        )
        _require_nonempty_string(state.get("id"), context=f"frontend surface state {index} ID")
        if state.get("question") is not None:
            _require_nonempty_string(
                state.get("question"), context=f"frontend surface state {index} question"
            )
        _require_nonempty_string(
            state.get("ready_text"), context=f"frontend surface state {index} ready_text"
        )
    if [state["id"] for state in states] != expected_state_ids:
        raise ValueError("frontend surface state roster or order is not canonical")

    viewports = protocol.get("viewports")
    if not isinstance(viewports, list) or len(viewports) != 3:
        raise ValueError("frontend surface protocol requires exactly three viewports")
    for index, viewport in enumerate(viewports):
        if not isinstance(viewport, dict):
            raise ValueError(f"frontend surface viewport {index} must be an object")
        _require_exact_keys(
            viewport,
            {"id", "width", "height", "device_scale_factor", "is_mobile"},
            context=f"frontend surface viewport {index}",
        )
        _require_nonempty_string(
            viewport.get("id"), context=f"frontend surface viewport {index} ID"
        )
        for key in ("width", "height", "device_scale_factor"):
            _strict_int(viewport, key, f"frontend surface viewport {index}", minimum=1)
        _strict_bool(viewport, "is_mobile", f"frontend surface viewport {index}")
    if [viewport["id"] for viewport in viewports] != ["mobile", "tablet", "desktop"]:
        raise ValueError("frontend surface viewport roster or order is not canonical")

    execution_environment = protocol.get("execution_environment")
    if execution_environment != {
        "locale": "en-CA",
        "timezone_id": "America/Vancouver",
        "color_scheme": "light",
        "reduced_motion": "reduce",
        "browser_name": "chromium",
        "headless": True,
    }:
        raise ValueError("frontend surface execution environment is not canonical")
    map_parity = protocol.get("map_parity")
    if map_parity != {
        "applicable_state_ids": [
            "live",
            "mixed",
            "stale",
            "no_result",
            "partial_layer",
        ],
        "pagination_mode": "none",
        "response_complete_roster": True,
        "allow_rendered_roster_truncation": False,
    }:
        raise ValueError("frontend surface map-parity protocol is not canonical")

    thresholds = protocol.get("surface_thresholds")
    expected_threshold_keys = {
        "axe_wcag_a_aa_findings_max",
        "document_horizontal_overflow_max_px",
        "clipped_text_elements_max",
        "inaccessible_stylesheets_max",
        "stylesheet_load_failures_max",
        "unstyled_interactive_elements_max",
        "undersized_interactive_elements_max",
        "undersized_text_elements_max",
        "minimum_interactive_target_css_px",
        "minimum_body_text_css_px",
        "minimum_secondary_text_css_px",
        "console_errors_max",
        "page_errors_max",
        "unexpected_request_origins_max",
        "direct_third_party_tile_requests_max",
        "allowed_failed_request_urls",
        "allowed_request_origins",
    }
    if not isinstance(thresholds, dict):
        raise ValueError("frontend surface thresholds must be an object")
    _require_exact_keys(
        thresholds, expected_threshold_keys, context="frontend surface thresholds"
    )
    for key in expected_threshold_keys - {
        "allowed_failed_request_urls",
        "allowed_request_origins",
    }:
        _strict_int(thresholds, key, "frontend surface thresholds", minimum=0)
    if thresholds.get("allowed_failed_request_urls") != []:
        raise ValueError("frontend surface failed-request allowlist must remain empty")
    allowed_origins = thresholds.get("allowed_request_origins")
    if (
        not isinstance(allowed_origins, list)
        or not allowed_origins
        or not all(isinstance(value, str) and value for value in allowed_origins)
        or len(allowed_origins) != len(set(allowed_origins))
    ):
        raise ValueError("frontend surface allowed request origins are invalid")

    journeys = protocol.get("functional_journeys")
    if not isinstance(journeys, list) or len(journeys) != 3:
        raise ValueError("frontend surface protocol requires exactly three journeys")
    for index, journey in enumerate(journeys):
        if not isinstance(journey, dict):
            raise ValueError(f"frontend journey {index} must be an object")
        _require_exact_keys(
            journey,
            {"id", "required_checks"},
            context=f"frontend journey {index}",
        )
        _require_nonempty_string(journey.get("id"), context=f"frontend journey {index} ID")
        checks = journey.get("required_checks")
        if (
            not isinstance(checks, list)
            or not checks
            or not all(isinstance(value, str) and value for value in checks)
            or len(checks) != len(set(checks))
        ):
            raise ValueError(f"frontend journey {index} required checks are invalid")
    if [journey["id"] for journey in journeys] != [
        "keyboard_evidence_navigation",
        "location_privacy_boundary",
        "history_clear_boundary",
    ]:
        raise ValueError("frontend functional journey roster or order is not canonical")

    privacy_evidence = protocol.get("privacy_evidence")
    if privacy_evidence != {
        "request_url": "http://127.0.0.1:4175/api/v1/ask",
        "expected_questions": ["surface:grounded", "surface:live-fresh"],
        "allowed_body_keys": ["history", "location", "question"],
        "fixture_location": {
            "raw_latitude": 49.282729,
            "raw_longitude": -123.120738,
            "rounded_latitude": 49.28,
            "rounded_longitude": -123.12,
            "radius_km": 50,
        },
        "persistence_probe_tokens": [
            "49.282729",
            "-123.120738",
            "49.28",
            "-123.12",
        ],
    }:
        raise ValueError("frontend privacy evidence protocol is not canonical")

    performance = protocol.get("performance")
    if not isinstance(performance, dict):
        raise ValueError("frontend performance protocol must be an object")
    _require_exact_keys(
        performance,
        {
            "browser",
            "profiles",
            "warmup_samples",
            "cold_samples",
            "cache_disabled_for_cold_samples",
            "cpu_throttling_rate",
            "network",
            "aggregation",
            "metrics",
            "thresholds",
        },
        context="frontend performance protocol",
    )
    if performance.get("browser") != "chromium":
        raise ValueError("frontend performance protocol requires Chromium")
    if performance.get("profiles") != ["mobile", "desktop"]:
        raise ValueError("frontend performance profile order is not canonical")
    if (
        _strict_int(performance, "warmup_samples", "frontend performance", minimum=0) != 1
        or _strict_int(performance, "cold_samples", "frontend performance", minimum=0) != 7
        or not _strict_bool(
            performance,
            "cache_disabled_for_cold_samples",
            "frontend performance",
        )
    ):
        raise ValueError("frontend performance sample protocol must be exactly 1+7")
    _strict_number(
        performance,
        "cpu_throttling_rate",
        "frontend performance",
        minimum=1,
    )
    network = performance.get("network")
    if not isinstance(network, dict):
        raise ValueError("frontend performance network profile must be an object")
    _require_exact_keys(
        network,
        {
            "latency_ms",
            "download_bytes_per_second",
            "upload_bytes_per_second",
            "connection_type",
        },
        context="frontend performance network profile",
    )
    for key in ("latency_ms", "download_bytes_per_second", "upload_bytes_per_second"):
        _strict_number(network, key, "frontend performance network profile", minimum=0)
    _require_nonempty_string(
        network.get("connection_type"), context="frontend performance connection type"
    )
    if performance.get("aggregation") != "p75_nearest_rank":
        raise ValueError("frontend performance aggregation is not canonical")
    expected_performance_metrics = [
        "lcp_ms",
        "cls",
        "inp_interaction_proxy_ms",
        "map_ready_after_interaction_ms",
    ]
    if performance.get("metrics") != expected_performance_metrics:
        raise ValueError("frontend performance metric roster or order is not canonical")
    performance_thresholds = performance.get("thresholds")
    if not isinstance(performance_thresholds, dict) or list(performance_thresholds) != [
        "mobile",
        "desktop",
    ]:
        raise ValueError("frontend performance threshold profiles are not canonical")
    expected_profile_threshold_keys = {
        "lcp_ms_max",
        "cls_max",
        "inp_interaction_proxy_ms_max",
        "map_ready_after_interaction_ms_max",
    }
    for profile_id, profile_thresholds in performance_thresholds.items():
        if not isinstance(profile_thresholds, dict):
            raise ValueError(f"frontend {profile_id} thresholds must be an object")
        _require_exact_keys(
            profile_thresholds,
            expected_profile_threshold_keys,
            context=f"frontend {profile_id} thresholds",
        )
        for key in expected_profile_threshold_keys:
            _strict_number(
                profile_thresholds,
                key,
                f"frontend {profile_id} thresholds",
                minimum=0,
            )
    return protocol


def _frontend_p75(values: list[float]) -> float:
    if len(values) != 7 or any(not math.isfinite(value) for value in values):
        raise ValueError("frontend performance p75 requires exactly seven finite cold samples")
    ordered = sorted(values)
    return ordered[math.ceil(0.75 * len(ordered)) - 1]


def _require_object_list(value: Any, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{context} must be a list of objects")
    return value


def _require_string_list(value: Any, *, context: str, unique: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{context} must be a list of strings")
    if unique and len(value) != len(set(value)):
        raise ValueError(f"{context} must not contain duplicates")
    return value


def _frontend_surface_environment(
    environment: Any,
    *,
    protocol: dict[str, Any],
    expected_environment: dict[str, str | int],
    top_level_browser: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(environment, dict):
        raise ValueError("frontend surface report has no execution_environment")
    _require_exact_keys(
        environment,
        {"os", "runtime", "browser", "run_profiles"},
        context="frontend surface execution_environment",
    )
    observed_os = environment.get("os")
    if not isinstance(observed_os, dict):
        raise ValueError("frontend surface OS identity must be an object")
    _require_exact_keys(
        observed_os,
        {"name", "release", "architecture", "cpu_model", "logical_cpu_count"},
        context="frontend surface OS identity",
    )
    expected_os = {
        "name": str(expected_environment["os"]).lower(),
        "release": expected_environment["os_release"],
        "architecture": expected_environment["architecture"],
        "cpu_model": expected_environment["cpu_model"],
        "logical_cpu_count": expected_environment["logical_cpu_count"],
    }
    if observed_os != expected_os:
        raise ValueError("frontend surface report was produced on a different OS/CPU identity")

    observed_runtime = environment.get("runtime")
    if not isinstance(observed_runtime, dict):
        raise ValueError("frontend surface runtime identity must be an object")
    _require_exact_keys(
        observed_runtime,
        {"node_version", "npm_version", "playwright_package_version"},
        context="frontend surface runtime identity",
    )
    expected_runtime = {
        "node_version": str(expected_environment["node_version"]).removeprefix("v"),
        "npm_version": expected_environment["npm_version"],
        "playwright_package_version": expected_environment["playwright_version"],
    }
    if observed_runtime != expected_runtime:
        raise ValueError(
            "frontend surface report uses a different Node/npm/Playwright identity"
        )

    observed_browser = environment.get("browser")
    if not isinstance(observed_browser, dict):
        raise ValueError("frontend surface browser identity must be an object")
    _require_exact_keys(
        observed_browser,
        {"name", "version", "headless", "locale", "timezone_id"},
        context="frontend surface browser identity",
    )
    if observed_browser.get("name") != protocol["execution_environment"]["browser_name"]:
        raise ValueError("frontend surface report uses the wrong browser")
    version = _require_nonempty_string(
        observed_browser.get("version"), context="frontend surface browser version"
    )
    expected_version_match = re.search(
        r"[0-9]+(?:\.[0-9]+)+", str(expected_environment["chromium_version"])
    )
    if expected_version_match is None or version != expected_version_match.group(0):
        raise ValueError(
            "frontend surface browser version differs from the capture environment"
        )
    if (
        _strict_bool(observed_browser, "headless", "frontend surface browser")
        is not protocol["execution_environment"]["headless"]
    ):
        raise ValueError("frontend surface browser must run headlessly")
    _require_nonempty_string(
        observed_browser.get("locale"), context="frontend surface browser locale"
    )
    _require_nonempty_string(
        observed_browser.get("timezone_id"), context="frontend surface browser timezone"
    )
    if top_level_browser != {
        "name": observed_browser["name"],
        "version": observed_browser["version"],
    }:
        raise ValueError("frontend surface top-level browser identity is inconsistent")
    for key in ("locale", "timezone_id"):
        if observed_browser[key] != protocol["execution_environment"][key]:
            raise ValueError(f"frontend surface browser {key} differs from the protocol")

    run_profiles = environment.get("run_profiles")
    if not isinstance(run_profiles, dict):
        raise ValueError("frontend surface run profiles must be an object")
    _require_exact_keys(
        run_profiles,
        {"surface_matrix", "functional_journeys", "performance"},
        context="frontend surface run profiles",
    )
    surface_profiles = _require_object_list(
        run_profiles.get("surface_matrix"), context="frontend surface matrix profiles"
    )
    if len(surface_profiles) != 3:
        raise ValueError("frontend surface environment must retain three matrix profiles")
    expected_matrix_profile_keys = {
        "viewport_id",
        "viewport",
        "device_scale_factor",
        "is_mobile",
        "color_scheme",
        "reduced_motion",
        "locale",
        "timezone_id",
        "cpu_throttling",
        "network",
    }

    def validate_profile(
        profile: dict[str, Any],
        *,
        viewport: dict[str, Any],
        context: str,
        profile_id_key: str,
        performance_profile: bool,
    ) -> None:
        expected_keys = set(expected_matrix_profile_keys)
        expected_keys.add(profile_id_key)
        _require_exact_keys(profile, expected_keys, context=context)
        _validate_profile_identity(
            profile, viewport, observed_browser, protocol, context, profile_id_key
        )
        _validate_profile_throttling(profile, protocol, context, performance_profile)

    for profile, viewport in zip(surface_profiles, protocol["viewports"], strict=True):
        validate_profile(
            profile,
            viewport=viewport,
            context=f"frontend matrix profile {viewport['id']}",
            profile_id_key="viewport_id",
            performance_profile=False,
        )

    journey_profiles = _require_object_list(
        run_profiles.get("functional_journeys"),
        context="frontend functional journey profiles",
    )
    if len(journey_profiles) != 3:
        raise ValueError("frontend environment must retain three journey profiles")
    desktop = next(
        viewport for viewport in protocol["viewports"] if viewport["id"] == "desktop"
    )
    for journey, profile in zip(protocol["functional_journeys"], journey_profiles, strict=True):
        if profile.get("journey_id") != journey["id"]:
            raise ValueError("frontend journey execution profile order is not canonical")
        profile_without_journey = dict(profile)
        profile_without_journey.pop("journey_id", None)
        validate_profile(
            profile_without_journey,
            viewport=desktop,
            context=f"frontend functional journey profile {journey['id']}",
            profile_id_key="viewport_id",
            performance_profile=False,
        )

    performance_profiles = _require_object_list(
        run_profiles.get("performance"), context="frontend performance run profiles"
    )
    if len(performance_profiles) != 2:
        raise ValueError("frontend environment must retain two performance profiles")
    viewport_by_id = {viewport["id"]: viewport for viewport in protocol["viewports"]}
    for profile_id, profile in zip(
        protocol["performance"]["profiles"], performance_profiles, strict=True
    ):
        validate_profile(
            profile,
            viewport=viewport_by_id[profile_id],
            context=f"frontend performance run profile {profile_id}",
            profile_id_key="profile_id",
            performance_profile=True,
        )
    return environment


def _validate_profile_identity(
    profile: dict[str, Any],
    viewport: dict[str, Any],
    observed_browser: dict[str, Any],
    protocol: dict[str, Any],
    context: str,
    profile_id_key: str,
) -> None:
    if profile.get(profile_id_key) != viewport["id"]:
        raise ValueError(f"{context} uses the wrong profile ID")
    if profile.get("viewport_id") != viewport["id"]:
        raise ValueError(f"{context} uses the wrong viewport ID")
    if profile.get("viewport") != {"width": viewport["width"], "height": viewport["height"]}:
        raise ValueError(f"{context} uses the wrong viewport")
    if profile.get("device_scale_factor") != viewport["device_scale_factor"]:
        raise ValueError(f"{context} uses the wrong device scale")
    if (
        type(profile.get("is_mobile")) is not bool
        or profile["is_mobile"] != viewport["is_mobile"]
    ):
        raise ValueError(f"{context} uses the wrong mobile profile")
    for key in ("color_scheme", "reduced_motion", "locale", "timezone_id"):
        _require_nonempty_string(profile.get(key), context=f"{context} {key}")
    expected = protocol["execution_environment"]
    if (
        profile["locale"],
        profile["timezone_id"],
        profile["color_scheme"],
        profile["reduced_motion"],
    ) != (
        observed_browser["locale"],
        observed_browser["timezone_id"],
        expected["color_scheme"],
        expected["reduced_motion"],
    ):
        raise ValueError(f"{context} visual/locale/timezone profile is inconsistent")


def _validate_profile_throttling(
    profile: dict[str, Any],
    protocol: dict[str, Any],
    context: str,
    performance: bool,
) -> None:
    cpu, network = profile.get("cpu_throttling"), profile.get("network")
    if not isinstance(cpu, dict) or not isinstance(network, dict):
        raise ValueError(f"{context} throttling profiles must be objects")
    if performance:
        expected_cpu = {
            "mode": "cdp_emulation",
            "rate": protocol["performance"]["cpu_throttling_rate"],
        }
        expected_network = {
            "mode": "cdp_emulation",
            **protocol["performance"]["network"],
            "cache_disabled": protocol["performance"]["cache_disabled_for_cold_samples"],
        }
        if cpu != expected_cpu:
            raise ValueError(f"{context} CPU profile differs from the protocol")
        if network != expected_network:
            raise ValueError(f"{context} network profile differs from the protocol")
        return
    _require_exact_keys(cpu, {"mode", "rate"}, context=f"{context} CPU profile")
    _require_exact_keys(network, {"mode", "cache_policy"}, context=f"{context} network profile")
    if cpu != {"mode": "none", "rate": 1} or network != {
        "mode": "local_preview_with_deterministic_routes",
        "cache_policy": "fresh_browser_context_default",
    }:
        raise ValueError(f"{context} must declare an unthrottled functional profile")
