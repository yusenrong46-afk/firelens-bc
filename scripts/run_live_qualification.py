#!/usr/bin/env python3
"""Qualify official live sources plus cached chat/map API behavior."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import LiveResultKind
from firelens.live import LAYER_URLS, LiveDataService
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_live.json"
LAYERS = tuple(LiveResultKind)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))]


def _commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _record_pairs(payload: dict[str, Any], field: str) -> set[tuple[str, str]]:
    return {
        (str(row["result_id"]), str(row["status"]))
        for row in payload.get(field, [])
        if isinstance(row, dict) and row.get("result_id") and row.get("status")
    }


async def _timed_get(client: httpx.AsyncClient, *, batch: int, index: int) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.get(
        "/api/v1/live/map",
        params={"layers": "incidents,perimeters,evacuations"},
        headers={"x-forwarded-for": f"198.51.{batch}.{index + 1}"},
    )
    return {
        "status_code": response.status_code,
        "latency_ms": (time.perf_counter() - started) * 1_000,
        "result_count": len(response.json().get("results", []))
        if response.status_code == 200
        else 0,
    }


async def qualify(*, p95_target_ms: float) -> dict[str, Any]:
    config = FireLensConfig.from_env(ROOT)
    runtime = load_runtime(config)
    live_service = LiveDataService()
    started = time.perf_counter()
    try:
        cold_started = time.perf_counter()
        cold = await live_service.map_results(layers=LAYERS)
        cold_latency_ms = (time.perf_counter() - cold_started) * 1_000

        app = create_app(config, runtime=runtime, live_service=live_service)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat = await client.post(
                "/api/v1/ask",
                json={"question": "Are there active wildfires in BC currently?"},
                headers={"x-forwarded-for": "198.51.100.250"},
            )
            incident_map = await client.get(
                "/api/v1/live/map",
                params={"layers": "incidents"},
                headers={"x-forwarded-for": "198.51.100.251"},
            )

            batches: dict[str, list[dict[str, Any]]] = {}
            for concurrency in (1, 5, 20):
                batches[str(concurrency)] = await asyncio.gather(
                    *(
                        _timed_get(client, batch=concurrency, index=index)
                        for index in range(concurrency)
                    )
                )

        chat_payload = chat.json() if chat.status_code == 200 else {}
        map_payload = incident_map.json() if incident_map.status_code == 200 else {}
        chat_pairs = _record_pairs(chat_payload, "live_results")
        map_pairs = _record_pairs(map_payload, "results")
        all_cached_rows = [row for rows in batches.values() for row in rows]
        cached_latencies = [float(row["latency_ms"]) for row in all_cached_rows]
        cached_p95_ms = _p95(cached_latencies)
        metadata_complete = all(
            result.authority
            and result.source_url
            and result.source_updated_at
            and result.retrieved_at
            and result.status
            for result in cold.results
        )
        available = not cold.unavailable_layers
        matching_records = bool(chat_pairs) and chat_pairs.issubset(map_pairs)
        api_success = (
            chat.status_code == 200
            and incident_map.status_code == 200
            and all(row["status_code"] == 200 for row in all_cached_rows)
        )
        records_digest = hashlib.sha256(
            json.dumps(sorted(map_pairs), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "report_version": "firelens.live_qualification.v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "commit": _commit(),
            "source_urls": {kind.value: LAYER_URLS[kind] for kind in LAYERS},
            "cold": {
                "latency_ms": cold_latency_ms,
                "result_count": len(cold.results),
                "unavailable_layers": [kind.value for kind in cold.unavailable_layers],
                "metadata_complete": metadata_complete,
            },
            "chat_map": {
                "chat_status_code": chat.status_code,
                "map_status_code": incident_map.status_code,
                "chat_record_count": len(chat_pairs),
                "map_record_count": len(map_pairs),
                "matching_ids_and_statuses": matching_records,
                "map_records_sha256": records_digest,
            },
            "cached_api": {
                "p95_target_ms": p95_target_ms,
                "p95_latency_ms": cached_p95_ms,
                "request_count": len(all_cached_rows),
                "by_concurrency": {
                    key: {
                        "request_count": len(rows),
                        "status_codes": sorted({int(row["status_code"]) for row in rows}),
                        "p95_latency_ms": _p95([float(row["latency_ms"]) for row in rows]),
                    }
                    for key, rows in batches.items()
                },
            },
            "checks": {
                "all_official_layers_available": available,
                "metadata_complete": metadata_complete,
                "chat_map_records_match": matching_records,
                "all_api_requests_succeeded": api_success,
                "cached_p95_within_target": cached_p95_ms <= p95_target_ms,
            },
            "elapsed_seconds": time.perf_counter() - started,
            "qualified": (
                available
                and metadata_complete
                and matching_records
                and api_success
                and cached_p95_ms <= p95_target_ms
            ),
        }
    finally:
        await live_service.aclose()
        await runtime.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--p95-target-ms", type=float, default=4_000)
    args = parser.parse_args()
    if args.p95_target_ms <= 0:
        parser.error("--p95-target-ms must be greater than zero")
    report = asyncio.run(qualify(p95_target_ms=args.p95_target_ms))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["qualified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
