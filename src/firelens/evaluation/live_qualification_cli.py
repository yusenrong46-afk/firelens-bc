"""Qualify official live sources plus cached chat/map API behavior."""

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

import httpx

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import LiveResult, LiveResultKind
from firelens.git_identity import clean_checkout_commit
from firelens.live import LAYER_URLS, LiveDataService
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_live.json"
LAYERS = tuple(LiveResultKind)
NEAR_ME_REQUEST = {
    "location": {"latitude": 49.28, "longitude": -123.12, "radius_km": 50.0},
    "layers": [kind.value for kind in LAYERS],
    "page": 1,
    "page_size": 200,
}


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def _commit() -> str | None:
    return clean_checkout_commit(
        ROOT,
        context="live qualification identity",
    )


def _record_pairs(payload: dict[str, Any], field: str) -> set[tuple[str, str]]:
    return {
        (str(row["result_id"]), str(row["status"]))
        for row in payload.get(field, [])
        if isinstance(row, dict) and row.get("result_id") and row.get("status")
    }


def _record_rows(payload: dict[str, Any], field: str) -> list[dict[str, str]]:
    """Retain the public identity fields used by the chat/map equality check."""

    return [
        {"result_id": str(row["result_id"]), "status": str(row["status"])}
        for row in payload.get(field, [])
        if isinstance(row, dict) and row.get("result_id") and row.get("status")
    ]


def _cold_record_metadata(result: LiveResult) -> dict[str, str]:
    """Serialize only public provenance needed to recompute metadata completeness."""

    return {
        "result_id": str(result.result_id),
        "kind": result.kind.value,
        "authority": str(result.authority),
        "source_url": str(result.source_url),
        "source_updated_at": result.source_updated_at.isoformat(),
        "retrieved_at": result.retrieved_at.isoformat(),
        "status": str(result.status),
    }


def _cached_api_evidence(
    batches: dict[str, list[dict[str, Any]]], *, p95_target_ms: float
) -> dict[str, Any]:
    """Build cached-request evidence without discarding any request-level row."""

    requests = [row for rows in batches.values() for row in rows]
    latencies = [float(row["latency_ms"]) for row in requests]
    return {
        "p95_target_ms": p95_target_ms,
        "p95_latency_ms": _p95(latencies),
        "request_count": len(requests),
        "requests": requests,
        "by_concurrency": {
            key: {
                "request_count": len(rows),
                "status_codes": sorted({int(row["status_code"]) for row in rows}),
                "p95_latency_ms": _p95([float(row["latency_ms"]) for row in rows]),
            }
            for key, rows in batches.items()
        },
    }


async def _timed_get(client: httpx.AsyncClient, *, batch: int, index: int) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.get(
        "/api/v1/live/map",
        params={"layers": "incidents,perimeters,evacuations"},
        headers={"x-forwarded-for": f"198.51.{batch}.{index + 1}"},
    )
    return {
        "request_id": f"cached-{batch}-{index + 1:02d}",
        "method": "GET",
        "path": "/api/v1/live/map",
        "layers": ["incidents", "perimeters", "evacuations"],
        "concurrency": batch,
        "request_index": index + 1,
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
            near_me = await client.post(
                "/api/v1/live/nearby",
                json=NEAR_ME_REQUEST,
                headers={"x-forwarded-for": "198.51.100.252"},
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
        near_me_payload = near_me.json() if near_me.status_code == 200 else {}
        chat_pairs = _record_pairs(chat_payload, "live_results")
        map_pairs = _record_pairs(map_payload, "results")
        chat_rows = _record_rows(chat_payload, "live_results")
        map_rows = _record_rows(map_payload, "results")
        near_me_rows = _record_rows(near_me_payload, "results")
        near_me_pagination = near_me_payload.get("pagination")
        near_me_fallbacks = near_me_payload.get("official_fallback_urls")
        near_me_layer_statuses = near_me_payload.get("layer_statuses")
        near_me_contract_valid = bool(
            near_me.status_code == 200
            and isinstance(near_me_pagination, dict)
            and near_me_pagination.get("page") == 1
            and near_me_pagination.get("page_size") == 200
            and near_me_pagination.get("returned_results") == len(near_me_rows)
            and isinstance(near_me_pagination.get("total_results"), int)
            and near_me_pagination["total_results"] >= len(near_me_rows)
            and isinstance(near_me_fallbacks, list)
            and bool(near_me_fallbacks)
            and near_me_payload.get("requested_layers") == [kind.value for kind in LAYERS]
            and near_me_payload.get("requested_radius_km") == 50.0
            and near_me_payload.get("unavailable_layers") == []
            and isinstance(near_me_layer_statuses, list)
            and all(isinstance(row, dict) for row in near_me_layer_statuses)
            and [row.get("kind") for row in near_me_layer_statuses]
            == [kind.value for kind in LAYERS]
            and sum(
                int(row.get("matching_result_count", -1))
                for row in near_me_layer_statuses
                if isinstance(row, dict)
            )
            == near_me_pagination.get("total_results")
        )
        cached_api = _cached_api_evidence(batches, p95_target_ms=p95_target_ms)
        all_cached_rows = cached_api["requests"]
        cached_p95_ms = float(cached_api["p95_latency_ms"])
        cold_records = [_cold_record_metadata(result) for result in cold.results]
        metadata_complete = all(
            record["authority"]
            and record["source_url"]
            and record["source_updated_at"]
            and record["retrieved_at"]
            and record["status"]
            for record in cold_records
        )
        available = not cold.unavailable_layers
        matching_records = bool(chat_pairs) and chat_pairs.issubset(map_pairs)
        api_success = (
            chat.status_code == 200
            and incident_map.status_code == 200
            and near_me.status_code == 200
            and all(row["status_code"] == 200 for row in all_cached_rows)
        )
        records_digest = hashlib.sha256(
            json.dumps(sorted(map_pairs), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "report_version": "firelens.live_qualification.v2",
            "evidence_schema_version": "firelens.live_qualification.evidence.v2",
            "generated_at": datetime.now(UTC).isoformat(),
            "commit": _commit(),
            "source_urls": {kind.value: LAYER_URLS[kind] for kind in LAYERS},
            "cold": {
                "latency_ms": cold_latency_ms,
                "result_count": len(cold.results),
                "requested_layers": [kind.value for kind in LAYERS],
                "unavailable_layers": [kind.value for kind in cold.unavailable_layers],
                "records": cold_records,
                "metadata_complete": metadata_complete,
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
                "chat_status_code": chat.status_code,
                "map_status_code": incident_map.status_code,
                "chat_record_count": len(chat_pairs),
                "map_record_count": len(map_pairs),
                "chat_records": chat_rows,
                "map_records": map_rows,
                "matching_ids_and_statuses": matching_records,
                "map_records_sha256": records_digest,
            },
            "near_me": {
                "request": {
                    "method": "POST",
                    "path": "/api/v1/live/nearby",
                    "body": NEAR_ME_REQUEST,
                },
                "status_code": near_me.status_code,
                "requested_radius_km": near_me_payload.get("requested_radius_km"),
                "requested_layers": near_me_payload.get("requested_layers"),
                "resolved_location": near_me_payload.get("resolved_location"),
                "viewport": near_me_payload.get("viewport"),
                "pagination": near_me_pagination,
                "result_count": len(near_me_rows),
                "records": near_me_rows,
                "unavailable_layers": near_me_payload.get("unavailable_layers"),
                "layer_statuses": near_me_layer_statuses,
                "official_fallback_urls": near_me_fallbacks,
            },
            "cached_api": cached_api,
            "checks": {
                "all_official_layers_available": available,
                "metadata_complete": metadata_complete,
                "chat_map_records_match": matching_records,
                "all_api_requests_succeeded": api_success,
                "cached_p95_within_target": cached_p95_ms <= p95_target_ms,
                "near_me_contract_valid": near_me_contract_valid,
            },
            "elapsed_seconds": time.perf_counter() - started,
            "qualified": (
                available
                and metadata_complete
                and matching_records
                and api_success
                and cached_p95_ms <= p95_target_ms
                and near_me_contract_valid
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
