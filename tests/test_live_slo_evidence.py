from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import scripts.live_slo_evidence as live_slo
from firelens.contracts import (
    AggregateFreshness,
    Freshness,
    LiveLayerStatus,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "data" / "evaluation" / "live_slo.v1.yaml"


def _response(layers: tuple[LiveResultKind, ...], *, stale: bool = False) -> LiveMapResponse:
    now = datetime.now(UTC)
    results = [
        LiveResult(
            result_id=f"{kind.value}:1",
            kind=kind,
            source_url=f"https://official.example.test/{kind.value}",
            source_updated_at=now - timedelta(minutes=10),
            retrieved_at=now,
            freshness=Freshness.STALE if stale else Freshness.FRESH,
            status="Active",
            geometry={"type": "Point", "coordinates": [-123.12, 49.28]},
        )
        for kind in layers
    ]
    return LiveMapResponse(
        generated_at=now,
        results=results,
        aggregate_freshness=(AggregateFreshness.STALE if stale else AggregateFreshness.FRESH),
        layer_statuses=[
            LiveLayerStatus(
                kind=kind,
                authority="BC Wildfire Service",
                source_url=live_slo.LAYER_URLS[kind],
                available=True,
                source_updated_at=now - timedelta(minutes=5),
                retrieved_at=now,
                freshness=Freshness.STALE if stale else Freshness.FRESH,
                matching_result_count=1,
            )
            for kind in layers
        ],
    )


class FakeLiveService:
    def __init__(self) -> None:
        self.closed = False

    async def map_results(self, *, layers):
        return _response(layers)

    async def nearby_results(self, location, *, layers):
        assert location.latitude is not None
        return _response(layers)

    async def aclose(self) -> None:
        self.closed = True


def test_protocol_is_explicitly_unratified_and_has_bounded_bc_roster() -> None:
    protocol = live_slo.load_protocol(PROTOCOL)

    assert protocol["qualification_eligible"] is False
    assert protocol["thresholds"] is None
    assert protocol["phases"] == ["cold", "cached"]
    assert len(protocol["regions"]) == 3
    assert protocol["max_repetitions"] == 10


def test_capture_retains_full_layer_region_phase_roster_and_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services: list[FakeLiveService] = []

    def service_factory() -> FakeLiveService:
        service = FakeLiveService()
        services.append(service)
        return service

    monkeypatch.setattr(live_slo, "_git_identity", lambda: ("a" * 40, False))
    report = asyncio.run(
        live_slo.capture(
            protocol_path=PROTOCOL,
            repetitions=2,
            service_factory=service_factory,
        )
    )
    verified = live_slo.verify(report, protocol_path=PROTOCOL)

    assert report["row_count"] == 24
    assert len(report["summaries"]) == 12
    assert report["qualification_eligible"] is False
    assert report["thresholds"] is None
    assert verified == {
        "verified": True,
        "qualification_eligible": False,
        "worktree_dirty": False,
        "row_count": 24,
        "summary_count": 12,
    }
    assert len(services) == 2
    assert all(service.closed for service in services)
    assert {(row["target_id"], row["phase"]) for row in report["rows"]} == {
        (target, phase)
        for target in (
            "layer:incident",
            "layer:perimeter",
            "layer:evacuation",
            "region:lower_mainland",
            "region:okanagan",
            "region:central_bc",
        )
        for phase in ("cold", "cached")
    }


def test_verifier_rejects_summary_roster_and_freshness_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_slo, "_git_identity", lambda: ("b" * 40, False))
    report = asyncio.run(
        live_slo.capture(
            protocol_path=PROTOCOL,
            repetitions=1,
            service_factory=FakeLiveService,
        )
    )

    wrong_summary = copy.deepcopy(report)
    wrong_summary["summaries"][0]["latency_p95_ms"] += 1
    with pytest.raises(ValueError, match="summaries differ"):
        live_slo.verify(wrong_summary, protocol_path=PROTOCOL)

    missing_row = copy.deepcopy(report)
    missing_row["rows"].pop()
    missing_row["row_count"] -= 1
    with pytest.raises(ValueError, match="roster differs"):
        live_slo.verify(missing_row, protocol_path=PROTOCOL)

    wrong_freshness = copy.deepcopy(report)
    wrong_freshness["rows"][0]["aggregate_freshness"] = "stale"
    with pytest.raises(ValueError, match="aggregate freshness differs"):
        live_slo.verify(wrong_freshness, protocol_path=PROTOCOL)


def test_capture_sanitizes_unexpected_failures_without_claiming_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingService(FakeLiveService):
        async def map_results(self, *, layers):
            raise RuntimeError("private upstream details")

        async def nearby_results(self, location, *, layers):
            raise RuntimeError("private upstream details")

    monkeypatch.setattr(live_slo, "_git_identity", lambda: ("c" * 40, True))
    report = asyncio.run(
        live_slo.capture(
            protocol_path=PROTOCOL,
            repetitions=1,
            service_factory=FailingService,
        )
    )

    assert live_slo.verify(report, protocol_path=PROTOCOL)["worktree_dirty"] is True
    assert all(row["status"] == "error" for row in report["rows"])
    assert all(row["error_kind"] == "unexpected" for row in report["rows"])
    assert "private upstream details" not in str(report)
    assert all(summary["availability_rate"] == 0 for summary in report["summaries"])


def test_capture_refuses_repetitions_outside_protocol() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        asyncio.run(
            live_slo.capture(
                protocol_path=PROTOCOL,
                repetitions=11,
                service_factory=FakeLiveService,
            )
        )
