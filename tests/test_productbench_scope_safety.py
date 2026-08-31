"""Exact ProductBench scope and useful-safety regression locks."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from test_luna_brain_agent import (
    CountingMapService,
    InventingThenRewritingProvider,
    RecordingStatic,
    UnavailableLiveService,
    _background_response,
    _fire,
    _kit_response,
)

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import (
    AgentGeography,
    AgentRequestMode,
    AgentScopeResult,
    build_agent_query_plan,
    plan_agent_request,
)
from firelens.agent.tools import AgentTool
from firelens.answering.intent import live_layers_for_question, plan_query
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    LiveResultKind,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
)
from firelens.live import LiveDataErrorKind, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator


def _sync_test(function: Any) -> Any:
    def run() -> None:
        asyncio.run(function())

    run.__name__ = function.__name__
    return run


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Show me active fires within 50 km of Kamloops.", "Kamloops"),
        ("Which fire near Kelowna is closest to the city?", "Kelowna"),
    ),
)
def test_pb02_pb06_exact_places_bind_one_location_radius(
    question: str,
    place: str,
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.live_location_candidates == (place,)
    assert location is not None
    assert location.label == place
    assert location.radius_km == 50
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.tool_calls[0].as_arguments() == {"place_label": place}


def test_pb12_exact_alert_action_is_reviewed_guidance_without_live_authority() -> None:
    question = "What should I do if I’m under an evacuation alert?"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert plan.route == QueryRoute.RELATED
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.geography == AgentGeography.NONE
    assert plan.live_layers == ()
    assert [call.name for call in plan.tool_calls] == [AgentTool.SEARCH_REVIEWED_GUIDANCE]


def test_pb18_exact_being_held_clause_preserves_live_and_reviewed_lanes() -> None:
    question = "Show the fires near Kamloops and explain what “Being Held” means."
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.has_reviewed_guidance
    assert parsed.reviewed_guidance_text == "explain what “Being Held” means"
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kamloops"
    assert plan.static_subrequest == "explain what “Being Held” means"
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]


def test_pb21_natural_place_language_is_a_bounded_live_lookup() -> None:
    question = "I’m in downtown Kelowna. Anything nearby I should know about?"
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.live_location_candidates == ("Kelowna",)
    assert location is not None and location.label == "Kelowna"
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kelowna"
    assert plan.live_layers == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
        LiveResultKind.EVACUATION,
    )
    assert all(call.as_arguments() == {"place_label": "Kelowna"} for call in plan.tool_calls)


@pytest.mark.parametrize("place", ("West Kelowna", "North Vancouver"))
def test_pb21_normalization_preserves_legitimate_directional_locality_names(
    place: str,
) -> None:
    question = f"I’m in {place}. Anything nearby I should know about?"

    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)

    assert parsed.live_location_candidates == (place,)
    assert location is not None
    assert location.label == place


@_sync_test
async def test_pb21_modifier_is_normalized_before_exact_locality_resolution() -> None:
    class ExactLocalityMapService(CountingMapService):
        def __init__(self) -> None:
            super().__init__([])
            self.resolved_labels: list[str | None] = []

        async def resolve_location(self, location: Any) -> tuple[float, float]:
            self.resolve_calls += 1
            self.resolved_labels.append(location.label)
            if location.label != "Kelowna":
                raise LiveDataUnavailable(
                    "the place label did not exactly match a British Columbia community",
                    kind=LiveDataErrorKind.NOT_FOUND,
                )
            return 49.88, -119.49

    service = ExactLocalityMapService()
    plan = await build_agent_query_plan(
        QueryRequest(question="I’m in downtown Kelowna. Anything nearby I should know about?"),
        LiveAnswerCoordinator(cast(Any, service)),
    )

    assert service.resolved_labels == ["Kelowna"]
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.scope_result == AgentScopeResult.READY
    assert plan.location_label == "Kelowna"


def test_pb22_no_orders_is_an_explicit_no_all_clear_location_prompt() -> None:
    question = "There are no evacuation orders on your map. Does that mean I’m safe?"
    request = QueryRequest(question=question)
    plan = plan_agent_request(request)

    assert is_empty_map_safety_inference(question)
    assert plan_query(request).route == QueryRoute.LIVE
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.REQUIRES_INPUT
    assert plan.tool_calls == ()
    assert plan.terminal_response is not None
    response = plan.terminal_response
    assert response.response_mode == ResponseMode.REQUIRES_INPUT
    assert response.required_input is not None
    assert response.required_input.continuation_question == (
        "Show current evacuation alerts and orders near my place."
    )
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert public.startswith("no.")
    assert "does not mean you are safe" in public
    assert "not an all-clear" in public
    assert {link.title for link in response.related_links} == {
        "BC Wildfire Service map",
        "EmergencyInfoBC",
    }


@_sync_test
async def test_pb12_public_path_uses_static_service_and_no_live_lookup() -> None:
    question = "What should I do if I’m under an evacuation alert?"
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question=question))

    assert execution.route == QueryRoute.RELATED
    assert execution.response.response_mode == ResponseMode.GROUNDED
    assert execution.tools == (AgentTool.SEARCH_REVIEWED_GUIDANCE,)
    assert len(static.calls) == 1
    assert live.map_calls == 0
    assert live.nearby_calls == 0
    assert live.resolve_calls == 0


@_sync_test
async def test_pb21_public_path_uses_bounded_official_layers_without_static_rag() -> None:
    question = "I’m in downtown Kelowna. Anything nearby I should know about?"
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    static.provider = provider
    live = CountingMapService([_fire(result_id="incident:21", name="Ridge Fire")])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question=question))

    assert execution.route == QueryRoute.LIVE
    assert execution.response.response_mode == ResponseMode.LIVE
    assert live.nearby_calls > 0
    assert live.map_calls == 0
    assert len(static.calls) == 0
    assert provider.turns == 0


@_sync_test
async def test_refresh_uses_a_new_live_snapshot_without_inventing_a_delta() -> None:
    static = RecordingStatic(_background_response())
    live = CountingMapService([_fire(result_id="incident:refresh", name="Refresh Fire")])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(
        QueryRequest(question="Refresh the wildfire data and tell me whether anything changed.")
    )

    public = " ".join([execution.response.answer or "", *execution.response.limitations])
    assert execution.route == QueryRoute.LIVE
    assert execution.response.response_mode == ResponseMode.LIVE
    assert "current official snapshot" in public.casefold()
    assert "does not retain a prior official snapshot" in public.casefold()
    assert live.map_calls == 1
    assert live.nearby_calls == 0
    assert len(static.calls) == 0


@_sync_test
async def test_unavailable_refresh_never_claims_that_a_snapshot_was_fetched() -> None:
    static = RecordingStatic(_background_response())
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, UnavailableLiveService())),
    ).answer(
        QueryRequest(question="Refresh the wildfire data and tell me whether anything changed.")
    )

    public = " ".join([execution.response.answer or "", *execution.response.limitations])
    assert execution.response.response_mode == ResponseMode.ABSTENTION
    assert "official live wildfire layers were unavailable" in public.casefold()
    assert "fetched a current official snapshot" not in public.casefold()
    assert len(static.calls) == 0


@_sync_test
async def test_pb22_public_path_requires_location_without_fetch_or_model() -> None:
    question = "There are no evacuation orders on your map. Does that mean I’m safe?"
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question=question))

    assert execution.route == QueryRoute.LIVE
    assert execution.response.response_mode == ResponseMode.REQUIRES_INPUT
    assert execution.response.reason_code == ReasonCode.LIVE_DATA_REQUIRED
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == 0
    assert live.nearby_calls == 0
    assert live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_pb23_keeps_decision_block_but_offers_bounded_official_check() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="Should I evacuate right now?"))

    response = execution.response
    assert execution.route == QueryRoute.PROHIBITED
    assert response.response_mode == ResponseMode.REQUIRES_INPUT
    assert response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert response.required_input is not None
    assert response.required_input.continuation_question == (
        "Show current evacuation alerts and orders near my place."
    )
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert "cannot decide whether you should evacuate" in public
    assert "check official evacuation alerts and orders" in public
    assert {link.title for link in response.related_links} == {
        "BC Wildfire Service map",
        "EmergencyInfoBC",
    }
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_personalized_evacuation_with_place_offers_check_without_lookup() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="Should I evacuate from Kelowna?"))

    response = execution.response
    assert execution.route == QueryRoute.PROHIBITED
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert response.required_input is None
    assert "kelowna" in (response.answer or "").casefold()
    assert {link.title for link in response.related_links} == {
        "BC Wildfire Service map",
        "EmergencyInfoBC",
    }
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_pb24_blocks_route_choice_and_hands_off_without_retrieval() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(
        QueryRequest(question="What road should my family take to get away from the fire?")
    )

    response = execution.response
    assert execution.route == QueryRoute.PROHIBITED
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert "cannot choose an evacuation road or route" in public
    assert "follow instructions from the issuing local authority" in public
    assert {link.title for link in response.related_links} == {
        "DriveBC road conditions",
        "EmergencyInfoBC",
    }
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@pytest.mark.parametrize(
    "question",
    (
        "what is the most common mistake to make when wildfire is coming",
        "what are some things not needed for the bag",
    ),
)
def test_prior_ordinary_guidance_language_stays_conversational_without_live_scope(
    question: str,
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route in {QueryRoute.RELATED, QueryRoute.TANGENT}
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.geography == AgentGeography.NONE
    assert plan.live_layers == ()
    assert all(
        call.name
        not in {
            AgentTool.LIST_OFFICIAL_FIRES,
            AgentTool.LIST_OFFICIAL_EVACUATIONS,
        }
        for call in plan.tool_calls
    )


@_sync_test
async def test_false_no_fire_premise_is_corrected_without_fetching_a_roster() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_background_response())
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(
        QueryRequest(
            question="There are no fires within 50 km, so there is nothing to worry about, right?"
        )
    )

    response = execution.response
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.reason_code == ReasonCode.LIVE_DATA_REQUIRED
    assert public.startswith("no.")
    assert "does not establish" in public
    assert "all-clear" in public
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_evacuation_alert_cannot_be_ignored_based_on_fire_distance() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_background_response())
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="Can I ignore an evacuation alert if the fire is far away?"))

    response = execution.response
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert public.startswith("no.")
    assert "do not ignore an evacuation alert" in public
    assert "authority that issued the alert" in public
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_stock_market_wildfire_metaphor_stays_in_labelled_background() -> None:
    static = RecordingStatic(_background_response())
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="Is the stock market a wildfire right now?"))

    assert execution.route == QueryRoute.TANGENT
    assert execution.response.response_mode == ResponseMode.BACKGROUND
    assert execution.tools == (AgentTool.ANSWER_GENERAL_BACKGROUND,)
    assert len(static.calls) == 1
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0


@_sync_test
async def test_driving_for_fuel_is_usefully_handed_off_without_live_roster() -> None:
    provider = InventingThenRewritingProvider()
    static = RecordingStatic(_background_response())
    static.provider = provider
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="Can I drive to get gas if there is a wildfire nearby?"))

    response = execution.response
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert "cannot decide whether you should drive for fuel" in public
    assert "drivebc" in public
    assert execution.tools == ()
    assert len(static.calls) == 0
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
    assert provider.turns == 0


@_sync_test
async def test_general_fuel_preparedness_stays_useful_without_live_dispatch() -> None:
    static = RecordingStatic(_background_response())
    live = CountingMapService([])
    execution = await FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, live)),
    ).answer(QueryRequest(question="What should I do about gas when wildfire is coming?"))

    assert execution.response.response_mode == ResponseMode.BACKGROUND
    assert execution.tools == (AgentTool.ANSWER_GENERAL_BACKGROUND,)
    assert len(static.calls) == 1
    assert live.map_calls == live.nearby_calls == live.resolve_calls == 0


@_sync_test
async def test_prior_general_and_guidance_prompts_keep_typed_authority_lanes() -> None:
    cases = (
        (
            "what is the most common mistake to make when wildfire is coming",
            _background_response(),
            ResponseMode.BACKGROUND,
            AgentTool.ANSWER_GENERAL_BACKGROUND,
        ),
        (
            "what are some things not needed for the bag",
            _background_response(),
            ResponseMode.BACKGROUND,
            AgentTool.ANSWER_GENERAL_BACKGROUND,
        ),
        (
            "what should I know about wildfire smoke",
            _kit_response(mode=ResponseMode.GROUNDED),
            ResponseMode.GROUNDED,
            AgentTool.SEARCH_REVIEWED_GUIDANCE,
        ),
        (
            "Who won the Stanley Cup?",
            _background_response(),
            ResponseMode.BACKGROUND,
            AgentTool.ANSWER_GENERAL_BACKGROUND,
        ),
    )
    for question, canned, expected_mode, expected_tool in cases:
        static = RecordingStatic(canned)
        live = CountingMapService([])
        execution = await FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(QueryRequest(question=question))

        assert execution.response.response_mode == expected_mode, question
        assert execution.response.response_mode != ResponseMode.SCOPE_REDIRECT, question
        assert execution.tools == (expected_tool,), question
        assert len(static.calls) == 1, question
        assert live.map_calls == live.nearby_calls == live.resolve_calls == 0, question


@_sync_test
async def test_personal_leave_place_now_is_blocked_with_handoff_and_no_execution() -> None:
    for question, place in (
        ("Can I leave Kelowna now?", "Kelowna"),
        ("Can we leave Kamloops right now?", "Kamloops"),
        ("Could I leave Vernon tonight?", "Vernon"),
    ):
        provider = InventingThenRewritingProvider()
        static = RecordingStatic(_background_response())
        static.provider = provider
        live = CountingMapService([])
        execution = await FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(QueryRequest(question=question))

        assert execution.route == QueryRoute.PROHIBITED, question
        assert execution.response.response_mode == ResponseMode.ABSTENTION, question
        assert execution.response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
        assert place.casefold() in (execution.response.answer or "").casefold()
        assert {link.title for link in execution.response.related_links} == {
            "BC Wildfire Service map",
            "EmergencyInfoBC",
        }
        assert execution.tools == ()
        assert len(static.calls) == 0
        assert live.map_calls == live.nearby_calls == live.resolve_calls == 0
        assert provider.turns == 0


def test_ordinary_leave_permission_is_not_misread_as_evacuation_authority() -> None:
    for question in ("Can I leave work now?", "Could we leave school early?"):
        plan = plan_agent_request(QueryRequest(question=question))

        assert plan.route != QueryRoute.PROHIBITED, question
        assert plan.mode == AgentRequestMode.STATIC, question
        assert plan.live_layers == (), question


@_sync_test
async def test_creative_wildfire_requests_are_labelled_background_without_live() -> None:
    for question in (
        "Tell me a story about wildfires.",
        "Tell me a wildfire story.",
        "Write a short poem about a forest fire.",
    ):
        parsed = parse_request_intent(question)
        plan = plan_agent_request(QueryRequest(question=question))
        static = RecordingStatic(_background_response())
        live = CountingMapService([])
        execution = await FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(QueryRequest(question=question))

        assert not parsed.has_live_records, question
        assert plan.mode == AgentRequestMode.STATIC, question
        assert plan.live_layers == (), question
        assert execution.response.response_mode == ResponseMode.BACKGROUND, question
        assert execution.tools == (AgentTool.ANSWER_GENERAL_BACKGROUND,), question
        assert live.map_calls == live.nearby_calls == live.resolve_calls == 0


@pytest.mark.parametrize(
    "question",
    (
        "What do I do if I have received an evacuation alert?",
        "What do we do after receiving an evacuation order?",
        "What should I do if I am under an evacuation alert?",
    ),
)
def test_received_evacuation_notice_is_reviewed_guidance_without_live(
    question: str,
) -> None:
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert plan.route == QueryRoute.RELATED
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.live_layers == ()
    assert [call.name for call in plan.tool_calls] == [AgentTool.SEARCH_REVIEWED_GUIDANCE]


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Anything I should know about near Kelowna?", "Kelowna"),
        ("What is going on near Kelowna?", "Kelowna"),
        ("Is there anything happening near Kamloops?", "Kamloops"),
        ("Anything we should know about around Vernon?", "Vernon"),
    ),
)
def test_natural_near_place_language_is_bounded_live(
    question: str,
    place: str,
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert all(call.as_arguments() == {"place_label": place} for call in plan.tool_calls)


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Which incident near Kelowna is closest?", "Kelowna"),
        ("Which fire near Kamloops is nearest?", "Kamloops"),
        ("Which incident near West Kelowna is the closest?", "West Kelowna"),
    ),
)
def test_closest_near_place_does_not_capture_ranking_tail(
    question: str,
    place: str,
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("What is the nearest fire to downtown Kelowna?", "Kelowna"),
        ("Which wildfire is closest to downtown Kamloops?", "Kamloops"),
        ("What is the closest incident to North Vancouver?", "North Vancouver"),
    ),
)
def test_nearest_fire_to_place_is_exact_location_radius(
    question: str,
    place: str,
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert all(call.as_arguments() == {"place_label": place} for call in plan.tool_calls)
