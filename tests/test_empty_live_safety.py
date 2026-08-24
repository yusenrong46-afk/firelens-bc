from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

from firelens.agent import FireLensAgent
from firelens.contracts import (
    AnswerSectionKind,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    LocationInput,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
)
from firelens.live_answering import LiveAnswerCoordinator


class _EmptyOfficialLiveService:
    def __init__(self, results: list[LiveResult] | None = None) -> None:
        self.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 23, tzinfo=UTC),
            results=results or [],
        )
        self.nearby_calls = 0

    async def nearby_page(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        del args, kwargs
        self.nearby_calls += 1
        return self.response

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        del args, kwargs
        return self.response

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        del location
        return 49.89, -119.5


class _UnexpectedStaticService:
    async def ask(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("an empty-map live question must not fall through to static RAG")


def test_empty_official_map_never_becomes_an_all_clear() -> None:
    async def run() -> None:
        live = _EmptyOfficialLiveService()
        execution = await FireLensAgent(
            cast(Any, _UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(
            QueryRequest(
                question=(
                    "The wildfire map is empty near Kelowna. Does that mean everything is safe?"
                )
            )
        )

        response = execution.response
        public_text = " ".join([response.answer or "", *response.limitations]).casefold()

        assert live.nearby_calls > 0
        assert execution.route == QueryRoute.LIVE
        assert response.response_mode == ResponseMode.LIVE
        assert response.reason_code == ReasonCode.LIVE_DATA_REQUIRED
        assert response.live_results == []
        assert response.resolved_location is not None
        assert "no matching official wildfire records" in public_text
        assert "does not mean the area is safe" in public_text
        assert "not an all-clear" in public_text
        assert "not a safety determination" in public_text
        assert "outside the grounded sources" not in public_text
        assert [section.kind for section in response.answer_sections] == [
            AnswerSectionKind.UNCERTAINTY,
            AnswerSectionKind.OFFICIAL_HANDOFF,
        ]
        assert [link.title for link in response.related_links] == [
            "BC Wildfire Service map",
            "EmergencyInfoBC",
        ]

    asyncio.run(run())


def test_nonempty_lookup_corrects_the_empty_map_inference_without_a_safety_claim() -> None:
    async def run() -> None:
        stamp = datetime(2026, 8, 23, tzinfo=UTC)
        live = _EmptyOfficialLiveService(
            [
                LiveResult(
                    result_id="incident:kelowna-fixture",
                    kind=LiveResultKind.INCIDENT,
                    source_url="https://example.test/incident/kelowna-fixture",
                    source_updated_at=stamp,
                    retrieved_at=stamp,
                    freshness=Freshness.FRESH,
                    status="Being Held",
                    name="Kelowna Fixture",
                    geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
                )
            ]
        )
        execution = await FireLensAgent(
            cast(Any, _UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(
            QueryRequest(
                question=(
                    "The wildfire map is blank near Kelowna. Does that mean there is no "
                    "wildfire risk?"
                )
            )
        )

        response = execution.response
        public_text = " ".join([response.answer or "", *response.limitations]).casefold()

        assert live.nearby_calls > 0
        assert execution.route == QueryRoute.LIVE
        assert response.response_mode == ResponseMode.LIVE
        assert response.resolved_location is not None
        assert len(response.live_results) == 1
        assert "empty map view is not an all-clear" in public_text
        assert "does not establish that the area is safe" in public_text
        assert "1 layer record" in public_text
        assert "not distinct-fire counts or a safety determination" in public_text

    asyncio.run(run())
