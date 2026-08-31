"""Behavioral proof for the immutable application-owned agent plan."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from firelens.agent.query_plan import (
    AgentGeography,
    AgentRequestMode,
    AgentScopeResult,
    build_agent_query_plan,
    plan_agent_request,
)
from firelens.agent.tools import AgentTool
from firelens.contracts import (
    ConversationTurn,
    LiveResultKind,
    LocationInput,
    MapContext,
    QueryRequest,
    QueryRoute,
    ResponseMode,
)
from firelens.live import LiveDataErrorKind, LiveDataUnavailable


class Resolver:
    def __init__(self, *, found: bool = True) -> None:
        self.found = found
        self.labels: list[str | None] = []

    async def resolve_location(self, location: Any) -> tuple[float, float]:
        self.labels.append(getattr(location, "label", None))
        if not self.found:
            raise LiveDataUnavailable(
                "not found",
                kind=LiveDataErrorKind.NOT_FOUND,
            )
        return 49.89, -119.49


class Coordinator:
    def __init__(self, resolver: Resolver) -> None:
        self.live_service = resolver


def _plan(question: str, *, found: bool = True, selected: str | None = None) -> Any:
    context = MapContext(selected_live_result_id=selected) if selected else MapContext()
    return asyncio.run(
        build_agent_query_plan(
            QueryRequest(question=question, context=context),
            Coordinator(Resolver(found=found)),  # type: ignore[arg-type]
        )
    )


@pytest.mark.parametrize(
    "question",
    (
        "Are there fires near Kelowna today, and what belongs in an emergency kit?",
        "Kelowna: what is burning today, and what belongs in an emergency kit?",
        "What's burning near Kelowna now, plus what belongs in an emergency kit?",
    ),
)
def test_mixed_plan_preserves_exact_static_clause_and_order(question: str) -> None:
    plan = _plan(question)
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kelowna"
    assert plan.live_layers == (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    assert plan.static_subrequest == "what belongs in an emergency kit"
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Kelowna"}
    assert plan.tool_calls[1].as_arguments() == {"query": "what belongs in an emergency kit"}


@pytest.mark.parametrize(
    ("question", "place", "static_subrequest"),
    (
        (
            "What is the closest fire to Penticton and what should I have ready?",
            "Penticton",
            "what should I have ready",
        ),
        (
            "Are there fires near Kamloops and how should I prepare for poor air quality?",
            "Kamloops",
            "how should I prepare for poor air quality",
        ),
        (
            "Give me a short summary of current Kelowna fires plus official preparedness advice.",
            "Kelowna",
            "official preparedness advice",
        ),
    ),
)
def test_product_journey_mixed_requests_preserve_both_lanes(
    question: str, place: str, static_subrequest: str
) -> None:
    plan = _plan(question)

    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.static_subrequest == static_subrequest
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Are there any current fires on Vancouver Island?", "Vancouver Island"),
        ("When was the wildfire information for Kelowna last updated?", "Kelowna"),
        ("List the closest wildfires to Kelowna from nearest to farthest.", "Kelowna"),
        ("Give me three facts about the closest wildfire to Kelowna.", "Kelowna"),
    ),
)
def test_product_journey_live_requests_keep_explicit_geography(
    question: str, place: str
) -> None:
    plan = _plan(question)

    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.tool_calls[0].as_arguments() == {"place_label": place}


def test_perimeter_existential_requests_only_the_perimeter_layer() -> None:
    plan = _plan("Is there a fire perimeter near Kelowna?")

    assert plan.mode == AgentRequestMode.LIVE
    assert plan.live_layers == (LiveResultKind.PERIMETER,)
    assert plan.location_label == "Kelowna"


def test_nonliteral_wildfire_metaphor_never_fetches_live_records() -> None:
    plan = _plan("My workload is a wildfire. Is it out of control?")

    assert plan.route == QueryRoute.TANGENT
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.live_layers == ()
    assert plan.tool_calls == ()


def test_ambiguous_nearby_family_request_uses_stated_place_without_safety_inference() -> None:
    plan = _plan("My parents are in Penticton. Is anything nearby?")

    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Penticton"
    assert plan.static_subrequest is None


def test_implicit_nearby_mixed_request_preserves_reviewed_smoke_half() -> None:
    plan = _plan(
        "What's happening around Kamloops, and how should I prepare for poor air quality?"
    )

    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kamloops"
    assert plan.static_subrequest == "how should I prepare for poor air quality"
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.LIST_OFFICIAL_EVACUATIONS,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]


@pytest.mark.parametrize(
    ("question", "place", "static_subrequest"),
    (
        (
            "Show current fires near Kelowna and emergency kit advice.",
            "Kelowna",
            "emergency kit advice",
        ),
        (
            "Kelowna fires today and grab-and-go bag contents.",
            "Kelowna",
            "grab-and-go bag contents",
        ),
        (
            "Map fires around Vernon with evacuation alert definitions.",
            "Vernon",
            "evacuation alert definitions",
        ),
    ),
)
def test_terse_mixed_plan_does_not_drop_guidance_or_widen_live_scope(
    question: str, place: str, static_subrequest: str
) -> None:
    plan = _plan(question)

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.live_layers == (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    assert plan.static_subrequest == static_subrequest
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]
    assert plan.tool_calls[0].as_arguments() == {"place_label": place}
    assert plan.tool_calls[1].as_arguments() == {"query": static_subrequest}


def test_province_plan_has_one_explicit_scope_and_no_default_static_call() -> None:
    plan = _plan("What is burning in BC today?")
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.static_subrequest is None
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].as_arguments() == {}


@pytest.mark.parametrize(
    "question",
    (
        "Give me a distribution of the current wildfires in BC by region and status.",
        "Give current wildfires in B.C. by region/status",
        "Give current wildfires in British Columbia by fire centre and status.",
    ),
)
def test_province_analysis_axes_are_not_misread_as_a_place(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.location_label is None
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].as_arguments() == {}


def test_explicit_province_analysis_overrides_stale_retained_location_before_resolution() -> (
    None
):
    resolver = Resolver(found=False)
    request = QueryRequest(
        question="Give me a distribution of the current wildfires in BC by region and status.",
        location=LocationInput(label="Kelowna"),
    )

    plan = asyncio.run(build_agent_query_plan(request, Coordinator(resolver)))  # type: ignore[arg-type]

    assert resolver.labels == []
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.location_label is None
    assert plan.tool_calls[0].as_arguments() == {}


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Give current wildfires near Kelowna by region and status", "Kelowna"),
        ("Give current wildfires in Okanagan by fire centre and status", "Okanagan"),
    ),
)
def test_regional_analysis_retains_a_real_location(question: str, place: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.tool_calls[0].as_arguments() == {"place_label": place}


def test_explicit_question_location_overrides_stale_retained_location_for_resolution() -> None:
    resolver = Resolver()
    request = QueryRequest(
        question="Give current wildfires near Vernon by region and status.",
        location=LocationInput(label="Kelowna"),
    )

    plan = asyncio.run(build_agent_query_plan(request, Coordinator(resolver)))  # type: ignore[arg-type]

    assert resolver.labels == ["Vernon"]
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Vernon"
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Vernon"}


def test_selected_record_plan_owns_exact_record_identifier() -> None:
    plan = _plan(
        "What is the status of this fire?",
        selected="incident:7",
    )
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.SELECTED
    assert plan.geography == AgentGeography.SELECTED_RECORD
    assert plan.tool_calls[0].as_arguments() == {"result_id": "incident:7"}
    assert not plan.authorizes(
        AgentTool.GET_OFFICIAL_FIRE.value,
        {"result_id": "incident:other"},
    )


@pytest.mark.parametrize(
    "question",
    ("Is it still burning?", "What official details are on it?"),
)
def test_selected_record_binds_narrow_supported_deictic_followups(question: str) -> None:
    plan = plan_agent_request(
        QueryRequest(
            question=question,
            context=MapContext(selected_live_result_id="incident:7"),
        )
    )

    assert plan.mode == AgentRequestMode.SELECTED
    assert plan.geography == AgentGeography.SELECTED_RECORD
    assert plan.tool_calls[0].name == AgentTool.GET_OFFICIAL_FIRE
    assert plan.tool_calls[0].as_arguments() == {"result_id": "incident:7"}


@pytest.mark.parametrize("question", ("Why do people leave it too late?", "What is it?"))
def test_selected_record_does_not_overbind_general_or_ambiguous_pronouns(question: str) -> None:
    plan = plan_agent_request(
        QueryRequest(
            question=question,
            context=MapContext(selected_live_result_id="incident:7"),
        )
    )

    assert plan.mode != AgentRequestMode.SELECTED
    assert all(call.name != AgentTool.GET_OFFICIAL_FIRE for call in plan.tool_calls)


@pytest.mark.parametrize(
    "question",
    (
        "Tell me about Bald Range Fire",
        "Which fire is closest to Kelowna?",
        "What about the second fire?",
    ),
)
def test_existing_selection_binds_named_closest_and_ordinal_requests(question: str) -> None:
    plan = _plan(question, selected="incident:7")

    assert plan.mode == AgentRequestMode.SELECTED
    assert plan.geography == AgentGeography.SELECTED_RECORD
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].name == AgentTool.GET_OFFICIAL_FIRE


def test_visible_roster_ordinal_binds_exact_stable_record_id() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="Tell me more about the second one.",
            context=MapContext(
                visible_live_result_ids=["incident:1", "incident:2", "incident:3"]
            ),
        )
    )

    assert plan.mode == AgentRequestMode.SELECTED
    assert plan.geography == AgentGeography.SELECTED_RECORD
    assert plan.tool_calls[0].as_arguments() == {"result_id": "incident:2"}


@pytest.mark.parametrize(
    "question",
    (
        "Compare the closest active fires to Kelowna and Kamloops.",
        "Which city currently has the closer active fire, Kelowna or Vernon?",
    ),
)
def test_multi_place_distance_comparison_fails_truthfully_before_fetch(question: str) -> None:
    plan = _plan(question)

    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.REQUIRES_INPUT
    assert plan.tool_calls == ()
    assert plan.terminal_response is not None
    assert "cannot yet compare" in (plan.terminal_response.answer or "")


def test_multi_place_comparison_continues_with_the_community_the_user_chose() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="Compare the closest active fires to Kelowna and Kamloops.",
            location=LocationInput(label="Kelowna"),
        )
    )

    assert plan.mode != AgentRequestMode.TERMINAL
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kelowna"
    assert plan.tool_calls
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Kelowna"}


@pytest.mark.parametrize(
    "question",
    ("How large is the fire?", "What is the status of this fire?"),
)
def test_singular_size_or_status_requires_an_explicit_selection(question: str) -> None:
    plan = _plan(question)

    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.tool_calls == ()
    assert plan.terminal_response is not None
    assert "Select a mapped official record" in (plan.terminal_response.answer or "")


def test_explicit_unresolved_region_is_resumable_and_fetch_free() -> None:
    plan = _plan("What's burning in Okanagan today?", found=False)
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.REQUIRES_INPUT
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.tool_calls == ()
    assert plan.terminal_response is not None
    assert plan.terminal_response.response_mode == ResponseMode.REQUIRES_INPUT
    assert plan.terminal_response.required_input is not None
    assert (
        plan.terminal_response.required_input.continuation_question
        == "What's burning in Okanagan today?"
    )


def test_resolver_programming_error_is_not_relabelled_as_an_unresolved_place() -> None:
    class BrokenResolver:
        async def resolve_location(self, _location: object) -> tuple[float, float]:
            raise TypeError("resolver contract drift")

    with pytest.raises(TypeError, match="resolver contract drift"):
        asyncio.run(
            build_agent_query_plan(
                QueryRequest(question="What's burning in Kelowna today?"),
                Coordinator(BrokenResolver()),  # type: ignore[arg-type]
            )
        )


@pytest.mark.parametrize(
    "question",
    (
        "Are there wildfires near Calgary right now?",
        "Are there wildfires across Canada right now?",
        "Show current fires coast to coast.",
        "Show current fires across the country.",
        "Show current fires in all ten provinces.",
    ),
)
def test_out_of_scope_live_request_is_terminal_without_resolution(question: str) -> None:
    resolver = Resolver()
    plan = asyncio.run(
        build_agent_query_plan(
            QueryRequest(question=question),
            Coordinator(resolver),  # type: ignore[arg-type]
        )
    )
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.SCOPE_REDIRECT
    assert plan.tool_calls == ()
    assert resolver.labels == []
    assert plan.terminal_response is not None
    assert plan.terminal_response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert len(plan.terminal_response.trace_id) == 32


@pytest.mark.parametrize(
    "question",
    (
        "Give me the current wildfire picture from Atlantic to Pacific.",
        "Show today's wildfires throughout the nation.",
    ),
)
def test_national_scope_variants_never_substitute_bc_records(question: str) -> None:
    resolver = Resolver()
    plan = asyncio.run(
        build_agent_query_plan(
            QueryRequest(question=question),
            Coordinator(resolver),  # type: ignore[arg-type]
        )
    )

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.SCOPE_REDIRECT
    assert plan.tool_calls == ()
    assert resolver.labels == []
    assert plan.terminal_response is not None
    assert plan.terminal_response.response_mode == ResponseMode.SCOPE_REDIRECT


@pytest.mark.parametrize(
    ("question", "geography", "place", "static_subrequest"),
    (
        (
            "Current fires across British Columbia, plus smoke readiness guidance.",
            AgentGeography.PROVINCE_WIDE,
            None,
            "smoke readiness guidance",
        ),
        (
            "Near Prince George, current fires plus wildfire smoke health guidance "
            "plus emergency kit advice.",
            AgentGeography.LOCATION_RADIUS,
            "Prince George",
            "wildfire smoke health guidance and emergency kit advice",
        ),
    ),
)
def test_mixed_smoke_and_kit_requests_preserve_both_execution_lanes(
    question: str,
    geography: AgentGeography,
    place: str | None,
    static_subrequest: str,
) -> None:
    plan = _plan(question)

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == geography
    assert plan.location_label == place
    assert plan.live_layers == (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    assert plan.static_subrequest == static_subrequest
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]
    assert plan.tool_calls[0].as_arguments() == (
        {"place_label": place} if place is not None else {}
    )
    assert plan.tool_calls[1].as_arguments() == {"query": static_subrequest}


@pytest.mark.parametrize(
    "question",
    ("Show current highway closures near Kelowna.",),
)
def test_unsupported_live_route_has_an_explicit_terminal_scope(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.scope_result == AgentScopeResult.SCOPE_REDIRECT
    assert plan.tool_calls == ()


def test_unsupported_mixed_request_preserves_its_supported_static_clause() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="Are roads closed to Vernon and what belongs in an emergency kit?"
        )
    )
    assert plan.route == QueryRoute.RELATED
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.scope_result == AgentScopeResult.SCOPE_REDIRECT
    assert plan.static_subrequest == "what belongs in an emergency kit"
    assert plan.tool_calls[0].as_arguments() == {"query": "what belongs in an emergency kit"}


def test_historical_or_future_fire_question_does_not_gain_live_authority() -> None:
    plan = plan_agent_request(
        QueryRequest(question="Which fires will reach Kelowna next week?")
    )
    assert plan.route != QueryRoute.LIVE
    assert plan.live_layers == ()
    assert plan.tool_calls == ()


def test_plan_has_a_stable_json_projection_for_offline_evidence() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="Are there fires near Kelowna today, and what belongs in an emergency kit?"
        )
    )
    dumped = plan.model_dump(mode="json")
    assert dumped["scope_result"] == "ready"
    assert dumped["geography"] == "location_radius"
    assert dumped["tool_calls"] == [
        {
            "name": "list_official_fires",
            "arguments": {"place_label": "Kelowna"},
        },
        {
            "name": "search_reviewed_guidance",
            "arguments": {"query": "what belongs in an emergency kit"},
        },
    ]


@pytest.mark.parametrize(
    "question",
    (
        "What did wildfires burn last year?",
        "Tell me a story about dragons.",
        "Kamloops plus explain how wildfire ecology works.",
    ),
)
def test_non_current_or_non_live_questions_do_not_gain_live_tools(question: str) -> None:
    plan = _plan(question)
    assert plan.live_layers == ()
    assert all(
        call.name
        not in {
            AgentTool.LIST_OFFICIAL_FIRES,
            AgentTool.LIST_OFFICIAL_EVACUATIONS,
            AgentTool.GET_OFFICIAL_FIRE,
        }
        for call in plan.tool_calls
    )


def test_closest_one_follow_up_keeps_the_prior_named_place() -> None:
    history = [
        ConversationTurn(role="user", content="What official fires are near Kelowna?"),
        ConversationTurn(role="assistant", content="Current official information: Bald Range."),
    ]
    plan = plan_agent_request(
        QueryRequest(question="How far is the closest one?", history=history)
    )
    assert plan.location_label == "Kelowna"
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Kelowna"}


def test_second_fire_after_closest_still_keeps_the_named_place() -> None:
    history = [
        ConversationTurn(role="user", content="What official fires are near Kelowna?"),
        ConversationTurn(role="assistant", content="Current official information: Bald Range."),
        ConversationTurn(role="user", content="How far is the closest one?"),
        ConversationTurn(role="assistant", content="K51402 is the closest official record."),
    ]
    plan = plan_agent_request(
        QueryRequest(question="What about the second fire?", history=history)
    )
    assert plan.location_label == "Kelowna"
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Kelowna"}


def test_provider_arguments_cannot_widen_a_location_bound_plan() -> None:
    plan = _plan("Are there active wildfires near Kelowna currently?")
    assert plan.authorizes(
        AgentTool.LIST_OFFICIAL_FIRES.value,
        {"place_label": "Kelowna"},
    )
    assert not plan.authorizes(
        AgentTool.LIST_OFFICIAL_FIRES.value,
        {"place_label": "British Columbia"},
    )
    assert not plan.authorizes(
        AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
        {"place_label": "Kelowna"},
    )
