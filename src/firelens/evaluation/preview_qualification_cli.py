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

from firelens.evaluation.preview_raw_evidence import (
    LIVE_METADATA_FIELDS,
    _assert_no_sensitive_retained_fields,  # noqa: F401 - compatibility re-export
    _assert_raw_response_artifact_available,
    _assert_safe_retained_preview_report,
    _json_sha256,
    _raw_response_row,
    _response_evidence,
    _retained_media_type,
    _serialize_raw_response_artifact,
    _write_raw_response_artifact,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_preview.json"
DEFAULT_RAW_OUTPUT = ROOT / "output" / "qualification" / "private" / "v1_5_preview_raw.json"


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


async def qualify_preview(
    *,
    base_url: str,
    expected_version: str,
    expected_commit: str,
    p95_target_ms: float,
    raw_response_artifact_path: Path,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    _assert_raw_response_artifact_available(raw_response_artifact_path)
    started = time.perf_counter()
    requests: list[dict[str, Any]] = []
    raw_requests: list[dict[str, Any]] = []

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
            raw_requests.append(_raw_response_row(case_id, response.content))
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
    raw_text = _serialize_raw_response_artifact(requests, raw_requests)

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
        "raw_response_artifact_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
    }
    _assert_safe_retained_preview_report(report)
    _write_raw_response_artifact(raw_response_artifact_path, raw_text)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--p95-target-ms", type=float, default=4_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-evidence-output", type=Path, default=DEFAULT_RAW_OUTPUT)
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
    if args.output.resolve() == args.raw_evidence_output.resolve():
        parser.error("preview report and raw evidence output must be different files")
    report = asyncio.run(
        qualify_preview(
            base_url=args.base_url,
            expected_version=args.expected_version,
            expected_commit=args.expected_commit,
            p95_target_ms=args.p95_target_ms,
            raw_response_artifact_path=args.raw_evidence_output,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["qualified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
