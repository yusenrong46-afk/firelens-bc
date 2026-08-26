from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any, cast

from firelens.agent import FireLensAgent
from firelens.answering.intent import live_layers_for_question, plan_query
from firelens.answering.live_record_intent import is_fire_geography_analysis
from firelens.answering.location_intent import (
    coarse_location_from_question,
    directional_bc_region_label,
)
from firelens.contracts import (
    AskResponse,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    aggregate_live_freshness,
)
from firelens.live_answering import LiveAnswerCoordinator


def _incident(result_id: str, fire_centre: str) -> LiveResult:
    timestamp = datetime(2026, 8, 24, tzinfo=UTC)
    return LiveResult(
        result_id=result_id,
        kind=LiveResultKind.INCIDENT,
        source_url=f"https://example.test/incidents/{result_id}",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name=f"Fixture {result_id}",
        fire_centre=fire_centre,
        geometry={"type": "Point", "coordinates": [-123.0, 50.0]},
    )


class _RosterService:
    def __init__(self) -> None:
        self.map_calls = 0
        self.nearby_calls = 0
        self.resolve_calls = 0

    async def map_results(self, *, layers: tuple[LiveResultKind, ...]) -> LiveMapResponse:
        self.map_calls += 1
        assert layers == (LiveResultKind.INCIDENT,)
        results = [
            _incident("incident:1", "Prince George Fire Centre"),
            _incident("incident:2", "Prince George Fire Centre"),
            _incident("incident:3", "Coastal Fire Centre"),
        ]
        return LiveMapResponse(
            generated_at=datetime(2026, 8, 24, tzinfo=UTC),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.nearby_calls += 1
        raise AssertionError("a broad BC region must use the province-wide roster")

    async def resolve_location(self, *args: Any, **kwargs: Any) -> tuple[float, float]:
        del args, kwargs
        self.resolve_calls += 1
        raise AssertionError("a broad BC region must never be geocoded")


class _NoStatic:
    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        raise AssertionError("a live regional query must not call static retrieval")


class RegionalFireQueryTests(unittest.IsolatedAsyncioTestCase):
    def test_directional_bc_regions_are_province_wide_geography_queries(self) -> None:
        cases = {
            "Where are the wildfires in northern B.C. right now?": "northern B.C.",
            "Show current wildfires across northern British Columbia.": "northern B.C.",
            "Which fires are in North BC today?": "northern B.C.",
            "Where are wildfires in southern BC right now?": "southern B.C.",
            "Show wildfires across South B.C. today.": "southern B.C.",
            "Wildfires throughout southern British Columbia right now": "southern B.C.",
            "Where are wildfires in northern BC?": "northern B.C.",
            "Are there wildfires in northern BC?": "northern B.C.",
            "Show wildfires in northern BC.": "northern B.C.",
            "How many wildfires are in northern BC?": "northern B.C.",
            "Which fires are in northern B.C.?": "northern B.C.",
            "What fires are burning in northern B.C.?": "northern B.C.",
            "Are wildfires burning in northern B.C.?": "northern B.C.",
        }

        for question, label in cases.items():
            with self.subTest(question=question):
                self.assertEqual(directional_bc_region_label(question), label)
                self.assertIsNone(coarse_location_from_question(question))
                self.assertTrue(is_fire_geography_analysis(question))
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.LIVE,
                )
                self.assertEqual(
                    live_layers_for_question(question),
                    (LiveResultKind.INCIDENT,),
                )

    def test_named_places_with_direction_words_remain_community_queries(self) -> None:
        cases = {
            "Are there wildfires in North Vancouver right now?": "North Vancouver",
            "Are there wildfires near Northern Rockies right now?": "Northern Rockies",
            "Show current wildfires near South Hazelton.": "South Hazelton",
        }

        for question, expected_place in cases.items():
            with self.subTest(question=question):
                self.assertIsNone(directional_bc_region_label(question))
                self.assertFalse(is_fire_geography_analysis(question))
                location = coarse_location_from_question(question)
                self.assertIsNotNone(location)
                assert location is not None
                self.assertEqual(location.label, expected_place)

    def test_historical_or_explanatory_directional_regions_are_not_live_analysis(self) -> None:
        cases = (
            "Tell me about Northern B.C. wildfire history.",
            "How does wildfire geography affect southern British Columbia?",
            "Where will wildfires be in northern BC tomorrow?",
            "What is wildfire ecology in northern B.C.?",
            "What is wildfire history in northern B.C.?",
        )

        for question in cases:
            with self.subTest(question=question):
                self.assertIsNotNone(directional_bc_region_label(question))
                self.assertFalse(is_fire_geography_analysis(question))
                self.assertNotEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.LIVE,
                )
                self.assertEqual(live_layers_for_question(question), ())

    async def test_northern_bc_uses_roster_and_states_the_unvalidated_scope(self) -> None:
        service = _RosterService()
        agent = FireLensAgent(
            cast(Any, _NoStatic()),
            LiveAnswerCoordinator(cast(Any, service)),
        )

        execution = await agent.answer(
            QueryRequest(question="Where are the wildfires in northern B.C. right now?")
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(service.map_calls, 1)
        self.assertEqual(service.nearby_calls, 0)
        self.assertEqual(service.resolve_calls, 0)
        self.assertIsNone(execution.response.required_input)
        self.assertIn("do not provide a validated north/south classification", answer)
        self.assertIn("cannot determine which fetched incidents belong", answer)
        self.assertIn("Prince George Fire Centre has 2 incidents", answer)
        self.assertIn("Coastal Fire Centre has 1 incident", answer)
        self.assertNotIn("A BC place is needed", answer)


if __name__ == "__main__":
    unittest.main()
