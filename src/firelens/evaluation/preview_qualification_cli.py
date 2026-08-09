"""Run anonymous release checks against an approved FireLens preview URL."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_preview.json"
LIVE_METADATA_FIELDS = (
    "result_id",
    "authority",
    "source_url",
    "source_updated_at",
    "retrieved_at",
    "status",
)
RETAINED_MEDIA_TYPES = frozenset({"application/json", "text/html"})
FORBIDDEN_RETAINED_FIELDS = frozenset(
    {
        "answer",
        "authorization",
        "bbox",
        "body",
        "content",
        "context_text",
        "coordinates",
        "cookie",
        "geometry",
        "headers",
        "history_text",
        "latitude",
        "location",
        "longitude",
        "primary_text",
        "private_headers",
        "quote",
        "raw_response",
        "response_body",
        "response_content",
        "set-cookie",
        "source_passage",
    }
)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def _exact_support(payload: dict[str, Any]) -> bool:
    evidence = {
        row.get("evidence_id"): row
        for row in payload.get("evidence", [])
        if isinstance(row, dict) and row.get("evidence_id")
    }
    claims = payload.get("claims", [])
    if not claims or not evidence:
        return False
    for claim in claims:
        supports = claim.get("supports", []) if isinstance(claim, dict) else []
        if not supports:
            return False
        for support in supports:
            item = evidence.get(support.get("evidence_id"))
            quote = support.get("quote")
            if (
                not item
                or not isinstance(quote, str)
                or quote not in item.get("primary_text", "")
            ):
                return False
    return True


def _live_metadata_complete(rows: list[dict[str, Any]]) -> bool:
    required = set(LIVE_METADATA_FIELDS)
    return bool(rows) and all(
        required.issubset(row) and all(row[key] for key in required) for row in rows
    )


def _json_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _retained_media_type(value: str | None) -> str:
    """Retain only the protocol media type, never arbitrary header parameters."""

    media_type = str(value or "").split(";", 1)[0].strip().casefold()
    return media_type if media_type in RETAINED_MEDIA_TYPES else "other"


def _public_live_metadata(row: Any) -> dict[str, Any]:
    """Retain only public record provenance, while preserving malformed rows."""

    if not isinstance(row, dict):
        return {"invalid_record": True, "value_type": type(row).__name__}
    retained = {field: row.get(field) for field in LIVE_METADATA_FIELDS}
    source_url = retained.get("source_url")
    if isinstance(source_url, str):
        retained["source_url"] = (
            urlparse(source_url)._replace(params="", query="", fragment="").geturl()
        )
    return retained


def _assert_exact_retained_keys(
    payload: Any, expected: set[str], *, context: str
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be an object")
    actual = set(payload)
    if actual != expected:
        raise ValueError(
            f"{context} violates the retained-evidence schema; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    return payload


def _assert_no_sensitive_retained_fields(
    value: Any, *, context: str = "preview report"
) -> None:
    """Reject plaintext/body/location channels from any retained structure."""

    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in {field.replace("-", "_") for field in FORBIDDEN_RETAINED_FIELDS}:
                raise ValueError(f"{context} contains forbidden retained field {key!r}")
            _assert_no_sensitive_retained_fields(nested, context=f"{context}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_sensitive_retained_fields(nested, context=f"{context}[{index}]")


def _assert_safe_retained_preview_report(report: dict[str, Any]) -> None:
    """Enforce the content-free preview artifact boundary before serialization."""

    _assert_exact_retained_keys(
        report,
        {
            "report_version",
            "evidence_schema_version",
            "generated_at",
            "base_url",
            "expected",
            "observed",
            "requests",
            "ask_p95_ms",
            "p95_target_ms",
            "checks",
            "qualified",
            "elapsed_seconds",
            "not_executed",
        },
        context="preview report",
    )
    requests = report.get("requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise ValueError("preview report must retain exactly eight request rows")
    expected_cases = [
        "homepage",
        "liveness",
        "readiness",
        "static",
        "unsupported",
        "live",
        "mixed",
        "map",
    ]
    request_keys = {
        "case_id",
        "method",
        "path",
        "request",
        "request_body_sha256",
        "status_code",
        "latency_ms",
        "response_content_type",
        "response_content_length_bytes",
        "response_body_sha256",
        "response",
    }
    for index, row in enumerate(requests):
        _validate_retained_preview_request(row, index, expected_cases[index], request_keys)
    _assert_no_sensitive_retained_fields(report)


def _validate_retained_preview_request(
    row: Any, index: int, case_id: str, request_keys: set[str]
) -> None:
    retained = _assert_exact_retained_keys(
        row, request_keys, context=f"preview request {index}"
    )
    if retained.get("case_id") != case_id:
        raise ValueError("preview retained case order differs from the canonical protocol")
    request = retained.get("request")
    if not isinstance(request, dict) or not set(request).issubset({"question", "layers"}):
        raise ValueError(f"preview {case_id} request retains unsupported input fields")
    response = retained.get("response")
    simple_keys = {
        "homepage": set(),
        "liveness": {"status"},
        "readiness": {
            "status",
            "release_version",
            "build_commit",
            "deployment_id",
            "rate_limit_scope",
        },
    }
    if case_id in simple_keys:
        _assert_exact_retained_keys(
            response, simple_keys[case_id], context=f"preview {case_id} response"
        )
    elif case_id == "map":
        _validate_retained_live_records(response, context="preview map", map_response=True)
    else:
        _validate_retained_ask_response(response, case_id)


def _validate_retained_live_records(
    value: Any, *, context: str, map_response: bool = False
) -> None:
    payload = (
        _assert_exact_retained_keys(
            value, {"record_count", "records"}, context=f"{context} response"
        )
        if map_response
        else value
    )
    records = payload["records"] if map_response else payload
    for index, record in enumerate(records):
        _assert_exact_retained_keys(
            record, set(LIVE_METADATA_FIELDS), context=f"{context} record {index}"
        )


def _validate_retained_ask_response(response: Any, case_id: str) -> None:
    keys = {"status", "response_mode", "claim_count", "evidence_count", "live_result_count"}
    if case_id in {"static", "mixed"}:
        keys.add("exact_support")
    if case_id in {"live", "mixed"}:
        keys.add("live_records")
    payload = _assert_exact_retained_keys(response, keys, context=f"preview {case_id} response")
    _validate_retained_live_records(
        payload.get("live_records", []), context=f"preview {case_id} live"
    )
    if payload.get("exact_support") is not None:
        _validate_retained_exact_support(payload["exact_support"], case_id)


def _validate_retained_exact_support(support: Any, case_id: str) -> None:
    proof = _assert_exact_retained_keys(
        support, {"claims", "evidence"}, context=f"preview {case_id} exact-support proof"
    )
    for claim_index, claim in enumerate(proof["claims"]):
        retained = _assert_exact_retained_keys(
            claim, {"claim_id", "supports"}, context=f"preview {case_id} claim {claim_index}"
        )
        for support_index, row in enumerate(retained["supports"]):
            keys = {
                "evidence_id",
                "quote_sha256",
                "quote_length",
                "match_start",
                "match_end",
                "matched_slice_sha256",
            }
            _assert_exact_retained_keys(
                row,
                keys,
                context=f"preview {case_id} claim {claim_index} support {support_index}",
            )
    for index, row in enumerate(proof["evidence"]):
        _assert_exact_retained_keys(
            row,
            {"evidence_id", "primary_text_sha256", "primary_text_length"},
            context=f"preview {case_id} evidence {index}",
        )


def _exact_support_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a content-free proof roster for exact-quote support checks.

    The report binds each quote and evidence text by digest and retains the match
    offsets without copying answer or source text into a release artifact.
    """

    evidence_rows: list[dict[str, Any]] = []
    primary_by_id: dict[str, str] = {}
    for row in payload.get("evidence", []):
        if not isinstance(row, dict) or not row.get("evidence_id"):
            evidence_rows.append({"invalid_evidence": True, "value_type": type(row).__name__})
            continue
        evidence_id = str(row["evidence_id"])
        primary_text = row.get("primary_text")
        if not isinstance(primary_text, str):
            evidence_rows.append(
                {
                    "evidence_id": evidence_id,
                    "primary_text_sha256": None,
                    "primary_text_length": None,
                }
            )
            continue
        primary_by_id[evidence_id] = primary_text
        evidence_rows.append(
            {
                "evidence_id": evidence_id,
                "primary_text_sha256": hashlib.sha256(primary_text.encode("utf-8")).hexdigest(),
                "primary_text_length": len(primary_text),
            }
        )

    claim_rows: list[dict[str, Any]] = []
    for claim in payload.get("claims", []):
        if not isinstance(claim, dict):
            claim_rows.append({"invalid_claim": True, "value_type": type(claim).__name__})
            continue
        support_rows: list[dict[str, Any]] = []
        supports = claim.get("supports", [])
        if not isinstance(supports, list):
            supports = []
        for support in supports:
            if not isinstance(support, dict):
                support_rows.append(
                    {"invalid_support": True, "value_type": type(support).__name__}
                )
                continue
            evidence_id = str(support.get("evidence_id") or "")
            quote = support.get("quote")
            primary_text = primary_by_id.get(evidence_id)
            match_start = (
                primary_text.find(quote)
                if isinstance(primary_text, str) and isinstance(quote, str) and quote
                else -1
            )
            matched_slice = (
                primary_text[match_start : match_start + len(quote)]
                if match_start >= 0 and isinstance(primary_text, str) and isinstance(quote, str)
                else None
            )
            support_rows.append(
                {
                    "evidence_id": evidence_id,
                    "quote_sha256": (
                        hashlib.sha256(quote.encode("utf-8")).hexdigest()
                        if isinstance(quote, str)
                        else None
                    ),
                    "quote_length": len(quote) if isinstance(quote, str) else None,
                    "match_start": match_start,
                    "match_end": (
                        match_start + len(quote)
                        if match_start >= 0 and isinstance(quote, str)
                        else -1
                    ),
                    "matched_slice_sha256": (
                        hashlib.sha256(matched_slice.encode("utf-8")).hexdigest()
                        if matched_slice is not None
                        else None
                    ),
                }
            )
        claim_rows.append(
            {
                "claim_id": str(claim.get("claim_id") or ""),
                "supports": support_rows,
            }
        )
    return {"claims": claim_rows, "evidence": evidence_rows}


def _response_evidence(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Select the minimum response fields needed to recompute canonical checks."""

    if case_id == "homepage":
        return {}
    if case_id in {"liveness", "readiness"}:
        fields = (
            ("status",)
            if case_id == "liveness"
            else (
                "status",
                "release_version",
                "build_commit",
                "deployment_id",
                "rate_limit_scope",
            )
        )
        return {field: payload.get(field) for field in fields}

    evidence: dict[str, Any] = {
        "status": payload.get("status"),
        "response_mode": payload.get("response_mode"),
        "claim_count": len(payload.get("claims", []))
        if isinstance(payload.get("claims", []), list)
        else None,
        "evidence_count": len(payload.get("evidence", []))
        if isinstance(payload.get("evidence", []), list)
        else None,
        "live_result_count": len(payload.get("live_results", []))
        if isinstance(payload.get("live_results", []), list)
        else None,
    }
    if case_id in {"static", "mixed"}:
        evidence["exact_support"] = _exact_support_evidence(payload)
    if case_id in {"live", "mixed"}:
        evidence["live_records"] = [
            _public_live_metadata(row) for row in payload.get("live_results", [])
        ]
    if case_id == "map":
        evidence = {
            "record_count": len(payload.get("results", []))
            if isinstance(payload.get("results", []), list)
            else None,
            "records": [_public_live_metadata(row) for row in payload.get("results", [])],
        }
    return evidence


async def qualify_preview(
    *,
    base_url: str,
    expected_version: str,
    expected_commit: str,
    p95_target_ms: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    requests: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
        transport=transport,
        headers={"User-Agent": "FireLens-V1.5-preview-qualification/1"},
    ) as client:

        async def call(case_id: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
            request_started = time.perf_counter()
            response = await client.request(method, path, **kwargs)
            request_json = kwargs.get("json")
            request_params = kwargs.get("params")
            safe_request: dict[str, Any] = {}
            if isinstance(request_json, dict) and isinstance(request_json.get("question"), str):
                safe_request["question"] = request_json["question"]
            if isinstance(request_params, dict) and request_params.get("layers"):
                safe_request["layers"] = str(request_params["layers"]).split(",")
            requests.append(
                {
                    "case_id": case_id,
                    "method": method,
                    "path": path,
                    "request": safe_request,
                    "request_body_sha256": (
                        _json_sha256(request_json) if request_json is not None else None
                    ),
                    "status_code": response.status_code,
                    "latency_ms": (time.perf_counter() - request_started) * 1_000,
                    "response_content_type": _retained_media_type(
                        response.headers.get("content-type")
                    ),
                    "response_content_length_bytes": len(response.content),
                    "response_body_sha256": hashlib.sha256(response.content).hexdigest(),
                }
            )
            return response

        homepage = await call("homepage", "GET", "/")
        live_health = await call("liveness", "GET", "/api/v1/health/live")
        ready_health = await call("readiness", "GET", "/api/v1/health/ready")
        static = await call(
            "static",
            "POST",
            "/api/v1/ask",
            json={"question": "What belongs in an emergency kit?"},
        )
        unsupported = await call(
            "unsupported",
            "POST",
            "/api/v1/ask",
            json={
                "question": "What is the current air quality in Vancouver from wildfire smoke?"
            },
        )
        live = await call(
            "live",
            "POST",
            "/api/v1/ask",
            json={"question": "Are there active wildfires in BC currently?"},
        )
        mixed = await call(
            "mixed",
            "POST",
            "/api/v1/ask",
            json={
                "question": (
                    "Are there active wildfires in BC currently, and what belongs in an "
                    "emergency kit?"
                )
            },
        )
        map_response = await call(
            "map", "GET", "/api/v1/live/map", params={"layers": "incidents"}
        )

    payloads: dict[str, dict[str, Any]] = {}
    for name, response in {
        "liveness": live_health,
        "readiness": ready_health,
        "static": static,
        "unsupported": unsupported,
        "live": live,
        "mixed": mixed,
        "map": map_response,
    }.items():
        try:
            payloads[name] = response.json()
        except (json.JSONDecodeError, TypeError):
            payloads[name] = {}

    for request in requests:
        case_id = str(request["case_id"])
        request["response"] = _response_evidence(case_id, payloads.get(case_id, {}))

    ready = payloads["readiness"]
    live_rows = payloads["live"].get("live_results", [])
    mixed_rows = payloads["mixed"].get("live_results", [])
    map_rows = payloads["map"].get("results", [])
    live_pairs = {(row.get("result_id"), row.get("status")) for row in live_rows}
    map_pairs = {(row.get("result_id"), row.get("status")) for row in map_rows}
    dynamic_latencies = [row["latency_ms"] for row in requests if row["path"] == "/api/v1/ask"]
    checks = {
        "homepage_anonymous": homepage.status_code == 200
        and "text/html" in homepage.headers.get("content-type", ""),
        "liveness": live_health.status_code == 200
        and payloads["liveness"].get("status") == "alive",
        "readiness": ready_health.status_code == 200 and ready.get("status") == "ready",
        "release_identity": ready.get("release_version") == expected_version
        and ready.get("build_commit") == expected_commit,
        "static_grounded": static.status_code == 200
        and payloads["static"].get("status") == "answer"
        and payloads["static"].get("response_mode") in {"grounded", "partial", "conflict"}
        and _exact_support(payloads["static"]),
        "unsupported_fails_closed": unsupported.status_code == 200
        and payloads["unsupported"].get("status") == "abstention"
        and not payloads["unsupported"].get("claims")
        and not payloads["unsupported"].get("live_results"),
        "live_metadata_complete": live.status_code == 200
        and payloads["live"].get("response_mode") == "live"
        and _live_metadata_complete(live_rows),
        "mixed_separates_sources": mixed.status_code == 200
        and payloads["mixed"].get("response_mode") == "mixed"
        and _live_metadata_complete(mixed_rows)
        and _exact_support(payloads["mixed"]),
        "chat_map_records_match": bool(live_pairs) and live_pairs.issubset(map_pairs),
        "static_p95_within_target": _p95(dynamic_latencies) <= p95_target_ms,
    }
    report = {
        "report_version": "firelens.preview_qualification.v1",
        "evidence_schema_version": "firelens.preview_qualification.evidence.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": base_url.rstrip("/"),
        "expected": {"release_version": expected_version, "build_commit": expected_commit},
        "observed": {
            "release_version": ready.get("release_version"),
            "build_commit": ready.get("build_commit"),
            "deployment_id": ready.get("deployment_id"),
            "rate_limit_scope": ready.get("rate_limit_scope"),
        },
        "requests": requests,
        "ask_p95_ms": _p95(dynamic_latencies),
        "p95_target_ms": p95_target_ms,
        "checks": checks,
        "qualified": all(checks.values()),
        "elapsed_seconds": time.perf_counter() - started,
        "not_executed": [
            "forced official-source outage requires an approved preview failure-injection mechanism",
            "screen-reader and mobile interaction require browser verification",
            "distributed firewall enforcement requires owner review and publication",
        ],
    }
    _assert_safe_retained_preview_report(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--p95-target-ms", type=float, default=4_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-http", action="store_true", help="Allow localhost test servers"
    )
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "https" and not (
        args.allow_http
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        parser.error("preview qualification requires HTTPS (or --allow-http for localhost)")
    if not parsed.netloc or args.p95_target_ms <= 0:
        parser.error("provide a valid base URL and positive p95 target")
    report = asyncio.run(
        qualify_preview(
            base_url=args.base_url,
            expected_version=args.expected_version,
            expected_commit=args.expected_commit,
            p95_target_ms=args.p95_target_ms,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["qualified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
