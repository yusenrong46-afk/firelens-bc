from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

from firelens.agent import FireLensAgent
from firelens.contracts import (
    AnswerSectionKind,
    LiveMapResponse,
    LocationInput,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
)
from firelens.live_answering import LiveAnswerCoordinator


class _EmptyOfficialLiveService:
    def __init__(self) -> None:
        self.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 23, tzinfo=UTC),
            results=[],
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
                    "The map shows no fires near my town, so that means my area is safe, "
                    "correct?"
                ),
                location=LocationInput(label="Kelowna"),
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
