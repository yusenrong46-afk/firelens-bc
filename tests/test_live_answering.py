from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from firelens.contracts import (
    CoarseResolvedLocation,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapContext,
    QueryRequest,
    RequiredInputKind,
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

    async def nearby_page(self, *args, **kwargs):
        return self.response

    async def resolve_location(self, location):
        if location.latitude is None or location.longitude is None:
            return 49.0, -123.0
        return location.latitude, location.longitude


class CapturingNearbyService(FixedLiveService):
    def __init__(self, response: object) -> None:
        super().__init__(cast(Any, response))
        self.requested_location: LocationInput | None = None

    async def nearby_page(self, location, *args, **kwargs):
        self.requested_location = location
        return self.response


class LiveAnswerCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_record_detail_phrasings_preserve_map_context(self) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        result = LiveResult(
            result_id="incident:7",
            kind=LiveResultKind.INCIDENT,
            source_url="https://example.test/live/7",
            source_updated_at=timestamp,
            retrieved_at=timestamp,
            freshness=Freshness.FRESH,
            status="Being Held",
            name="Mountain Fire",
            size_hectares=123.4,
            geometry={"type": "Point", "coordinates": [-123.0, 50.0]},
        )
        coordinator = LiveAnswerCoordinator(
            cast(
                Any,
                FixedLiveService(LiveMapResponse(generated_at=timestamp, results=[result])),
            )
        )

        for question in (
            "What is the current status of this fire?",
            "What is happening with the selected wildfire?",
            "Give me the official details for this incident.",
            "When was this fire record updated?",
            "How large is this fire?",
        ):
            with self.subTest(question=question):
                request = QueryRequest(
                    question=question,
                    context=MapContext(selected_live_result_id="incident:7"),
                )
                self.assertTrue(coordinator.handles(request))
                response = await coordinator.answer(request, None)
                self.assertEqual(response.status, ResponseStatus.ANSWER)
                self.assertEqual(response.response_mode, ResponseMode.LIVE)
                self.assertEqual(response.selected_live_result_id, "incident:7")
                self.assertEqual(
                    [item.result_id for item in response.live_results],
                    ["incident:7"],
                )

    async def test_named_community_is_geocoded_without_a_redundant_prompt(self) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        result = LiveResult(
            result_id="incident:kelowna",
            kind=LiveResultKind.INCIDENT,
            source_url="https://example.test/live/kelowna",
            source_updated_at=timestamp,
            retrieved_at=timestamp,
            freshness=Freshness.FRESH,
            status="Out of Control",
            name="Kelowna Area Fire",
            geometry={"type": "Point", "coordinates": [-119.45, 49.9]},
        )
        live = SimpleNamespace(
            results=[result],
            limitations=[],
            unavailable_layers=[],
            resolved_location=CoarseResolvedLocation(
                latitude=49.89,
                longitude=-119.5,
            ),
        )
        service = CapturingNearbyService(live)
        coordinator = LiveAnswerCoordinator(cast(Any, service))

        response = await coordinator.answer(
            QueryRequest(question="Where are the current wildfires in Kelowna?"),
            None,
        )

        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertIsNone(response.required_input)
        self.assertEqual(response.resolved_location, live.resolved_location)
        self.assertIsNotNone(service.requested_location)
        assert service.requested_location is not None
        self.assertEqual(service.requested_location.label, "Kelowna")

    async def test_named_community_no_result_still_returns_a_focused_map_state(self) -> None:
        live = SimpleNamespace(
            results=[],
            limitations=[],
            unavailable_layers=[],
            resolved_location=CoarseResolvedLocation(
                latitude=49.89,
                longitude=-119.5,
            ),
        )
        coordinator = LiveAnswerCoordinator(cast(Any, CapturingNearbyService(live)))

        response = await coordinator.answer(
            QueryRequest(question="Show the wildfire situation around Kelowna."),
            None,
        )

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertEqual(response.live_results, [])
        self.assertEqual(response.resolved_location, live.resolved_location)
        self.assertIn("No matching official record", response.answer)

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
        self.assertEqual(response.aggregate_freshness, "stale")
        self.assertNotIn("Current official information", response.answer)
        self.assertIn("Cached official information", response.answer)
        self.assertTrue(
            any("refresh failed" in item.casefold() for item in response.limitations)
        )

    async def test_mixed_freshness_has_typed_state_and_no_current_wording(self) -> None:
        timestamp = datetime(2026, 7, 28, tzinfo=UTC)
        live = LiveMapResponse(
            generated_at=timestamp,
            results=[
                LiveResult(
                    result_id=f"incident:{index}",
                    kind=LiveResultKind.INCIDENT,
                    source_url=f"https://example.test/live/{index}",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=freshness,
                    status="Out of Control",
                    name=f"Test Fire {index}",
                    geometry={"type": "Point", "coordinates": [-123.5, 49.5]},
                )
                for index, freshness in enumerate((Freshness.FRESH, Freshness.STALE), start=1)
            ],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(live)))

        response = await coordinator.answer(
            QueryRequest(question="What active wildfires are in BC currently?"), None
        )

        self.assertEqual(response.aggregate_freshness, "mixed")
        self.assertNotIn("current", response.answer.casefold())
        self.assertNotIn("latest", response.answer.casefold())
        self.assertTrue(any("stale cached" in item.casefold() for item in response.limitations))

    async def test_missing_location_requests_input_before_live_fetch(self) -> None:
        live_service = UnexpectedLiveService()
        coordinator = LiveAnswerCoordinator(cast(Any, live_service))

        response = await coordinator.answer(
            QueryRequest(question="Are there active wildfires near me right now?"), None
        )

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.REQUIRES_INPUT)
        self.assertIsNotNone(response.required_input)
        assert response.required_input is not None
        self.assertEqual(response.required_input.kind, RequiredInputKind.LOCATION)
        self.assertEqual(live_service.calls, 0)
        self.assertIn("approximate location", response.answer)

    async def test_distance_followup_uses_selected_map_result(self) -> None:
        timestamp = datetime(2026, 7, 28, tzinfo=UTC)
        live = LiveMapResponse(
            generated_at=timestamp,
            results=[
                LiveResult(
                    result_id="incident:7",
                    kind=LiveResultKind.INCIDENT,
                    source_url="https://example.test/live/7",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=Freshness.FRESH,
                    status="Out of Control",
                    name="Mountain Fire",
                    geometry={"type": "Point", "coordinates": [-123.0, 50.0]},
                ),
                LiveResult(
                    result_id="incident:8",
                    kind=LiveResultKind.INCIDENT,
                    source_url="https://example.test/live/8",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=Freshness.FRESH,
                    status="Being Held",
                    name="Other Fire",
                    geometry={"type": "Point", "coordinates": [-124.0, 50.0]},
                ),
            ],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(live)))

        response = await coordinator.answer(
            QueryRequest(
                question="How far is it from me?",
                location=LocationInput(latitude=49.0, longitude=-123.0),
                context=MapContext(selected_live_result_id="incident:7"),
            ),
            None,
        )

        self.assertTrue(
            coordinator.handles(
                QueryRequest(
                    question="How far is it from me?",
                    context=MapContext(selected_live_result_id="incident:7"),
                )
            )
        )
        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertEqual(response.selected_live_result_id, "incident:7")
        self.assertEqual([item.result_id for item in response.live_results], ["incident:7"])
        self.assertGreater(response.live_results[0].distance_km or 0, 111.0)
        self.assertIn("straight-line", response.answer)

    async def test_distance_followup_never_substitutes_for_an_unmatched_selection(self) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        live = LiveMapResponse(
            generated_at=timestamp,
            results=[
                LiveResult(
                    result_id="incident:7",
                    kind=LiveResultKind.INCIDENT,
                    source_url="https://example.test/live/7",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=Freshness.FRESH,
                    status="Out of Control",
                    name="Other Fire",
                    geometry={"type": "Point", "coordinates": [-123.0, 49.0]},
                )
            ],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(live)))

        response = await coordinator.answer(
            QueryRequest(
                question="How far is this fire from me?",
                location=LocationInput(label="Vancouver"),
                context=MapContext(selected_live_result_id="evacuation:99"),
            ),
            None,
        )

        self.assertEqual(response.status, ResponseStatus.ABSTENTION)
        self.assertEqual(response.selected_live_result_id, "evacuation:99")
        self.assertEqual(response.live_results, [])
        self.assertTrue(
            any(
                "did not substitute a different nearby fire" in item
                for item in response.limitations
            )
        )

    async def test_status_followup_returns_only_the_selected_map_result(self) -> None:
        timestamp = datetime(2026, 7, 28, tzinfo=UTC)
        live = LiveMapResponse(
            generated_at=timestamp,
            results=[
                LiveResult(
                    result_id=f"incident:{index}",
                    kind=LiveResultKind.INCIDENT,
                    source_url=f"https://example.test/live/{index}",
                    source_updated_at=timestamp,
                    retrieved_at=timestamp,
                    freshness=Freshness.FRESH,
                    status=status,
                    name=name,
                    geometry={"type": "Point", "coordinates": [-123.0 - index, 50.0]},
                )
                for index, status, name in (
                    (7, "Out of Control", "Mountain Fire"),
                    (8, "Being Held", "Other Fire"),
                )
            ],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(live)))
        request = QueryRequest(
            question="What is happening with this fire?",
            context=MapContext(selected_live_result_id="incident:7"),
        )

        response = await coordinator.answer(request, None)

        self.assertTrue(coordinator.handles(request))
        self.assertEqual([item.result_id for item in response.live_results], ["incident:7"])
        self.assertIn("Mountain Fire", response.answer)
        self.assertNotIn("Other Fire", response.answer)

    async def test_unsupported_live_topic_is_not_substituted(self) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        live_service = FixedLiveService(LiveMapResponse(generated_at=timestamp, results=[]))
        coordinator = LiveAnswerCoordinator(cast(Any, live_service))

        response = await coordinator.answer(
            QueryRequest(question="What is the current air quality in Kelowna?"), None
        )

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertEqual(response.live_results, [])
        self.assertIsNotNone(response.resolved_location)
        self.assertIn("not connected", response.answer)
        self.assertTrue(response.related_links)
        self.assertEqual(response.related_links[0].title, "Current B.C. AQHI")

    async def test_safe_drive_question_redirects_to_drivebc_and_focuses_named_place(
        self,
    ) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        coordinator = LiveAnswerCoordinator(
            cast(
                Any,
                FixedLiveService(LiveMapResponse(generated_at=timestamp, results=[])),
            )
        )
        request = QueryRequest(
            question="Tell me whether it is safe to drive to Kelowna right now."
        )

        self.assertTrue(coordinator.handles(request))
        response = await coordinator.answer(request, None)

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertIsNotNone(response.resolved_location)
        self.assertEqual(response.related_links[0].title, "DriveBC road conditions")
        self.assertIn("cannot verify", response.answer)

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
