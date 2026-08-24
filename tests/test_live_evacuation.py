"""Focused regressions for deterministic official evacuation summaries."""

from __future__ import annotations

from datetime import UTC, datetime

from firelens.answering.live_evacuation import (
    evacuation_answer,
    is_evacuation_record_question,
)
from firelens.contracts import Freshness, LiveResult, LiveResultKind, QueryRequest


def _evacuation(*, result_id: str, status: str) -> LiveResult:
    stamp = datetime(2026, 8, 24, tzinfo=UTC)
    return LiveResult(
        result_id=result_id,
        kind=LiveResultKind.EVACUATION,
        source_url=f"https://example.test/{result_id}",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status=status,
        name="Example Wildfire",
        issuer="Example Regional District",
        geometry={"type": "Polygon", "coordinates": []},
    )


def test_dotted_bc_scope_uses_province_wide_grouping() -> None:
    question = "Where are the evacuation alerts and orders across B.C. right now?"
    records = [
        _evacuation(result_id="evacuation:order", status="Order"),
        _evacuation(result_id="evacuation:alert", status="Alert"),
    ]

    assert is_evacuation_record_question(question)
    answer = evacuation_answer(
        QueryRequest(question=question),
        records,
        display_name=lambda item: item.name or item.result_id,
        nearby_radius_km=50.0,
    )

    assert "across BC" in answer
    assert "2 unique name/status/issuer groups" in answer
    assert "2 official area records" in answer
    assert "requested place" not in answer
