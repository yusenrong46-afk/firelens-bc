"""Hard-probe, live-SLO, and model-review qualification report validation."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

import yaml

from firelens.evaluation.common import (
    ROOT,
)
from firelens.evaluation.common import (
    p95 as _p95,
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


def _require_object(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _hard_probe(
    report: dict[str, Any] | None, *, expected_mode: Literal["offline", "qualified"]
) -> dict[str, Any]:
    if report is None:
        return {"status": "not_run"}
    if report.get("schema_version") != "firelens_hard_probe_report.v1":
        raise ValueError("hard-probe report uses an unsupported schema_version")
    manifest = report.get("manifest")
    summary = report.get("summary")
    rows = report.get("results")
    if (
        not isinstance(manifest, dict)
        or not isinstance(summary, dict)
        or not isinstance(rows, list)
    ):
        raise ValueError("hard-probe report is missing its manifest, summary, or results")
    if manifest.get("mode") != expected_mode:
        raise ValueError(f"hard-probe report must use {expected_mode} mode")
    expected_boundary = "offline_double" if expected_mode == "offline" else "openrouter"
    if manifest.get("provider_boundary") != expected_boundary:
        raise ValueError("hard-probe report uses the wrong provider boundary")
    executed = _strict_int(summary, "executed", "hard-probe summary", minimum=0)
    passed = _strict_int(summary, "passed", "hard-probe summary", minimum=0)
    failed = _strict_int(summary, "failed", "hard-probe summary", minimum=0)
    if executed != 105 or len(rows) != 105 or passed + failed != executed:
        raise ValueError("hard-probe report must contain exactly 105 completed cases")
    case_ids: set[str] = set()
    passed_rows = 0
    latencies: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("hard-probe result must be an object")
        case_id = str(row.get("id") or "")
        if not case_id or case_id in case_ids:
            raise ValueError("hard-probe result IDs must be present and unique")
        case_ids.add(case_id)
        if _strict_bool(row, "passed", f"hard-probe result {case_id}"):
            passed_rows += 1
        latencies.append(
            _strict_number(row, "latency_ms", f"hard-probe result {case_id}", minimum=0)
        )
    if passed_rows != passed:
        raise ValueError("hard-probe summary does not match case-level pass results")
    dataset_payload = yaml.safe_load(
        (ROOT / "data/evaluation/hard_probe.v1.yaml").read_text(encoding="utf-8")
    )
    expected_priorities = {
        str(case["id"]): str(case["priority"]) for case in dataset_payload["cases"]
    }
    if case_ids != set(expected_priorities) or any(
        row.get("priority") != expected_priorities.get(str(row.get("id"))) for row in rows
    ):
        raise ValueError(
            "hard-probe case IDs or dataset priorities do not match the frozen case roster"
        )
    critical_failures = sum(
        1 for row in rows if row.get("priority") == "CRITICAL" and row.get("passed") is not True
    )
    cost_usd = _strict_number(summary, "cost_usd", "hard-probe summary", minimum=0)
    if expected_mode == "offline" and cost_usd != 0:
        raise ValueError("offline hard-probe report must have zero model cost")
    return {
        "status": "complete",
        "mode": manifest.get("mode"),
        "provider_boundary": manifest.get("provider_boundary"),
        "commit": manifest.get("commit"),
        "dataset_sha256": manifest.get("dataset_sha256"),
        "corpus_sha256": manifest.get("corpus_sha256"),
        "vector_matrix_sha256": manifest.get("vector_matrix_sha256"),
        "document_context_sha256": manifest.get("document_context_sha256"),
        "repairs_sha256": manifest.get("repairs_sha256"),
        "configuration_sha256": manifest.get("configuration_sha256"),
        "runtime_configuration": manifest.get("runtime_configuration"),
        "models": manifest.get("models"),
        "executed": executed,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / executed if executed else None,
        "critical_failures": critical_failures,
        "p95_latency_ms": _p95(latencies),
        "cost_usd": cost_usd,
    }


def _validated_public_live_rows(
    rows: Any,
    *,
    context: str,
    include_kind: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{context} must be a list")
    required = {
        "result_id",
        "authority",
        "source_url",
        "source_updated_at",
        "retrieved_at",
        "status",
    }
    if include_kind:
        required.add("kind")
    validated: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_context = f"{context} row {index}"
        if not isinstance(row, dict):
            raise ValueError(f"{row_context} must be an object")
        _require_exact_keys(row, required, context=row_context)
        for field in ("result_id", "authority", "status"):
            _require_nonempty_string(row.get(field), context=f"{row_context} {field}")
        source_url = _require_nonempty_string(
            row.get("source_url"), context=f"{row_context} source_url"
        )
        if not source_url.startswith("https://"):
            raise ValueError(f"{row_context} source_url must use HTTPS")
        _require_timestamp(
            row.get("source_updated_at"), context=f"{row_context} source_updated_at"
        )
        _require_timestamp(row.get("retrieved_at"), context=f"{row_context} retrieved_at")
        if include_kind and row.get("kind") not in {
            "incident",
            "perimeter",
            "evacuation",
        }:
            raise ValueError(f"{row_context} kind is not a canonical live layer")
        validated.append(row)
    return validated


def _validated_id_status_rows(rows: Any, *, context: str) -> list[tuple[str, str]]:
    if not isinstance(rows, list):
        raise ValueError(f"{context} must be a list")
    pairs: list[tuple[str, str]] = []
    for index, row in enumerate(rows):
        row_context = f"{context} row {index}"
        if not isinstance(row, dict):
            raise ValueError(f"{row_context} must be an object")
        _require_exact_keys(row, {"result_id", "status"}, context=row_context)
        pairs.append(
            (
                _require_nonempty_string(
                    row.get("result_id"), context=f"{row_context} result_id"
                ),
                _require_nonempty_string(row.get("status"), context=f"{row_context} status"),
            )
        )
    if len(pairs) != len(set(pairs)):
        raise ValueError(f"{context} contains duplicate ID/status pairs")
    return pairs


def _live(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"status": "not_run"}
    _require_exact_keys(
        report,
        {
            "report_version",
            "evidence_schema_version",
            "generated_at",
            "commit",
            "source_urls",
            "cold",
            "chat_map",
            "near_me",
            "cached_api",
            "checks",
            "elapsed_seconds",
            "qualified",
        },
        context="live qualification report",
    )
    if report.get("report_version") != "firelens.live_qualification.v2":
        raise ValueError("live qualification uses an unsupported report_version")
    if report.get("evidence_schema_version") != "firelens.live_qualification.evidence.v2":
        raise ValueError("live qualification raw evidence uses an unsupported schema")
    _require_timestamp(report.get("generated_at"), context="live qualification generated_at")
    commit = _require_nonempty_string(report.get("commit"), context="live qualification commit")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("live qualification commit must be a full lowercase Git SHA")
    _strict_number(report, "elapsed_seconds", "live qualification report", minimum=0)
    checks = _require_object(report.get("checks"), context="live checks")
    cold = _require_object(report.get("cold"), context="live cold result")
    cached = _require_object(report.get("cached_api"), context="live cached API")
    chat_map = _require_object(report.get("chat_map"), context="live chat/map")
    near_me = _require_object(report.get("near_me"), context="live near-me")
    expected_checks = {
        "all_official_layers_available",
        "metadata_complete",
        "chat_map_records_match",
        "all_api_requests_succeeded",
        "cached_p95_within_target",
        "near_me_contract_valid",
    }
    if set(checks) != expected_checks or not all(
        type(value) is bool for value in checks.values()
    ):
        raise ValueError("live qualification checks must be strict booleans")
    source_urls = report.get("source_urls")
    if (
        not isinstance(source_urls, dict)
        or set(source_urls) != {"incident", "perimeter", "evacuation"}
        or not all(
            isinstance(url, str) and url.startswith("https://") for url in source_urls.values()
        )
    ):
        raise ValueError("live qualification does not bind all official source URLs")
    _require_exact_keys(
        cold,
        {
            "latency_ms",
            "result_count",
            "requested_layers",
            "unavailable_layers",
            "records",
            "metadata_complete",
        },
        context="live cold result",
    )
    cold_latency = _strict_number(cold, "latency_ms", "live cold result", minimum=0)
    cold_count = _strict_int(cold, "result_count", "live cold result", minimum=0)
    canonical_cold_layers = ["incident", "perimeter", "evacuation"]
    if cold.get("requested_layers") != canonical_cold_layers:
        raise ValueError("live qualification cold layer roster differs from the protocol")
    unavailable_layers = cold.get("unavailable_layers")
    if (
        not isinstance(unavailable_layers, list)
        or len(unavailable_layers) != len(set(unavailable_layers))
        or any(layer not in canonical_cold_layers for layer in unavailable_layers)
    ):
        raise ValueError("live qualification unavailable layer evidence is invalid")
    cold_records = _validated_public_live_rows(
        cold.get("records"), context="live cold records", include_kind=True
    )
    if cold_count != len(cold_records):
        raise ValueError("live cold result_count differs from its raw records")
    metadata_complete = all(
        all(
            record[field]
            for field in (
                "authority",
                "source_url",
                "source_updated_at",
                "retrieved_at",
                "status",
            )
        )
        for record in cold_records
    )
    if _strict_bool(cold, "metadata_complete", "live cold result") != metadata_complete:
        raise ValueError("live cold metadata flag differs from its raw records")

    _require_exact_keys(
        chat_map,
        {
            "chat_request",
            "map_request",
            "chat_status_code",
            "map_status_code",
            "chat_record_count",
            "map_record_count",
            "chat_records",
            "map_records",
            "matching_ids_and_statuses",
            "map_records_sha256",
        },
        context="live chat/map result",
    )
    if chat_map.get("chat_request") != {
        "method": "POST",
        "path": "/api/v1/ask",
        "question": "Are there active wildfires in BC currently?",
    }:
        raise ValueError("live chat request differs from the canonical protocol")
    if chat_map.get("map_request") != {
        "method": "GET",
        "path": "/api/v1/live/map",
        "layers": ["incidents"],
    }:
        raise ValueError("live map request differs from the canonical protocol")
    chat_status = _strict_int(
        chat_map, "chat_status_code", "live chat/map result", minimum=100, maximum=599
    )
    map_status = _strict_int(
        chat_map, "map_status_code", "live chat/map result", minimum=100, maximum=599
    )
    chat_pairs = _validated_id_status_rows(
        chat_map.get("chat_records"), context="live chat records"
    )
    map_pairs = _validated_id_status_rows(
        chat_map.get("map_records"), context="live map records"
    )
    if _strict_int(chat_map, "chat_record_count", "live chat/map result", minimum=0) != len(
        chat_pairs
    ):
        raise ValueError("live chat record count differs from its raw records")
    if _strict_int(chat_map, "map_record_count", "live chat/map result", minimum=0) != len(
        map_pairs
    ):
        raise ValueError("live map record count differs from its raw records")
    records_match = bool(chat_pairs) and set(chat_pairs).issubset(set(map_pairs))
    if (
        _strict_bool(chat_map, "matching_ids_and_statuses", "live chat/map result")
        != records_match
    ):
        raise ValueError("live chat/map match flag differs from its raw records")
    map_digest = hashlib.sha256(
        json.dumps(sorted(map_pairs), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if chat_map.get("map_records_sha256") != map_digest:
        raise ValueError("live map record digest differs from its raw records")

    _require_exact_keys(
        near_me,
        {
            "request",
            "status_code",
            "requested_radius_km",
            "requested_layers",
            "resolved_location",
            "viewport",
            "pagination",
            "result_count",
            "records",
            "unavailable_layers",
            "layer_statuses",
            "official_fallback_urls",
        },
        context="live near-me result",
    )
    canonical_near_me_body = {
        "location": {"latitude": 49.28, "longitude": -123.12, "radius_km": 50.0},
        "layers": canonical_cold_layers,
        "page": 1,
        "page_size": 200,
    }
    if near_me.get("request") != {
        "method": "POST",
        "path": "/api/v1/live/nearby",
        "body": canonical_near_me_body,
    }:
        raise ValueError("live near-me request differs from the canonical protocol")
    near_me_status = _strict_int(
        near_me,
        "status_code",
        "live near-me result",
        minimum=100,
        maximum=599,
    )
    requested_radius = _strict_number(
        near_me,
        "requested_radius_km",
        "live near-me result",
        minimum=1,
        maximum=200,
    )
    requested_layers = near_me.get("requested_layers")
    resolved_location = near_me.get("resolved_location")
    viewport = near_me.get("viewport")
    pagination = near_me.get("pagination")
    if requested_layers != canonical_cold_layers or requested_radius != 50.0:
        raise ValueError("live near-me response differs from the requested scope")
    if resolved_location != {"latitude": 49.28, "longitude": -123.12}:
        raise ValueError("live near-me response differs from the coarse requested location")
    if not isinstance(viewport, dict):
        raise ValueError("live near-me viewport must be an object")
    _require_exact_keys(
        viewport,
        {"west", "south", "east", "north"},
        context="live near-me viewport",
    )
    west = _strict_number(viewport, "west", "live near-me viewport", minimum=-180, maximum=180)
    south = _strict_number(viewport, "south", "live near-me viewport", minimum=-90, maximum=90)
    east = _strict_number(viewport, "east", "live near-me viewport", minimum=-180, maximum=180)
    north = _strict_number(viewport, "north", "live near-me viewport", minimum=-90, maximum=90)
    if not west < east or not south < north:
        raise ValueError("live near-me viewport must be ordered")
    if not isinstance(pagination, dict):
        raise ValueError("live near-me pagination must be an object")
    _require_exact_keys(
        pagination,
        {
            "page",
            "page_size",
            "total_results",
            "total_pages",
            "returned_results",
            "has_previous",
            "has_next",
        },
        context="live near-me pagination",
    )
    page = _strict_int(pagination, "page", "live near-me pagination", minimum=1)
    page_size = _strict_int(
        pagination, "page_size", "live near-me pagination", minimum=1, maximum=200
    )
    total_results = _strict_int(
        pagination, "total_results", "live near-me pagination", minimum=0
    )
    total_pages = _strict_int(pagination, "total_pages", "live near-me pagination", minimum=0)
    returned_results = _strict_int(
        pagination, "returned_results", "live near-me pagination", minimum=0
    )
    near_me_pairs = _validated_id_status_rows(
        near_me.get("records"), context="live near-me records"
    )
    near_me_count = _strict_int(near_me, "result_count", "live near-me result", minimum=0)
    expected_total_pages = math.ceil(total_results / page_size)
    expected_returned = min(page_size, total_results)
    pagination_consistent = bool(
        page == 1
        and page_size == 200
        and total_pages == expected_total_pages
        and returned_results == expected_returned
        and near_me_count == returned_results == len(near_me_pairs)
        and _strict_bool(pagination, "has_previous", "live near-me pagination") is False
        and _strict_bool(pagination, "has_next", "live near-me pagination")
        is (total_results > page_size)
    )
    near_unavailable = near_me.get("unavailable_layers")
    if (
        not isinstance(near_unavailable, list)
        or len(near_unavailable) != len(set(near_unavailable))
        or any(layer not in canonical_cold_layers for layer in near_unavailable)
    ):
        raise ValueError("live near-me unavailable-layer evidence is invalid")
    near_layer_statuses = near_me.get("layer_statuses")
    if not isinstance(near_layer_statuses, list) or len(near_layer_statuses) != len(
        canonical_cold_layers
    ):
        raise ValueError("live near-me layer-status evidence is incomplete")
    layer_status_count = 0
    layer_statuses_valid = True
    for index, raw_status in enumerate(near_layer_statuses):
        context = f"live near-me layer status {index}"
        if not isinstance(raw_status, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            raw_status,
            {
                "kind",
                "authority",
                "source_url",
                "available",
                "source_updated_at",
                "retrieved_at",
                "freshness",
                "matching_result_count",
            },
            context=context,
        )
        kind = canonical_cold_layers[index]
        if raw_status.get("kind") != kind:
            raise ValueError("live near-me layer statuses differ from requested layer order")
        available_status = _strict_bool(raw_status, "available", context)
        count = _strict_int(raw_status, "matching_result_count", context, minimum=0)
        layer_status_count += count
        authority = raw_status.get("authority")
        source_url = raw_status.get("source_url")
        if (
            not isinstance(authority, str)
            or not authority.strip()
            or not isinstance(source_url, str)
            or source_url != source_urls[kind]
        ):
            raise ValueError("live near-me layer authority or source URL is invalid")
        if available_status:
            _require_timestamp(
                raw_status.get("source_updated_at"),
                context=f"{context} source_updated_at",
            )
            _require_timestamp(
                raw_status.get("retrieved_at"),
                context=f"{context} retrieved_at",
            )
            if raw_status.get("freshness") not in {"fresh", "stale"}:
                raise ValueError("live near-me layer freshness is invalid")
        elif (
            raw_status.get("source_updated_at") is not None
            or raw_status.get("retrieved_at") is not None
            or raw_status.get("freshness") is not None
            or count
        ):
            raise ValueError("unavailable live near-me layer claims observations")
        layer_statuses_valid = layer_statuses_valid and (
            available_status == (kind not in near_unavailable)
        )
    fallbacks = near_me.get("official_fallback_urls")
    fallbacks_valid = bool(
        isinstance(fallbacks, list)
        and fallbacks
        and len(fallbacks) == len(set(fallbacks))
        and all(isinstance(url, str) and url.startswith("https://") for url in fallbacks)
    )
    near_me_contract_valid = bool(
        near_me_status == 200
        and pagination_consistent
        and fallbacks_valid
        and not near_unavailable
        and layer_statuses_valid
        and layer_status_count == total_results
    )

    _require_exact_keys(
        cached,
        {
            "p95_target_ms",
            "p95_latency_ms",
            "request_count",
            "requests",
            "by_concurrency",
        },
        context="live cached API",
    )
    p95_target = _strict_number(cached, "p95_target_ms", "live cached API", minimum=0.0000001)
    submitted_cached_p95 = _strict_number(
        cached, "p95_latency_ms", "live cached API", minimum=0
    )
    if _strict_int(cached, "request_count", "live cached API", minimum=0) != 26:
        raise ValueError("live qualification must contain the frozen 26 cached requests")
    cached_requests = cached.get("requests")
    if not isinstance(cached_requests, list) or len(cached_requests) != 26:
        raise ValueError("live qualification must retain all 26 cached request rows")
    expected_roster = [
        (concurrency, request_index)
        for concurrency in (1, 5, 20)
        for request_index in range(1, concurrency + 1)
    ]
    observed_roster: list[tuple[int, int]] = []
    cached_latencies: list[float] = []
    cached_statuses: list[int] = []
    grouped_rows: dict[int, list[dict[str, Any]]] = {1: [], 5: [], 20: []}
    request_keys = {
        "request_id",
        "method",
        "path",
        "layers",
        "concurrency",
        "request_index",
        "status_code",
        "latency_ms",
        "result_count",
    }
    for index, request in enumerate(cached_requests):
        context = f"live cached request {index}"
        if not isinstance(request, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(request, request_keys, context=context)
        concurrency = _strict_int(request, "concurrency", context, minimum=1)
        request_index = _strict_int(request, "request_index", context, minimum=1)
        if (concurrency, request_index) not in expected_roster:
            raise ValueError("live cached request concurrency roster is invalid")
        expected_id = f"cached-{concurrency}-{request_index:02d}"
        if request.get("request_id") != expected_id:
            raise ValueError("live cached request ID differs from its roster position")
        if (
            request.get("method") != "GET"
            or request.get("path") != "/api/v1/live/map"
            or request.get("layers") != ["incidents", "perimeters", "evacuations"]
        ):
            raise ValueError("live cached request differs from the canonical protocol")
        cached_statuses.append(
            _strict_int(request, "status_code", context, minimum=100, maximum=599)
        )
        cached_latencies.append(_strict_number(request, "latency_ms", context, minimum=0))
        _strict_int(request, "result_count", context, minimum=0)
        observed_roster.append((concurrency, request_index))
        grouped_rows[concurrency].append(request)
    if observed_roster != expected_roster:
        raise ValueError("live cached request roster/order differs from the frozen protocol")
    cached_p95 = _p95(cached_latencies)
    assert cached_p95 is not None
    if submitted_cached_p95 != cached_p95:
        raise ValueError("live cached p95 differs from the raw request latencies")

    by_concurrency = cached.get("by_concurrency")
    if not isinstance(by_concurrency, dict):
        raise ValueError("live cached concurrency summary must be an object")
    _require_exact_keys(by_concurrency, {"1", "5", "20"}, context="live concurrency summary")
    for concurrency, rows in grouped_rows.items():
        summary = by_concurrency[str(concurrency)]
        context = f"live concurrency {concurrency} summary"
        if not isinstance(summary, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            summary,
            {"request_count", "status_codes", "p95_latency_ms"},
            context=context,
        )
        if _strict_int(summary, "request_count", context, minimum=0) != len(rows):
            raise ValueError(f"{context} count differs from raw requests")
        status_codes = sorted({int(row["status_code"]) for row in rows})
        if summary.get("status_codes") != status_codes:
            raise ValueError(f"{context} status codes differ from raw requests")
        group_p95 = _p95([float(row["latency_ms"]) for row in rows])
        if _strict_number(summary, "p95_latency_ms", context, minimum=0) != group_p95:
            raise ValueError(f"{context} p95 differs from raw requests")

    recomputed_checks = {
        "all_official_layers_available": not unavailable_layers,
        "metadata_complete": metadata_complete,
        "chat_map_records_match": records_match,
        "all_api_requests_succeeded": (
            chat_status == 200
            and map_status == 200
            and near_me_status == 200
            and all(status == 200 for status in cached_statuses)
        ),
        "cached_p95_within_target": cached_p95 <= p95_target,
        "near_me_contract_valid": near_me_contract_valid,
    }
    if checks != recomputed_checks:
        raise ValueError("live qualification checks differ from raw validated evidence")
    qualified = _strict_bool(report, "qualified", "live qualification report")
    if qualified != all(recomputed_checks.values()):
        raise ValueError("live qualification flag differs from raw validated evidence")
    return {
        "status": "complete",
        "commit": commit,
        "qualified": qualified,
        "cold_latency_ms": cold_latency,
        "cold_result_count": cold_count,
        "cached_p95_ms": cached_p95,
        "chat_map_records_match": records_match,
        "checks": checks,
    }


def _review(
    report: dict[str, Any] | None,
    *,
    expected_cases: int,
    expected_summary_version: str,
) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "case_count": expected_cases,
            "approved_case_count": None,
            "approval_rate": None,
            "qualified": None,
        }
    if report.get("summary_version") != expected_summary_version:
        raise ValueError("review summary uses an unsupported summary_version")
    context = expected_summary_version
    case_count = _strict_int(report, "case_count", context, minimum=0)
    expected_present = _strict_bool(report, "expected_case_count_present", context)
    if case_count != expected_cases or not expected_present:
        raise ValueError(f"review summary must contain exactly {expected_cases} cases")
    approved = _strict_int(
        report,
        "approved_case_count",
        context,
        minimum=0,
        maximum=case_count,
    )
    reviewer_present = _strict_bool(report, "reviewer_present", context)
    reviewed_at_present = _strict_bool(report, "reviewed_at_present", context)
    qualified = _strict_bool(report, "qualified", context)
    if not reviewer_present or not reviewed_at_present:
        raise ValueError("review summary requires a named reviewer and review timestamp")
    reviewer = report.get("reviewer")
    reviewed_at = report.get("reviewed_at")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("review summary must retain the reviewer identity")
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        raise ValueError("review summary must retain the review timestamp")
    for hash_key in ("review_sha256", "report_sha256"):
        if (
            expected_summary_version.startswith("firelens_owner_")
            or hash_key == "review_sha256"
        ):
            value = report.get(hash_key)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"review summary must retain {hash_key}")
    unsupported = (
        _strict_int(report, "unsupported_verified_claim_count", context, minimum=0)
        if expected_summary_version == "firelens_owner_semantic_review_summary.v1"
        else 0
    )
    unclear = (
        _strict_int(report, "unclear_claim_count", context, minimum=0)
        if (expected_summary_version == "firelens_owner_semantic_review_summary.v1")
        else 0
    )
    if qualified and (approved != case_count or unsupported or unclear):
        raise ValueError("qualified review summary contains unresolved or unapproved cases")
    return {
        "status": "complete",
        "commit": report.get("commit"),
        "dataset_sha256": report.get("dataset_sha256"),
        "corpus_sha256": report.get("corpus_sha256"),
        "vector_matrix_sha256": report.get("vector_matrix_sha256"),
        "configuration_sha256": report.get("configuration_sha256"),
        "document_context_sha256": report.get("document_context_sha256"),
        "repairs_sha256": report.get("repairs_sha256"),
        "report_sha256": report.get("report_sha256"),
        "review_sha256": report.get("review_sha256"),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "case_count": case_count,
        "approved_case_count": approved,
        "approval_rate": approved / case_count if case_count else None,
        "unsupported_verified_claim_count": unsupported,
        "unclear_claim_count": unclear,
        "qualified": qualified,
    }
