#!/usr/bin/env python3
"""Run anonymous release checks against an approved FireLens preview URL."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_preview.json"


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
    required = {
        "result_id",
        "authority",
        "source_url",
        "source_updated_at",
        "retrieved_at",
        "status",
    }
    return bool(rows) and all(
        required.issubset(row) and all(row[key] for key in required) for row in rows
    )


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

        async def call(method: str, path: str, **kwargs: Any) -> httpx.Response:
            request_started = time.perf_counter()
            response = await client.request(method, path, **kwargs)
            requests.append(
                {
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "latency_ms": (time.perf_counter() - request_started) * 1_000,
                }
            )
            return response

        homepage = await call("GET", "/")
        live_health = await call("GET", "/api/v1/health/live")
        ready_health = await call("GET", "/api/v1/health/ready")
        static = await call(
            "POST", "/api/v1/ask", json={"question": "What belongs in an emergency kit?"}
        )
        unsupported = await call(
            "POST",
            "/api/v1/ask",
            json={
                "question": "What is the current air quality in Vancouver from wildfire smoke?"
            },
        )
        live = await call(
            "POST",
            "/api/v1/ask",
            json={"question": "Are there active wildfires in BC currently?"},
        )
        mixed = await call(
            "POST",
            "/api/v1/ask",
            json={
                "question": (
                    "Are there active wildfires in BC currently, and what belongs in an "
                    "emergency kit?"
                )
            },
        )
        map_response = await call("GET", "/api/v1/live/map", params={"layers": "incidents"})

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
    return {
        "report_version": "firelens.preview_qualification.v1",
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
