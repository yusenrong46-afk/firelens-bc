"""Map/list parity and responsive frontend surface evidence validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from firelens.evaluation.common import (
    ROOT,
    file_sha256,
)
from firelens.evaluation.common import (
    require_digest as _require_digest,
)
from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
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
from firelens.evaluation.frontend_browser import (
    _frontend_axe,
    _frontend_layout,
    _frontend_runtime,
)
from firelens.evaluation.frontend_protocol import (
    _require_object_list,
    _require_string_list,
)


def _frontend_expected_map_roster(state_id: str) -> list[str]:
    if state_id == "live":
        return [f"incident:surface-{index:02d}" for index in range(1, 11)]
    if state_id in {"mixed", "stale", "partial_layer"}:
        return ["incident:surface-7"]
    if state_id == "no_result":
        return []
    raise ValueError(f"frontend state {state_id} is not in the map-parity roster")


def _frontend_expected_map_records(state_id: str) -> dict[str, dict[str, str]]:
    roster = _frontend_expected_map_roster(state_id)
    if state_id == "live":
        return {
            record_id: {
                "name": f"Surface Test Fire {record_id.rsplit('-', 1)[1]}",
                "source_url": (
                    f"https://example.test/incidents/surface-{record_id.rsplit('-', 1)[1]}"
                ),
                "geometry_type": "Point",
            }
            for record_id in roster
        }
    return {
        record_id: {
            "name": "Surface Test Fire",
            "source_url": "https://example.test/incidents/surface-7",
            "geometry_type": "Point",
        }
        for record_id in roster
    }


def _frontend_map_evidence(
    evidence: Any,
    *,
    context: str,
    state_id: str,
    protocol: dict[str, Any],
) -> tuple[bool | None, bool | None, bool | None]:
    if not isinstance(evidence, dict):
        raise ValueError(f"{context} map evidence must be an object")
    expected_keys = {
        "applicability",
        "reason",
        "collection_status",
        "pagination",
        "map_surface_present",
        "expected_response_record_ids",
        "rendered_accessible_list_record_ids",
        "rendered_map_feature_or_marker_record_ids",
        "rendered_accessible_list_records",
        "rendered_map_feature_or_marker_records",
        "unresolved_accessible_list_entries",
        "unresolved_map_feature_or_marker_entries",
        "detail_integrity",
        "marker_placement_sanity",
        "map_list_parity",
    }
    _require_exact_keys(evidence, expected_keys, context=f"{context} map evidence")
    applicable = state_id in protocol["map_parity"]["applicable_state_ids"]
    if not applicable:
        expected = {
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
        if evidence != expected:
            raise ValueError(f"{context} has invalid not-applicable map evidence")
        return None, None, None

    if evidence.get("applicability") != "applicable" or evidence.get("reason") is not None:
        raise ValueError(f"{context} map evidence applicability is inconsistent")
    if evidence.get("collection_status") != "complete":
        raise ValueError(f"{context} map evidence collection is incomplete")
    expected_ids = _frontend_expected_map_roster(state_id)
    expected_pagination = {
        "mode": protocol["map_parity"]["pagination_mode"],
        "response_complete_roster": protocol["map_parity"]["response_complete_roster"],
        "rendered_complete_roster_required": not protocol["map_parity"][
            "allow_rendered_roster_truncation"
        ],
        "map_surface_required": bool(expected_ids),
        "expected_total_records": len(expected_ids),
    }
    if evidence.get("pagination") != expected_pagination:
        raise ValueError(f"{context} map pagination declaration is inconsistent")
    if evidence.get("expected_response_record_ids") != expected_ids:
        raise ValueError(f"{context} expected map-response roster was altered")
    expected_records = _frontend_expected_map_records(state_id)
    map_surface_present = _strict_bool(
        evidence, "map_surface_present", f"{context} map evidence"
    )
    list_ids = _require_string_list(
        evidence.get("rendered_accessible_list_record_ids"),
        context=f"{context} accessible list IDs",
        unique=True,
    )
    map_ids = _require_string_list(
        evidence.get("rendered_map_feature_or_marker_record_ids"),
        context=f"{context} map feature IDs",
        unique=True,
    )
    list_records = _require_object_list(
        evidence.get("rendered_accessible_list_records"),
        context=f"{context} accessible list records",
    )
    map_records = _require_object_list(
        evidence.get("rendered_map_feature_or_marker_records"),
        context=f"{context} map feature records",
    )
    unresolved_list = _require_object_list(
        evidence.get("unresolved_accessible_list_entries"),
        context=f"{context} unresolved list entries",
    )
    unresolved_map = _require_object_list(
        evidence.get("unresolved_map_feature_or_marker_entries"),
        context=f"{context} unresolved map entries",
    )
    for index, row in enumerate(list_records):
        _require_exact_keys(
            row,
            {
                "dom_index",
                "rendered_name",
                "rendered_source_url",
                "record_id",
                "geometry_type",
                "resolution",
            },
            context=f"{context} accessible list record {index}",
        )
        if (
            _strict_int(
                row,
                "dom_index",
                f"{context} accessible list record {index}",
                minimum=0,
            )
            != index
        ):
            raise ValueError(f"{context} accessible list DOM indices are not contiguous")
        _require_nonempty_string(
            row.get("rendered_name"),
            context=f"{context} accessible list record {index} name",
        )
        if row.get("rendered_source_url") is not None:
            _require_nonempty_string(
                row.get("rendered_source_url"),
                context=f"{context} accessible list record {index} source URL",
            )
        if row.get("record_id") is not None:
            _require_nonempty_string(
                row.get("record_id"),
                context=f"{context} accessible list record {index} ID",
            )
        if row.get("geometry_type") is not None:
            _require_nonempty_string(
                row.get("geometry_type"),
                context=f"{context} accessible list record {index} geometry type",
            )
        if row.get("resolution") not in {"unique_name_and_source", "unresolved"}:
            raise ValueError(f"{context} accessible list record {index} resolution is invalid")
        record_id = row.get("record_id")
        if isinstance(record_id, str):
            canonical = expected_records.get(record_id)
            if canonical is None or (
                row["rendered_name"] != canonical["name"]
                or row["rendered_source_url"] != canonical["source_url"]
                or row["geometry_type"] != canonical["geometry_type"]
                or row["resolution"] != "unique_name_and_source"
            ):
                raise ValueError(
                    f"{context} accessible list record {index} is not canonically resolved"
                )
        elif row.get("resolution") != "unresolved":
            raise ValueError(f"{context} unresolved accessible record is misclassified")
    for index, row in enumerate(map_records):
        allowed_keys = {
            "dom_index",
            "rendered_popup_name",
            "element_tag",
            "record_id",
            "geometry_type",
            "canonical_source_url",
            "source_url_observed_in_popup",
            "observed_visible",
            "observed_center_css_px",
            "resolution",
        }
        if row.get("resolution") == "interaction_error":
            allowed_keys.add("error")
        _require_exact_keys(
            row,
            allowed_keys,
            context=f"{context} map feature record {index}",
        )
        if (
            _strict_int(
                row,
                "dom_index",
                f"{context} map feature record {index}",
                minimum=0,
            )
            != index
        ):
            raise ValueError(f"{context} map feature DOM indices are not contiguous")
        if row.get("rendered_popup_name") is not None:
            _require_nonempty_string(
                row.get("rendered_popup_name"),
                context=f"{context} map feature record {index} popup name",
            )
        _require_nonempty_string(
            row.get("element_tag"),
            context=f"{context} map feature record {index} element tag",
        )
        if row.get("record_id") is not None:
            _require_nonempty_string(
                row.get("record_id"), context=f"{context} map feature record {index} ID"
            )
        if row.get("geometry_type") is not None:
            _require_nonempty_string(
                row.get("geometry_type"),
                context=f"{context} map feature record {index} geometry type",
            )
        if row.get("canonical_source_url") is not None:
            _require_nonempty_string(
                row.get("canonical_source_url"),
                context=f"{context} map feature record {index} canonical source URL",
            )
        _strict_bool(
            row,
            "source_url_observed_in_popup",
            f"{context} map feature record {index}",
        )
        _strict_bool(
            row,
            "observed_visible",
            f"{context} map feature record {index}",
        )
        observed_center = row.get("observed_center_css_px")
        if observed_center is not None:
            if not isinstance(observed_center, dict):
                raise ValueError(
                    f"{context} map feature record {index} center must be an object"
                )
            _require_exact_keys(
                observed_center,
                {"x", "y"},
                context=f"{context} map feature record {index} center",
            )
            for coordinate in ("x", "y"):
                _strict_number(
                    observed_center,
                    coordinate,
                    f"{context} map feature record {index} center",
                )
        if row.get("resolution") not in {
            "unique_popup_name",
            "unresolved",
            "interaction_error",
        }:
            raise ValueError(f"{context} map feature record {index} resolution is invalid")
        record_id = row.get("record_id")
        if isinstance(record_id, str):
            canonical = expected_records.get(record_id)
            if canonical is None or (
                row["rendered_popup_name"] != canonical["name"]
                or row["geometry_type"] != canonical["geometry_type"]
                or row["canonical_source_url"] != canonical["source_url"]
                or row["source_url_observed_in_popup"] is not False
                or row["resolution"] != "unique_popup_name"
            ):
                raise ValueError(
                    f"{context} map feature record {index} is not canonically resolved"
                )
        elif row.get("resolution") not in {"unresolved", "interaction_error"}:
            raise ValueError(f"{context} unresolved map feature is misclassified")
    resolved_list_ids = [
        row["record_id"] for row in list_records if isinstance(row.get("record_id"), str)
    ]
    resolved_map_ids = [
        row["record_id"] for row in map_records if isinstance(row.get("record_id"), str)
    ]
    if resolved_list_ids != list_ids or resolved_map_ids != map_ids:
        raise ValueError(f"{context} map/list ID rosters differ from retained record rows")
    expected_unresolved_list = [
        row for row in list_records if not isinstance(row.get("record_id"), str)
    ]
    expected_unresolved_map = [
        row for row in map_records if not isinstance(row.get("record_id"), str)
    ]
    if unresolved_list != expected_unresolved_list or unresolved_map != expected_unresolved_map:
        raise ValueError(f"{context} unresolved map/list partitions are inconsistent")
    if map_surface_present != bool(expected_ids):
        raise ValueError(f"{context} map-surface presence differs from the fixture state")

    recomputed_detail_integrity = (
        resolved_list_ids == list_ids
        and resolved_map_ids == map_ids
        and expected_unresolved_list == unresolved_list
        and expected_unresolved_map == unresolved_map
        and len(list_records) == len(list_ids) + len(unresolved_list)
        and len(map_records) == len(map_ids) + len(unresolved_map)
    )
    declared_detail_integrity = _strict_bool(
        evidence, "detail_integrity", f"{context} map evidence"
    )
    if declared_detail_integrity != recomputed_detail_integrity:
        raise ValueError(f"{context} map detail-integrity aggregate differs from raw rows")

    visible_resolved_markers = [
        row
        for row in map_records
        if isinstance(row.get("record_id"), str)
        and row["observed_visible"] is True
        and isinstance(row.get("observed_center_css_px"), dict)
    ]
    unique_centers = {
        (
            row["observed_center_css_px"]["x"],
            row["observed_center_css_px"]["y"],
        )
        for row in visible_resolved_markers
    }
    expected_marker_count = len(map_ids)
    placement_sanity = (
        len(visible_resolved_markers) == expected_marker_count
        and len(unique_centers) == expected_marker_count
    )
    recomputed_placement = {
        "scope": "css_pixel_center_uniqueness_only_not_geospatial_accuracy",
        "observed_visible_marker_count": len(visible_resolved_markers),
        "observed_unique_visible_center_count": len(unique_centers),
        "expected_rendered_marker_count": expected_marker_count,
        "sanity_passed": placement_sanity,
    }
    if evidence.get("marker_placement_sanity") != recomputed_placement:
        raise ValueError(f"{context} marker-placement aggregate differs from raw rows")

    def exact_roster(expected: list[str], observed: list[str]) -> bool:
        return (
            len(expected) == len(observed)
            and len(set(expected)) == len(expected)
            and len(set(observed)) == len(observed)
            and sorted(expected) == sorted(observed)
        )

    recomputed = (
        (not expected_pagination["map_surface_required"] or map_surface_present)
        and exact_roster(expected_ids, list_ids)
        and exact_roster(expected_ids, map_ids)
        and not unresolved_list
        and not unresolved_map
    )
    declared = _strict_bool(evidence, "map_list_parity", f"{context} map evidence")
    if declared != recomputed:
        raise ValueError(f"{context} map/list parity aggregate differs from raw rosters")
    return declared, declared_detail_integrity, placement_sanity


def _frontend_surface_row(
    row: Any,
    *,
    state: dict[str, Any],
    viewport: dict[str, Any],
    protocol: dict[str, Any],
    report_path: Path,
    base_url: str,
) -> dict[str, Any]:
    context = f"frontend surface {state['id']}::{viewport['id']}"
    if not isinstance(row, dict):
        raise ValueError(f"{context} row must be an object")
    _require_exact_keys(
        row,
        {
            "state_id",
            "viewport_id",
            "viewport",
            "status",
            "screenshot",
            "axe",
            "layout",
            "map_evidence",
            "runtime",
            "checks",
            "qualified",
        },
        context=context,
    )
    if row.get("state_id") != state["id"] or row.get("viewport_id") != viewport["id"]:
        raise ValueError(f"{context} row roster or order is inconsistent")
    expected_viewport = {
        "width": viewport["width"],
        "height": viewport["height"],
        "device_scale_factor": viewport["device_scale_factor"],
        "is_mobile": viewport["is_mobile"],
    }
    if row.get("viewport") != expected_viewport:
        raise ValueError(f"{context} viewport differs from the protocol")
    if row.get("status") != "complete":
        raise ValueError(f"{context} is incomplete and cannot enter the benchmark")

    screenshot = row.get("screenshot")
    if not isinstance(screenshot, dict):
        raise ValueError(f"{context} screenshot evidence is missing")
    _require_exact_keys(
        screenshot,
        {
            "path",
            "sha256",
            "bytes",
            "format",
            "signature_hex",
            "width_px",
            "height_px",
        },
        context=f"{context} screenshot evidence",
    )
    expected_screenshot_path = (
        report_path.parent / "screenshots" / f"{state['id']}--{viewport['id']}.png"
    )
    screenshot_root = report_path.parent / "screenshots"
    if screenshot_root.is_symlink() or expected_screenshot_path.is_symlink():
        raise ValueError(f"{context} screenshot path cannot use a symlink")
    resolved_screenshot_root = screenshot_root.resolve()
    expected_screenshot_path = expected_screenshot_path.resolve()
    if expected_screenshot_path.parent != resolved_screenshot_root:
        raise ValueError(f"{context} screenshot escapes its capture-owned directory")
    expected_screenshot_reference = (
        expected_screenshot_path.relative_to(ROOT).as_posix()
        if expected_screenshot_path.is_relative_to(ROOT)
        else f"screenshots/{state['id']}--{viewport['id']}.png"
    )
    declared_screenshot_path = screenshot.get("path")
    if (
        not isinstance(declared_screenshot_path, str)
        or Path(declared_screenshot_path).is_absolute()
        or ".." in Path(declared_screenshot_path).parts
        or not declared_screenshot_path.endswith(".png")
    ):
        raise ValueError(f"{context} screenshot path is not a safe relative PNG path")
    if screenshot.get("path") != expected_screenshot_reference:
        raise ValueError(f"{context} screenshot path is not canonical")
    if not expected_screenshot_path.is_file():
        raise ValueError(f"{context} screenshot file is missing")
    declared_screenshot_bytes = _strict_int(
        screenshot, "bytes", f"{context} screenshot evidence", minimum=1
    )
    if declared_screenshot_bytes != expected_screenshot_path.stat().st_size:
        raise ValueError(f"{context} screenshot byte count differs from the file")
    _require_digest(screenshot.get("sha256"), context=f"{context} screenshot digest")
    if screenshot["sha256"] != file_sha256(expected_screenshot_path):
        raise ValueError(f"{context} screenshot digest differs from the file")
    if (
        screenshot.get("format") != "png"
        or screenshot.get("signature_hex") != "89504e470d0a1a0a"
        or expected_screenshot_path.read_bytes()[:8].hex() != screenshot["signature_hex"]
    ):
        raise ValueError(f"{context} screenshot PNG signature is invalid")
    try:
        with Image.open(expected_screenshot_path) as screenshot_image:
            if screenshot_image.format != "PNG":
                raise ValueError(f"{context} screenshot is not a PNG")
            screenshot_size = screenshot_image.size
            screenshot_image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"{context} screenshot is not a valid decoded PNG") from error
    expected_pixel_width = viewport["width"] * viewport["device_scale_factor"]
    minimum_pixel_height = viewport["height"] * viewport["device_scale_factor"]
    declared_pixel_size = (
        _strict_int(screenshot, "width_px", f"{context} screenshot evidence", minimum=1),
        _strict_int(screenshot, "height_px", f"{context} screenshot evidence", minimum=1),
    )
    if declared_pixel_size != screenshot_size:
        raise ValueError(f"{context} screenshot dimensions differ from decoded PNG")
    if (
        screenshot_size[0] != expected_pixel_width
        or screenshot_size[1] < minimum_pixel_height
        or screenshot_size[1] > minimum_pixel_height * 20
    ):
        raise ValueError(
            f"{context} screenshot dimensions are outside the full-page viewport bounds"
        )

    axe_count, _ = _frontend_axe(row.get("axe"), context=context)
    layout_count, layout = _frontend_layout(
        row.get("layout"),
        context=context,
        thresholds=protocol["surface_thresholds"],
    )
    map_parity, map_detail_integrity, map_marker_placement_sanity = _frontend_map_evidence(
        row.get("map_evidence"),
        context=context,
        state_id=state["id"],
        protocol=protocol,
    )
    css_runtime_count, runtime_violation_count, runtime = _frontend_runtime(
        row.get("runtime"),
        context=context,
        state=state,
        base_url=base_url,
        thresholds=protocol["surface_thresholds"],
    )
    thresholds = protocol["surface_thresholds"]
    expected_checks: dict[str, bool | str] = {
        "axe_engine_version_bound": True,
        "axe_wcag_a_aa_findings_within_limit": axe_count
        <= thresholds["axe_wcag_a_aa_findings_max"],
        "no_document_horizontal_overflow": layout["document_horizontal_overflow_px"]
        <= thresholds["document_horizontal_overflow_max_px"],
        "clipped_text_within_limit": len(layout["clipped_text_elements"])
        <= thresholds["clipped_text_elements_max"],
        "stylesheets_accessible": len(layout["inaccessible_stylesheets"])
        <= thresholds["inaccessible_stylesheets_max"],
        "stylesheets_loaded": len(runtime["request_derived"]["stylesheet_load_failures"])
        <= thresholds["stylesheet_load_failures_max"],
        "interactive_elements_styled": len(layout["unstyled_interactive_elements"])
        <= thresholds["unstyled_interactive_elements_max"],
        "interactive_targets_sized": len(layout["undersized_interactive_elements"])
        <= thresholds["undersized_interactive_elements_max"],
        "text_sizes_within_protocol": len(layout["undersized_text_elements"])
        <= thresholds["undersized_text_elements_max"],
        "console_clean": len(runtime["unexpected_console_errors"])
        <= thresholds["console_errors_max"],
        "page_errors_clean": len(runtime["page_errors"]) <= thresholds["page_errors_max"],
        "request_origins_allowed": len(runtime["request_derived"]["unexpected_request_origins"])
        <= thresholds["unexpected_request_origins_max"],
        "no_unallowlisted_failed_requests": not runtime["request_derived"][
            "unallowlisted_failed_requests"
        ],
        "no_direct_third_party_tile_requests": len(
            runtime["request_derived"]["direct_third_party_tile_requests"]
        )
        <= thresholds["direct_third_party_tile_requests_max"],
        "map_list_parity": map_parity if map_parity is not None else "not_applicable",
        "map_detail_integrity": (
            map_detail_integrity if map_detail_integrity is not None else "not_applicable"
        ),
        "map_marker_placement_sanity": (
            map_marker_placement_sanity
            if map_marker_placement_sanity is not None
            else "not_applicable"
        ),
    }
    checks = row.get("checks")
    if checks != expected_checks:
        raise ValueError(f"{context} checks differ from raw evidence")
    qualified = all(
        value is True or value == "not_applicable" for value in expected_checks.values()
    )
    if type(row.get("qualified")) is not bool or row["qualified"] != qualified:
        raise ValueError(f"{context} qualification differs from raw evidence")
    return {
        "qualified": qualified,
        "axe_finding_count": axe_count,
        "css_layout_violation_count": layout_count + css_runtime_count,
        "runtime_violation_count": runtime_violation_count,
        "direct_third_party_tile_request_count": len(
            runtime["request_derived"]["direct_third_party_tile_requests"]
        ),
        "map_list_parity": map_parity,
        "map_detail_integrity": map_detail_integrity,
        "map_marker_placement_sanity": map_marker_placement_sanity,
    }
