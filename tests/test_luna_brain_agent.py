"""Characterization for the thin-app Luna brain. Not frozen benchmark labels."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import HttpUrl

from firelens.agent import AgentTool, FireLensAgent
from firelens.agent.chat import ChatToolCall, ChatTurn
from firelens.agent.packet import AgentPacket, live_record_fact
from firelens.agent.rails import output_rail_errors
from firelens.answering.live_analysis import compose_official_answer
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    CoarseResolvedLocation,
    ConversationTurn,
    EvidenceStatus,
    Freshness,
    GeometryRelation,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    MapContext,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.live import LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator


def _timestamp() -> datetime:
    return datetime(2026, 8, 15, tzinfo=UTC)


def _fire(
    *,
    result_id: str,
    name: str | None = None,
    status: str = "Being Held",
    size_hectares: float | None = None,
    fire_centre: str | None = None,
    incident_number: str | None = None,
    kind: LiveResultKind = LiveResultKind.INCIDENT,
    longitude: float = -119.5,
    latitude: float = 49.9,
    geometry: dict[str, object] | None = None,
    geometry_relation: GeometryRelation = GeometryRelation.UNKNOWN,
) -> LiveResult:
    stamp = _timestamp()
    return LiveResult(
        result_id=result_id,
        kind=kind,
        source_url=f"https://example.test/live/{result_id}",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status=status,
        name=name,
        incident_number=incident_number,
        size_hectares=size_hectares,
        fire_centre=fire_centre,
        geometry_relation=geometry_relation,
        geometry=geometry or {"type": "Point", "coordinates": [longitude, latitude]},
    )


class FixedLiveService:
    def __init__(
        self,
        results: list[LiveResult],
        *,
        map_results: list[LiveResult] | None = None,
        nearby_results: list[LiveResult] | None = None,
        roster_total: int | None = None,
    ) -> None:
        self.results = results
        self._map_results = map_results
        self._nearby_results = nearby_results
        self._roster_total = roster_total
        self.requested_location = None

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        return LiveMapResponse(
            generated_at=_timestamp(),
            results=self._map_results if self._map_results is not None else self.results,
        )

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        return 49.88, -119.49

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        self.requested_location = location
        page_results = (
            self._nearby_results if self._nearby_results is not None else self.results
        )
        total = self._roster_total if self._roster_total is not None else len(page_results)
        return type(
            "Nearby",
            (),
            {
                "results": page_results,
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": CoarseResolvedLocation(latitude=49.88, longitude=-119.49),
                "pagination": type("Pagination", (), {"total_results": total})(),
            },
        )()


class SilentStatic:
    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("this live characterization must not call static RAG")


def _kit_response(*, mode: ResponseMode) -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Include water, medication, and copies of important documents.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[
            ClaimSupport(
                evidence_id="E1",
                quote="Include water, medication, and copies of important documents.",
            )
        ],
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="k" * 32,
        response_mode=mode,
        answer="Include water, medication, and copies of important documents.",
        claims=[claim] if mode == ResponseMode.GROUNDED else [],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Reviewed emergency kit guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/kit"),
                locator="Section 1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Include water, medication, and copies of important documents.",
                context_text="Include water, medication, and copies of important documents.",
            )
        ]
        if mode == ResponseMode.GROUNDED
        else [],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        )
        if mode == ResponseMode.GROUNDED
        else None,
        limitations=(
            []
            if mode == ResponseMode.GROUNDED
            else ["General background — not verified against the FireLens corpus."]
        ),
    )


class KitStatic:
    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del request, args, kwargs
        return _kit_response(mode=ResponseMode.GROUNDED)


class AdjacentKitStatic:
    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del request, args
        if kwargs.get("prefer_reviewed_quotes"):
            return _kit_response(mode=ResponseMode.GROUNDED)
        return _kit_response(mode=ResponseMode.BACKGROUND)


def _agent(results: list[LiveResult], static: Any = None) -> FireLensAgent:
    return FireLensAgent(
        cast(Any, SilentStatic() if static is None else static),
        LiveAnswerCoordinator(cast(Any, FixedLiveService(results))),
    )


class InventingThenRewritingProvider:
    def __init__(self) -> None:
        self.turns = 0
        self.rewrites = 0

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        self.turns += 1
        joined = " ".join(str(message.get("content")) for message in messages)
        if "previous_answer_rejected_for" in joined:
            self.rewrites += 1
            return ChatTurn(content="Mountain Fire is Being Held in the official records.")
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_1",
                        name="list_official_fires",
                        arguments={"place_label": "Kelowna"},
                    ),
                ),
            )
        return ChatTurn(
            content=("You should evacuate now. Phantom Ridge Fire is at 123 Main Street.")
        )


class ProvinceLabelProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_bc",
                        name="list_official_fires",
                        arguments={"place_label": "British Columbia"},
                    ),
                ),
            )
        return ChatTurn(content="Official records list active wildfires.")


class LeaveNowDefinitionProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_def",
                        name="search_reviewed_guidance",
                        arguments={
                            "query": (
                                "What is the difference between an evacuation "
                                "alert and an order?"
                            )
                        },
                    ),
                ),
            )
        return ChatTurn(content="You should evacuate now from Kelowna.")


class CoordinateDumpProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(content="The perimeter point is 49.589303, -119.906732.")


class WriteOnlyProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(content="There are wildfires in British Columbia.")


class CapturingProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] | None = None

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if self.messages is None:
            self.messages = list(messages)
        del tools
        return ChatTurn(content="Ridge Fire is Being Held.")


class GetThenWriteProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_get",
                        name="get_official_fire",
                        arguments={"result_id": "incident:7"},
                    ),
                ),
            )
        return ChatTurn(content="Mountain Fire is Being Held.")


class ListKelownaProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_list",
                        name="list_official_fires",
                        arguments={"place_label": "Kelowna"},
                    ),
                ),
            )
        return ChatTurn(content="Other Fire is Being Held.")


class EvacProvinceProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_evac",
                        name="list_official_evacuations",
                        arguments={"place_label": "British Columbia"},
                    ),
                ),
            )
        return ChatTurn(content="No fetched official fire-related evacuation.")


class CountingMapService(FixedLiveService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.map_calls = 0
        self.nearby_calls = 0
        self.resolve_calls = 0

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        self.map_calls += 1
        return await super().map_results(*args, **kwargs)

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        self.nearby_calls += 1
        return await super().nearby_page(location, *args, **kwargs)

    async def resolve_location(self, location: Any) -> tuple[float, float]:
        self.resolve_calls += 1
        return await super().resolve_location(location)


class UnavailableLiveService:
    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        del args, kwargs
        raise LiveDataUnavailable("incident source is unavailable")

    async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise LiveDataUnavailable("incident source is unavailable")

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        raise LiveDataUnavailable("geocode unavailable")


class _ProviderStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("province-wide characterization must not call static RAG")


class _DefinitionStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        text = (
            "An evacuation alert means prepare to leave; an evacuation order "
            "means leave when officials issue it."
        )
        claim = PublicClaim(
            claim_id="C1",
            text=text,
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[
                ClaimSupport(
                    evidence_id="E1",
                    quote=text,
                )
            ],
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="d" * 32,
            response_mode=ResponseMode.GROUNDED,
            answer=text,
            claims=[claim],
            evidence=[
                PublicEvidence(
                    evidence_id="E1",
                    title="Reviewed evacuation definitions",
                    publisher="Government of British Columbia",
                    canonical_url=HttpUrl("https://example.test/evac"),
                    locator="Section 1",
                    temporal_class=TemporalClass.STABLE_GUIDANCE,
                    primary_text=(
                        "An evacuation alert means prepare to leave; an evacuation "
                        "order means leave when officials issue it."
                    ),
                    context_text=(
                        "An evacuation alert means prepare to leave; an evacuation "
                        "order means leave when officials issue it."
                    ),
                )
            ],
            validation=ValidationReport(
                accepted=True,
                citation_ids_valid=True,
                quotes_exact=True,
                claim_support_valid=True,
                policy_valid=True,
            ),
        )


class CountingStatic:
    def __init__(self, provider: InventingThenRewritingProvider) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("veto-rewrite characterization must not call static RAG")


class LunaBrainCharacterizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_closest_near_a_place_names_a_fetched_fire(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="where is the closest moutainfire near Kelowna")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(execution.tools, (AgentTool.LIST_OFFICIAL_FIRES,))
        self.assertIn("Mountain Fire", execution.response.answer or "")
        self.assertNotIn("capability", (execution.response.answer or "").casefold())
        self.assertEqual(execution.response.live_results[0].name, "Mountain Fire")

    async def test_max_hectares_uses_official_size_field(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Small Fire",
                    size_hectares=12.0,
                    fire_centre="Kamloops",
                ),
                _fire(
                    result_id="incident:2",
                    name="Ridge Fire",
                    size_hectares=840.0,
                    fire_centre="Southeast",
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="which BC mountain fire has the most burned hectares")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Ridge Fire", execution.response.answer or "")
        self.assertIn("840", execution.response.answer or "")
        self.assertNotIn("Small Fire", execution.response.answer or "")
        self.assertNotRegex(
            execution.response.answer or "",
            r"I (?:don't|do not) have that capability",
        )

    async def test_unknown_when_hectares_field_is_absent(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="which fire has the most burned hectares")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("do not report", (execution.response.answer or "").casefold())
        self.assertNotIn("840", execution.response.answer or "")

    async def test_geography_distribution_uses_official_centres(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Lake Fire",
                    fire_centre="Kamloops",
                    status="Out of Control",
                ),
                _fire(
                    result_id="incident:2",
                    name="Ridge Fire",
                    fire_centre="Southeast",
                    status="Being Held",
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="distribution of mountain fire geography")
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Kamloops", answer)
        self.assertIn("Southeast", answer)
        self.assertNotIn("Phantom", answer)

    async def test_kit_question_uses_reviewed_guidance(self) -> None:
        agent = _agent([], static=KitStatic())
        execution = await agent.answer(
            QueryRequest(question="What belongs in a grab-and-go bag?")
        )

        self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(
            execution.response.claims[0].supports[0].quote, execution.response.answer
        )
        self.assertFalse(execution.response.live_results)

    async def test_partial_layer_outage_response_survives_contract_revalidation(self) -> None:
        class PartialLive(FixedLiveService):
            async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
                layers = kwargs.get("layers")
                if layers and LiveResultKind.EVACUATION in layers:
                    raise LiveDataUnavailable("evacuation source is unavailable")
                return await super().map_results(*args, **kwargs)

            async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
                layers = kwargs.get("layers")
                if layers and LiveResultKind.EVACUATION in layers:
                    raise LiveDataUnavailable("evacuation source is unavailable")
                return await super().nearby_page(location, *args, **kwargs)

        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(
                cast(Any, PartialLive([_fire(result_id="incident:1", name="Ridge Fire")]))
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there fires and evacuation orders near Kelowna?")
        )

        response = execution.response
        self.assertIn(LiveResultKind.EVACUATION, response.unavailable_layers)
        # FastAPI revalidates the response model on serialization; a stale
        # history_text after the limitation append must not 500 a served Ask.
        AskResponse.model_validate(response.model_dump(mode="json"))

    async def test_precaution_near_mountain_fire_uses_reviewed_guidance_not_live(self) -> None:
        live = CountingMapService([])
        agent = FireLensAgent(
            cast(Any, KitStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        for question in (
            "what precaution should I take if I am near moutain fire",
            "What precautions should I take if I am near a mountain fire?",
        ):
            with self.subTest(question=question):
                live.map_calls = 0
                live.nearby_calls = 0
                live.resolve_calls = 0
                execution = await agent.answer(QueryRequest(question=question))
                self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
                self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
                self.assertFalse(execution.response.live_results)
                self.assertEqual(live.map_calls, 0)
                self.assertEqual(live.nearby_calls, 0)
                self.assertEqual(live.resolve_calls, 0)
                self.assertIn("water", (execution.response.answer or "").casefold())

    async def test_safety_language_is_vetoed_then_rewritten(self) -> None:
        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            LiveAnswerCoordinator(
                cast(
                    Any, FixedLiveService([_fire(result_id="incident:7", name="Mountain Fire")])
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertGreaterEqual(provider.rewrites, 1)
        answer = execution.response.answer or ""
        self.assertIn("Mountain Fire", answer)
        self.assertNotIn("evacuate", answer.casefold())
        self.assertNotIn("Phantom Ridge", answer)
        self.assertNotIn("123 Main", answer)

    async def test_input_seatbelt_blocks_evacuate_without_a_model_call(self) -> None:
        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(question="Should I evacuate from Kelowna right now?")
        )

        self.assertEqual(execution.route, QueryRoute.PROHIBITED)
        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(provider.turns, 0)
        self.assertIn("cannot provide", (execution.response.answer or "").casefold())

    async def test_named_place_how_close_is_not_unbound(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="perimeter:9",
                    name="Vernon Perimeter",
                    kind=LiveResultKind.PERIMETER,
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="How close is the wildfire perimeter near Vernon today?")
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertNotIn("Select a mapped fire", answer)
        self.assertIn("Vernon Perimeter", answer)
        self.assertRegex(answer, r"\d+(?:\.\d+)? km")

    async def test_deictic_distance_without_selection_still_abstains(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="How far is this fire from Kelowna?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertIn("Select a mapped fire", execution.response.answer or "")

    async def test_selected_id_missing_from_nearby_page_still_resolves(self) -> None:
        selected = _fire(result_id="incident:101", name="Far Fire")
        fillers = [
            _fire(result_id=f"incident:{index}", name=f"Filler {index}") for index in range(100)
        ]
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(
                cast(
                    Any,
                    FixedLiveService(
                        fillers,
                        nearby_results=fillers,
                        map_results=[*fillers, selected],
                    ),
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What source reported it?",
                context=MapContext(selected_live_result_id="incident:101"),
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Far Fire", execution.response.answer or "")
        self.assertEqual(execution.response.selected_live_result_id, "incident:101")

    async def test_closest_uses_minimum_distance_not_first_record(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Far Fire",
                    longitude=-123.0,
                    latitude=49.0,
                ),
                _fire(
                    result_id="incident:2",
                    name="Near Fire",
                    longitude=-119.49,
                    latitude=49.88,
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="What is the closest wildfire near Kelowna?")
        )

        answer = execution.response.answer or ""
        self.assertIn("Near Fire", answer)
        self.assertNotIn("Far Fire", answer)

    async def test_two_largest_compare_uses_official_sizes(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Small Fire", size_hectares=12.0),
                _fire(result_id="incident:2", name="Ridge Fire", size_hectares=840.0),
                _fire(result_id="incident:3", name="Lake Fire", size_hectares=200.0),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Compare the two largest BC mountain fires by hectares")
        )

        answer = execution.response.answer or ""
        self.assertIn("Ridge Fire", answer)
        self.assertIn("Lake Fire", answer)
        self.assertNotIn("Small Fire", answer)

    async def test_oldest_says_start_field_is_absent(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="Which official fire is the oldest?")
        )

        self.assertIn("do not report", (execution.response.answer or "").casefold())
        self.assertIn("start", (execution.response.answer or "").casefold())
        self.assertNotIn("Current official information:", execution.response.answer or "")

    async def test_named_fire_existence_does_not_list_substitutes(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="Is there a fire called Phantom Ridge Fire?")
        )

        answer = execution.response.answer or ""
        self.assertIn("No fetched official record is named Phantom Ridge Fire", answer)
        self.assertNotIn("Mountain Fire", answer)

    async def test_fire_number_is_used_when_name_is_missing(self) -> None:
        agent = _agent(
            [_fire(result_id="incident:7", incident_number="K21320", status="Being Held")]
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertIn("K21320", execution.response.answer or "")
        self.assertNotIn("Unnamed official record", execution.response.answer or "")

    async def test_unknown_geometry_is_not_treated_as_closest(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Broken Geometry Fire",
                    geometry={"type": "Polygon", "coordinates": []},
                ),
                _fire(
                    result_id="incident:2",
                    name="Locatable Fire",
                    longitude=-119.2,
                    latitude=49.7,
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="What is the closest wildfire near Kelowna?")
        )

        answer = execution.response.answer or ""
        self.assertIn("Locatable Fire", answer)
        self.assertNotIn("Broken Geometry Fire", answer)

    async def test_province_count_does_not_treat_page_size_as_total(self) -> None:
        page = [
            _fire(result_id=f"incident:{index}", name=f"Fire {index}") for index in range(100)
        ]
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, FixedLiveService(page, roster_total=240))),
        )
        execution = await agent.answer(
            QueryRequest(question="How many wildfires near Kelowna right now?")
        )

        answer = execution.response.answer or ""
        self.assertIn("100 of 240", answer)
        self.assertNotRegex(answer, r"contains 100 incident records and 0 perimeter")

    async def test_evac_yes_no_answers_the_asked_place(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.NEARBY,
                    status="Order",
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("Kelowna Order", answer)
        self.assertIn("not a stay-or-leave", answer.casefold())

    async def test_static_guidance_preserves_selected_record_id(self) -> None:
        agent = _agent([], static=KitStatic())
        execution = await agent.answer(
            QueryRequest(
                question="What belongs in a grab-and-go bag?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")

    async def test_guidance_tool_keeps_quotes_when_planner_is_adjacent(self) -> None:
        agent = _agent([], static=AdjacentKitStatic())
        execution = await agent.answer(
            QueryRequest(
                question="According to the official guide, what belongs in a grab-and-go bag?"
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertIn("water", (execution.response.answer or "").casefold())
        self.assertNotIn("not verified", (execution.response.answer or "").casefold())

    async def test_province_wide_place_label_uses_full_layer_not_nearby(self) -> None:
        live = FixedLiveService(
            [],
            map_results=[_fire(result_id="incident:9", name="Ridge Fire", size_hectares=840.0)],
            nearby_results=[],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ProvinceLabelProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertIsNone(live.requested_location)
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(execution.response.live_results[0].name, "Ridge Fire")
        self.assertNotEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)

    async def test_write_without_tools_still_fetches_official_fires(self) -> None:
        live = FixedLiveService(
            [_fire(result_id="incident:9", name="Ridge Fire", size_hectares=840.0)]
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertTrue(execution.response.live_results)
        self.assertEqual(execution.response.live_results[0].name, "Ridge Fire")

    async def test_definition_keeps_quotes_when_luna_uses_leave_now(self) -> None:
        agent = FireLensAgent(
            cast(Any, _DefinitionStatic(LeaveNowDefinitionProvider())),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the difference between an evacuation alert and an order?"
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertIn("alert", (execution.response.answer or "").casefold())
        self.assertIn("order", (execution.response.answer or "").casefold())
        self.assertNotEqual(execution.response.response_mode, ResponseMode.ABSTENTION)

    async def test_analysis_composer_wins_after_prefetch(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(
                cast(
                    Any,
                    FixedLiveService(
                        [
                            _fire(
                                result_id="incident:1",
                                name="Small Fire",
                                size_hectares=12.0,
                            ),
                            _fire(
                                result_id="incident:2",
                                name="Ridge Fire",
                                size_hectares=840.0,
                            ),
                        ]
                    ),
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="which BC mountain fire has the most burned hectares")
        )

        self.assertIn("Ridge Fire", execution.response.answer or "")
        self.assertIn("840", execution.response.answer or "")
        self.assertNotIn(
            "There are wildfires in British Columbia.", execution.response.answer or ""
        )

    async def test_existence_miss_does_not_list_substitutes(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(
                cast(
                    Any, FixedLiveService([_fire(result_id="incident:2", name="Mountain Fire")])
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="is there a wildfire called Phantom Ridge Fire in BC")
        )

        answer = execution.response.answer or ""
        self.assertIn("No fetched official record is named Phantom Ridge Fire", answer)
        self.assertNotIn("Mountain Fire", answer)

    async def test_published_answer_strips_precise_coordinates(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(CoordinateDumpProvider())),
            LiveAnswerCoordinator(
                cast(Any, FixedLiveService([_fire(result_id="incident:2", name="Ridge Fire")]))
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertNotIn("49.589303", execution.response.answer or "")
        self.assertIn("official mapped geometry", execution.response.answer or "")

    async def test_official_packet_omits_raw_coordinates(self) -> None:
        fact = live_record_fact(_fire(result_id="incident:2", name="Ridge Fire"))
        self.assertNotIn("coordinates", fact)
        self.assertNotIn("geometry", fact)
        self.assertEqual(fact["source_updated_at"], "2026-08-15T00:00:00+00:00")

    async def test_provider_first_user_turn_uses_content_key_with_packet(self) -> None:
        provider = CapturingProvider()
        live = FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(provider)),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        await agent.answer(QueryRequest(question="Are there active wildfires in BC currently?"))

        assert provider.messages is not None
        user = provider.messages[1]
        self.assertEqual(user["role"], "user")
        self.assertIn("content", user)
        self.assertNotIn("            content", user)
        payload = json.loads(user["content"])
        self.assertEqual(payload["question"], "Are there active wildfires in BC currently?")
        self.assertEqual(payload["history"], [])
        self.assertIn("official_packet", payload)
        self.assertEqual(
            payload["official_packet"]["official_records"][0]["name"], "Ridge Fire"
        )

    async def test_provider_first_user_turn_includes_bounded_history(self) -> None:
        provider = CapturingProvider()
        live = FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(provider)),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        history = (
            ConversationTurn(role="user", content="Are there active wildfires near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Official BC Wildfire Service records show Ridge Fire near Kelowna.",
            ),
        )
        await agent.answer(
            QueryRequest(
                question="How large is that fire?",
                history=list(history),
            )
        )

        assert provider.messages is not None
        payload = json.loads(provider.messages[1]["content"])
        self.assertEqual(payload["question"], "How large is that fire?")
        self.assertEqual(
            payload["history"],
            [turn.model_dump(mode="json") for turn in history],
        )

    def test_compose_official_answer_does_not_substitute_selected(self) -> None:
        answer = compose_official_answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            ),
            [_fire(result_id="incident:8", name="Other Fire")],
        )
        self.assertIn("will not substitute", answer)
        self.assertNotIn("Other Fire", answer)

    async def test_missing_selected_record_does_not_substitute_nearby(self) -> None:
        live = FixedLiveService(
            [_fire(result_id="incident:8", name="Other Fire")],
            map_results=[],
            nearby_results=[_fire(result_id="incident:8", name="Other Fire")],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ListKelownaProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(execution.response.status, ResponseStatus.ABSTENTION)
        self.assertIn("did not substitute", " ".join(execution.response.limitations))
        self.assertNotIn("Other Fire", execution.response.answer or "")

    async def test_evac_yes_no_uses_annotated_relation(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.UNKNOWN,
                    status="Order",
                    longitude=-119.49,
                    latitude=49.88,
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("Kelowna Order", answer)

    async def test_province_wide_evac_fetch_annotates_asked_place(self) -> None:
        live = FixedLiveService(
            [],
            map_results=[
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.UNKNOWN,
                    status="Order",
                    longitude=-119.49,
                    latitude=49.88,
                )
            ],
            nearby_results=[],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(EvacProvinceProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("Kelowna Order", answer)

    async def test_unsupported_selected_redirect_uses_requested_id(self) -> None:
        live = FixedLiveService(
            [
                _fire(result_id="incident:7", name="First Fire"),
                _fire(result_id="incident:8", name="Selected Fire"),
            ]
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ListKelownaProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="Why did this fire start?",
                context=MapContext(selected_live_result_id="incident:8"),
            )
        )

        self.assertEqual(execution.response.selected_live_result_id, "incident:8")
        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)

    async def test_selected_fetch_skips_duplicate_map_results(self) -> None:
        live = CountingMapService(
            [_fire(result_id="incident:7", name="Mountain Fire")],
            map_results=[_fire(result_id="incident:7", name="Mountain Fire")],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(GetThenWriteProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        await agent.answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(live.map_calls, 1)

    async def test_unavailable_layers_are_surfaced_on_ask(self) -> None:
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, UnavailableLiveService())),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertIn(LiveResultKind.INCIDENT, execution.response.unavailable_layers)
        self.assertTrue(
            any("unavailable" in item.casefold() for item in execution.response.limitations)
        )

    async def test_selected_update_question_uses_packet_timestamp(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(
                question="When was this fire last updated?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertIn("2026-08-15", execution.response.answer or "")

    def test_kilometre_rail_allows_radius_phrasing(self) -> None:
        errors = output_rail_errors(
            "Search used a 50 km radius around the community.", AgentPacket()
        )
        self.assertNotIn("invented_kilometre", errors)

    def test_unfetched_feed_rail_vetoes_aqhi_claims(self) -> None:
        errors = output_rail_errors("The AQHI is 3 in Kelowna.", AgentPacket())
        self.assertIn("unfetched_live_feed", errors)

    def test_unfetched_feed_rail_allows_official_handoff(self) -> None:
        errors = output_rail_errors(
            "FireLens is not connected to an official live source for air quality. "
            "Open the related official service for the current value: Current B.C. AQHI.",
            AgentPacket(unknown_topics=["air quality"]),
        )
        self.assertNotIn("unfetched_live_feed", errors)

    async def test_public_ask_seatbelt_does_not_use_legacy_live_composer(self) -> None:
        class ForbiddenCoordinator(LiveAnswerCoordinator):
            async def answer(self, request: QueryRequest, static_result: Any) -> AskResponse:
                del request, static_result
                raise AssertionError("public Ask must not use the legacy live answering path")

        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            ForbiddenCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the current air quality in Kelowna and should I evacuate?"
            )
        )

        self.assertEqual(execution.route, QueryRoute.PROHIBITED)
        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(provider.turns, 0)
        self.assertIn("cannot provide", (execution.response.answer or "").casefold())
