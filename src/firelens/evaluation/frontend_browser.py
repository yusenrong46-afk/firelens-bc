"""Browser runtime, console, accessibility, and layout evidence validation."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from firelens.evaluation.common import (
    ROOT,
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
from firelens.evaluation.frontend_protocol import (
    _require_object_list,
    _require_string_list,
)


def _frontend_console_event(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    _require_exact_keys(value, {"text", "location"}, context=context)
    _require_nonempty_string(value.get("text"), context=f"{context} text")
    location = value.get("location")
    if not isinstance(location, dict):
        raise ValueError(f"{context} location must be an object")
    _require_exact_keys(
        location,
        {"url", "line", "column", "lineNumber", "columnNumber"},
        context=f"{context} location",
    )
    if not isinstance(location.get("url"), str):
        raise ValueError(f"{context} location URL must be a string")
    for key in ("line", "column", "lineNumber", "columnNumber"):
        if isinstance(location.get(key), bool) or not isinstance(location.get(key), int):
            raise ValueError(f"{context} location {key} must be an integer")
    if (
        location["line"] != location["lineNumber"]
        or location["column"] != location["columnNumber"]
    ):
        raise ValueError(f"{context} location aliases are inconsistent")
    return value


def _frontend_http_failure(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    _require_exact_keys(value, {"url", "status", "question"}, context=context)
    _require_nonempty_string(value.get("url"), context=f"{context} URL")
    _strict_int(value, "status", context, minimum=400, maximum=599)
    _require_nonempty_string(value.get("question"), context=f"{context} question")
    return value


def _frontend_classify_console_errors(
    console_errors: list[dict[str, Any]], expected_http_failures: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    remaining = [dict(failure) for failure in expected_http_failures]
    expected: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    pattern = re.compile(
        r"Failed to load resource: the server responded with a status of (\d+)"
    )
    for event in console_errors:
        match = pattern.search(event["text"])
        status = int(match.group(1)) if match else None
        location_url = event["location"].get("url") or None
        match_index = next(
            (
                index
                for index, failure in enumerate(remaining)
                if failure["status"] == status
                and bool(location_url)
                and location_url == failure["url"]
            ),
            None,
        )
        if match_index is None:
            unexpected.append(event)
        else:
            expected.append({"event": event, "expected_http_failure": remaining[match_index]})
            remaining.pop(match_index)
    return expected, unexpected


def _frontend_axe(axe: Any, *, context: str) -> tuple[int, dict[str, Any]]:
    if not isinstance(axe, dict):
        raise ValueError(f"{context} axe evidence must be an object")
    _require_exact_keys(
        axe,
        {
            "engine_version",
            "installed_package_version",
            "engine_version_matches_installed_package",
            "finding_count",
            "impact_counts",
            "findings",
        },
        context=f"{context} axe evidence",
    )
    engine_version = _require_nonempty_string(
        axe.get("engine_version"), context=f"{context} axe engine version"
    )
    installed_version = _require_nonempty_string(
        axe.get("installed_package_version"),
        context=f"{context} installed axe package version",
    )
    try:
        lock = json.loads((ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))
        locked_version = str(lock["packages"]["node_modules/axe-core"]["version"])
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError("frontend axe-core lock identity is unavailable") from error
    version_matches = _strict_bool(
        axe,
        "engine_version_matches_installed_package",
        f"{context} axe evidence",
    )
    if (
        engine_version != installed_version
        or installed_version != locked_version
        or version_matches is not True
    ):
        raise ValueError(f"{context} axe engine is not bound to the locked package")
    count = _strict_int(axe, "finding_count", f"{context} axe evidence", minimum=0)
    findings = _require_object_list(axe.get("findings"), context=f"{context} axe findings")
    if len(findings) != count:
        raise ValueError(f"{context} axe aggregate differs from raw findings")
    impact_counts = axe.get("impact_counts")
    if not isinstance(impact_counts, dict):
        raise ValueError(f"{context} axe impact counts must be an object")
    expected_impact_keys = {"critical", "serious", "moderate", "minor", "unknown"}
    _require_exact_keys(
        impact_counts,
        expected_impact_keys,
        context=f"{context} axe impact counts",
    )
    for impact_key in expected_impact_keys:
        _strict_int(
            impact_counts,
            impact_key,
            f"{context} axe impact counts",
            minimum=0,
        )
    recomputed_impact_counts = {impact: 0 for impact in expected_impact_keys}
    wcag_tags = {"wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"}
    for finding_index, finding in enumerate(findings):
        finding_context = f"{context} axe finding {finding_index}"
        _require_exact_keys(
            finding,
            {"id", "impact", "tags", "help", "help_url", "nodes"},
            context=finding_context,
        )
        for key in ("id", "help", "help_url"):
            _require_nonempty_string(finding.get(key), context=f"{finding_context} {key}")
        impact = finding.get("impact")
        if impact not in {"critical", "serious", "moderate", "minor", None}:
            raise ValueError(f"{finding_context} impact is invalid")
        recomputed_impact_counts[impact if isinstance(impact, str) else "unknown"] += 1
        tags = _require_string_list(
            finding.get("tags"), context=f"{finding_context} tags", unique=True
        )
        if tags != sorted(tags) or not wcag_tags.intersection(tags):
            raise ValueError(f"{finding_context} tags are not canonical WCAG A/AA evidence")
        nodes = _require_object_list(finding.get("nodes"), context=f"{finding_context} nodes")
        if not nodes:
            raise ValueError(f"{finding_context} has no affected nodes")
        for node_index, node in enumerate(nodes):
            _require_exact_keys(
                node,
                {"target", "failure_summary"},
                context=f"{finding_context} node {node_index}",
            )
            targets = node.get("target")
            if (
                not isinstance(targets, list)
                or not targets
                or not all(isinstance(target, str) and target for target in targets)
            ):
                raise ValueError(f"{finding_context} node {node_index} has no targets")
            if node.get("failure_summary") is not None and not isinstance(
                node.get("failure_summary"), str
            ):
                raise ValueError(
                    f"{finding_context} node {node_index} failure_summary is invalid"
                )
    if impact_counts != recomputed_impact_counts:
        raise ValueError(f"{context} axe impact aggregate differs from raw findings")
    return count, axe


def _frontend_layout(
    layout: Any, *, context: str, thresholds: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    if not isinstance(layout, dict):
        raise ValueError(f"{context} layout evidence must be an object")
    _require_exact_keys(
        layout,
        {
            "document_horizontal_overflow_px",
            "clipped_text_elements",
            "undersized_text_elements",
            "stylesheet_count",
            "css_rule_count",
            "inaccessible_stylesheets",
            "undersized_interactive_elements",
            "unstyled_interactive_elements",
            "app_font_family",
        },
        context=f"{context} layout evidence",
    )
    overflow = _strict_number(
        layout,
        "document_horizontal_overflow_px",
        f"{context} layout evidence",
        minimum=0,
    )
    _strict_int(layout, "stylesheet_count", f"{context} layout evidence", minimum=0)
    _strict_int(layout, "css_rule_count", f"{context} layout evidence", minimum=0)
    _require_nonempty_string(
        layout.get("app_font_family"), context=f"{context} app font family"
    )
    clipped = _require_object_list(
        layout.get("clipped_text_elements"), context=f"{context} clipped text rows"
    )
    undersized_text = _require_object_list(
        layout.get("undersized_text_elements"),
        context=f"{context} undersized text rows",
    )
    inaccessible_stylesheets = _require_string_list(
        layout.get("inaccessible_stylesheets"),
        context=f"{context} inaccessible stylesheets",
    )
    undersized_interactive = _require_object_list(
        layout.get("undersized_interactive_elements"),
        context=f"{context} undersized interactive rows",
    )
    unstyled_interactive = _require_object_list(
        layout.get("unstyled_interactive_elements"),
        context=f"{context} unstyled interactive rows",
    )
    for index, row in enumerate(clipped):
        _require_exact_keys(
            row,
            {
                "tag",
                "class_name",
                "overflow_x",
                "overflow_y",
                "clipped_x_px",
                "clipped_y_px",
            },
            context=f"{context} clipped row {index}",
        )
    for index, row in enumerate(undersized_text):
        _require_exact_keys(
            row,
            {"tag", "class_name", "font_size_px", "required_font_size_px", "category"},
            context=f"{context} undersized text row {index}",
        )
    for index, row in enumerate(undersized_interactive):
        _require_exact_keys(
            row,
            {"tag", "label", "width", "height"},
            context=f"{context} undersized interactive row {index}",
        )
    for index, row in enumerate(unstyled_interactive):
        _require_exact_keys(
            row,
            {"tag", "label"},
            context=f"{context} unstyled interactive row {index}",
        )
    violation_count = (
        int(overflow > thresholds["document_horizontal_overflow_max_px"])
        + len(clipped)
        + len(undersized_text)
        + len(inaccessible_stylesheets)
        + len(undersized_interactive)
        + len(unstyled_interactive)
    )
    return violation_count, layout


def _frontend_runtime(
    runtime: Any,
    *,
    context: str,
    state: dict[str, Any],
    base_url: str,
    thresholds: dict[str, Any],
) -> tuple[int, int, dict[str, Any]]:
    if not isinstance(runtime, dict):
        raise ValueError(f"{context} runtime evidence must be an object")
    _require_exact_keys(
        runtime,
        {
            "console_errors",
            "expected_console_errors",
            "unexpected_console_errors",
            "expected_http_failures",
            "page_errors",
            "request_events",
            "request_derived",
        },
        context=f"{context} runtime evidence",
    )
    console_errors = _require_object_list(
        runtime.get("console_errors"), context=f"{context} console errors"
    )
    for index, event in enumerate(console_errors):
        _frontend_console_event(event, context=f"{context} console error {index}")
    expected_http_failures = _require_object_list(
        runtime.get("expected_http_failures"),
        context=f"{context} expected HTTP failures",
    )
    for index, failure in enumerate(expected_http_failures):
        _frontend_http_failure(failure, context=f"{context} expected HTTP failure {index}")
    expected_failure_roster = (
        [
            {
                "url": f"{base_url}/api/v1/ask",
                "status": 503,
                "question": "surface:unavailable",
            }
        ]
        if state["id"] == "provider_failure"
        else []
    )
    if expected_http_failures != expected_failure_roster:
        raise ValueError(f"{context} expected HTTP failure roster is not canonical")
    expected_console, unexpected_console = _frontend_classify_console_errors(
        console_errors, expected_http_failures
    )
    if len(expected_console) != len(expected_http_failures):
        raise ValueError(f"{context} expected HTTP failure has no exact console match")
    if runtime.get("expected_console_errors") != expected_console:
        raise ValueError(f"{context} expected-console classification is inconsistent")
    if runtime.get("unexpected_console_errors") != unexpected_console:
        raise ValueError(f"{context} unexpected-console classification is inconsistent")
    page_errors = _require_string_list(
        runtime.get("page_errors"), context=f"{context} page errors"
    )
    request_events = _require_object_list(
        runtime.get("request_events"), context=f"{context} request events"
    )
    for index, event in enumerate(request_events):
        event_context = f"{context} request event {index}"
        _require_exact_keys(
            event,
            {
                "sequence_index",
                "method",
                "url",
                "origin",
                "resource_type",
                "response_status",
                "failure",
            },
            context=event_context,
        )
        if _strict_int(event, "sequence_index", event_context, minimum=0) != index:
            raise ValueError(f"{context} request event sequence is not contiguous")
        method = _require_nonempty_string(
            event.get("method"), context=f"{event_context} method"
        )
        if method != method.upper():
            raise ValueError(f"{event_context} method is not canonical")
        url = _require_nonempty_string(event.get("url"), context=f"{event_context} URL")
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc or parsed.fragment:
            raise ValueError(f"{event_context} URL is not canonical")
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        if query_items != sorted(query_items):
            raise ValueError(f"{event_context} query parameters are not canonical")
        expected_origin = (
            f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme in {"http", "https"} else None
        )
        if event.get("origin") != expected_origin:
            raise ValueError(f"{event_context} origin differs from its URL")
        _require_nonempty_string(
            event.get("resource_type"), context=f"{event_context} resource type"
        )
        response_status = event.get("response_status")
        if response_status is not None and (
            isinstance(response_status, bool)
            or not isinstance(response_status, int)
            or not 100 <= response_status <= 599
        ):
            raise ValueError(f"{event_context} response status is invalid")
        failure_message = event.get("failure")
        if failure_message is not None:
            _require_nonempty_string(failure_message, context=f"{event_context} failure")
        if int(response_status is not None) + int(failure_message is not None) != 1:
            raise ValueError(f"{event_context} must retain exactly one request outcome")

    request_origins = sorted(
        {event["origin"] for event in request_events if isinstance(event["origin"], str)}
    )
    unexpected_origins = [
        origin
        for origin in request_origins
        if origin not in thresholds["allowed_request_origins"]
    ]
    failed_requests = [event for event in request_events if event["failure"] is not None]
    unallowlisted_failed_requests = [
        event
        for event in failed_requests
        if event["url"] not in thresholds["allowed_failed_request_urls"]
    ]
    stylesheet_failures = [
        event
        for event in request_events
        if event["resource_type"] == "stylesheet"
        and (
            event["failure"] is not None
            or (isinstance(event["response_status"], int) and event["response_status"] >= 400)
        )
    ]
    direct_tiles = [
        event
        for event in request_events
        if (urlsplit(event["url"]).hostname or "").endswith(".tile.openstreetmap.org")
    ]
    expected_derived = {
        "request_origins": request_origins,
        "unexpected_request_origins": unexpected_origins,
        "failed_requests": failed_requests,
        "unallowlisted_failed_requests": unallowlisted_failed_requests,
        "stylesheet_load_failures": stylesheet_failures,
        "direct_third_party_tile_requests": direct_tiles,
    }
    if runtime.get("request_derived") != expected_derived:
        raise ValueError(f"{context} request classifications differ from raw events")
    css_runtime_violations = len(stylesheet_failures)
    runtime_violations = (
        len(unexpected_console)
        + len(page_errors)
        + len(unexpected_origins)
        + len(unallowlisted_failed_requests)
    )
    return css_runtime_violations, runtime_violations, runtime
