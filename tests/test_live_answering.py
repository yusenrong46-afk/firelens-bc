from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any, cast

from firelens.contracts import (
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
)
from firelens.live_answering import LiveAnswerCoordinator


class UnexpectedLiveService:
    def __init__(self) -> None:
        self.calls = 0

    async def nearby_results(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("location policy must run before a live fetch")

    async def map_results(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("supported-layer policy must run before a live fetch")


class FixedLiveService:
    def __init__(self, response: LiveMapResponse) -> None:
        self.response = response

    async def map_results(self, *args, **kwargs):
        return self.response

    async def nearby_results(self, *args, **kwargs):
        return self.response


class LiveAnswerCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_records_are_never_described_as_current(self) -> None:
        timestamp = datetime(2026, 7, 28, tzinfo=UTC)
        live = LiveMapResponse(
            generated_at=timestamp,
            results=[
                LiveResult(
                    result_id="incident:1",
                    kind=LiveResultKind.INCIDENT,
                    source_url="https://example.test/live",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=Freshness.STALE,
                    status="Out of Control",
                    name="Test Fire",
                    geometry={"type": "Point", "coordinates": [-123.5, 49.5]},
                )
            ],
            limitations=["A refresh failed; cached records may be stale."],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(live)))

        response = await coordinator.answer(
            QueryRequest(question="What active wildfires are in BC currently?"), None
        )

        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertNotIn("Current official information", response.answer)
        self.assertIn("Cached official information", response.answer)

    async def test_missing_location_fails_before_live_fetch(self) -> None:
        live_service = UnexpectedLiveService()
        coordinator = LiveAnswerCoordinator(cast(Any, live_service))

        response = await coordinator.answer(
            QueryRequest(question="Are there active wildfires near me right now?"), None
        )

        self.assertEqual(response.status, ResponseStatus.ABSTENTION)
        self.assertEqual(response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(live_service.calls, 0)
        self.assertIn("does not infer location", response.answer)

    async def test_unsupported_live_topic_is_not_substituted(self) -> None:
        live_service = UnexpectedLiveService()
        coordinator = LiveAnswerCoordinator(cast(Any, live_service))

        response = await coordinator.answer(
            QueryRequest(question="What is the live smoke forecast right now?"), None
        )

        self.assertEqual(response.status, ResponseStatus.ABSTENTION)
        self.assertEqual(response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(live_service.calls, 0)
        self.assertIn("will not substitute", response.answer)

    def test_static_fragment_is_extracted_for_mixed_coordination(self) -> None:
        request = QueryRequest(
            question=(
                "Are there active fires near Kelowna, and what belongs in an emergency kit?"
            )
        )

        static_request = LiveAnswerCoordinator.static_request(request)

        self.assertIsNotNone(static_request)
        assert static_request is not None
        self.assertNotIn("active fires", static_request.question.casefold())
        self.assertIn("emergency kit", static_request.question.casefold())
