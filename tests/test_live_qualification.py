from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI

import scripts.run_live_qualification as live_qualification
from firelens.contracts import (
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
)
from scripts.run_live_qualification import (
    _cached_api_evidence,
    _cold_record_metadata,
    _p95,
    _record_rows,
    _timed_get,
)
from scripts.upgrade_benchmark import _live


def test_live_p95_uses_the_nearest_rank_definition() -> None:
    assert _p95([float(value) for value in range(1, 27)]) == 25.0


def test_cached_api_evidence_retains_the_exact_26_request_roster() -> None:
    batches: dict[str, list[dict]] = {}
    for concurrency in (1, 5, 20):
        batches[str(concurrency)] = [
            {
                "request_id": f"cached-{concurrency}-{index + 1:02d}",
                "method": "GET",
                "path": "/api/v1/live/map",
                "layers": ["incidents", "perimeters", "evacuations"],
                "concurrency": concurrency,
                "request_index": index + 1,
                "status_code": 200,
                "latency_ms": float(index + concurrency),
                "result_count": 3,
            }
            for index in range(concurrency)
        ]

    evidence = _cached_api_evidence(batches, p95_target_ms=4_000)

    assert evidence["request_count"] == 26
    assert len(evidence["requests"]) == 26
    assert len({row["request_id"] for row in evidence["requests"]}) == 26
    assert {row["concurrency"] for row in evidence["requests"]} == {1, 5, 20}
    assert all(
        row["layers"] == ["incidents", "perimeters", "evacuations"]
        for row in evidence["requests"]
    )
    assert evidence["p95_latency_ms"] > 0


def test_timed_cached_request_emits_recomputable_request_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/live/map"
        assert request.url.params["layers"] == "incidents,perimeters,evacuations"
        return httpx.Response(200, json={"results": [{"result_id": "incident:1"}]})

    async def run() -> dict:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://example.test"
        ) as client:
            return await _timed_get(client, batch=5, index=2)

    row = asyncio.run(run())

    assert row["request_id"] == "cached-5-03"
    assert row["method"] == "GET"
    assert row["path"] == "/api/v1/live/map"
    assert row["concurrency"] == 5
    assert row["request_index"] == 3
    assert row["status_code"] == 200
    assert row["result_count"] == 1
    assert row["latency_ms"] >= 0


def test_live_evidence_retains_cold_provenance_and_chat_map_pairs() -> None:
    timestamp = datetime(2026, 8, 6, tzinfo=UTC)
    record = LiveResult(
        result_id="incident:1",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/source",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Out of Control",
        geometry={"type": "Point", "coordinates": [-123.1, 49.2]},
    )

    cold = _cold_record_metadata(record)
    pairs = _record_rows(
        {
            "live_results": [
                {"result_id": "incident:1", "status": "Out of Control"},
                {"result_id": "incident:2", "status": "Being Held"},
            ]
        },
        "live_results",
    )

    assert cold == {
        "result_id": "incident:1",
        "kind": "incident",
        "authority": "BC Wildfire Service",
        "source_url": "https://example.test/source",
        "source_updated_at": "2026-08-06T00:00:00+00:00",
        "retrieved_at": "2026-08-06T00:00:00+00:00",
        "status": "Out of Control",
    }
    assert pairs == [
        {"result_id": "incident:1", "status": "Out of Control"},
        {"result_id": "incident:2", "status": "Being Held"},
    ]


def test_live_qualification_report_emits_all_raw_evidence(monkeypatch) -> None:
    timestamp = datetime(2026, 8, 6, tzinfo=UTC)
    record = LiveResult(
        result_id="incident:1",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/source",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Out of Control",
        geometry={"type": "Point", "coordinates": [-123.1, 49.2]},
    )
    live_response = LiveMapResponse(generated_at=timestamp, results=[record])

    class FakeLiveService:
        async def map_results(self, *, layers):
            assert layers == tuple(LiveResultKind)
            return live_response

        async def aclose(self) -> None:
            return None

    class FakeRuntime:
        async def aclose(self) -> None:
            return None

    app = FastAPI()

    @app.post("/api/v1/ask")
    async def ask() -> dict:
        return {"live_results": [record.model_dump(mode="json")]}

    @app.get("/api/v1/live/map")
    async def live_map() -> dict:
        return {"results": [record.model_dump(mode="json")]}

    @app.post("/api/v1/live/nearby")
    async def near_me() -> dict:
        return {
            "requested_radius_km": 50.0,
            "requested_layers": [kind.value for kind in LiveResultKind],
            "resolved_location": {"latitude": 49.28, "longitude": -123.12},
            "viewport": {
                "west": -123.8,
                "south": 48.8,
                "east": -122.4,
                "north": 49.8,
            },
            "results": [record.model_dump(mode="json")],
            "pagination": {
                "page": 1,
                "page_size": 200,
                "total_results": 1,
                "total_pages": 1,
                "returned_results": 1,
                "has_previous": False,
                "has_next": False,
            },
            "unavailable_layers": [],
            "layer_statuses": [
                {
                    "kind": kind.value,
                    "authority": "BC Wildfire Service",
                    "source_url": live_qualification.LAYER_URLS[kind],
                    "available": True,
                    "source_updated_at": timestamp.isoformat(),
                    "retrieved_at": timestamp.isoformat(),
                    "freshness": "fresh",
                    "matching_result_count": 1 if kind == LiveResultKind.INCIDENT else 0,
                }
                for kind in LiveResultKind
            ],
            "official_fallback_urls": ["https://official.example.test/map"],
        }

    monkeypatch.setattr(live_qualification, "LiveDataService", FakeLiveService)
    monkeypatch.setattr(live_qualification, "load_runtime", lambda _config: FakeRuntime())
    monkeypatch.setattr(
        live_qualification,
        "create_app",
        lambda _config, *, runtime, live_service: app,
    )
    monkeypatch.setattr(live_qualification, "_commit", lambda: "a" * 40)

    report = asyncio.run(live_qualification.qualify(p95_target_ms=4_000))

    assert report["qualified"] is True
    assert report["evidence_schema_version"] == "firelens.live_qualification.evidence.v2"
    assert report["cold"]["records"] == [_cold_record_metadata(record)]
    assert report["chat_map"]["chat_records"] == [
        {"result_id": "incident:1", "status": "Out of Control"}
    ]
    assert report["chat_map"]["map_records"] == report["chat_map"]["chat_records"]
    assert report["cached_api"]["request_count"] == 26
    assert len(report["cached_api"]["requests"]) == 26
    assert len({row["request_id"] for row in report["cached_api"]["requests"]}) == 26
    assert report["checks"]["near_me_contract_valid"] is True
    assert report["near_me"]["result_count"] == 1
    assert _live(report)["qualified"] is True
