"""Same-day stabilization regressions for the confirmed FireLens-200 failures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from firelens.agent.fallback_brain import planned_static_subrequest
from firelens.agent.live_selection import selected_live_result_id
from firelens.agent.query_plan import AgentRequestMode, plan_agent_request
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    unsupported_live_topics,
)
from firelens.answering.intent_automaton import ClauseIntentKind, parse_request_intent
from firelens.answering.live_analysis import official_analysis_answer
from firelens.answering.live_analysis_distance import is_freshness_question
from firelens.answering.live_evacuation import (
    evacuation_answer,
    is_evacuation_record_question,
)
from firelens.answering.live_handoffs import related_live_links
from firelens.answering.live_request_intent import is_selected_record_followup
from firelens.contracts import (
    ConversationTurn,
    Freshness,
    LiveResult,
    LiveResultKind,
    MapContext,
    QueryRequest,
    QueryRoute,
    ReasonCode,
)
from firelens.guidance_capabilities import resolve_capability


def _record(
    *,
    result_id: str,
    kind: LiveResultKind,
    status: str = "Out of Control",
    name: str | None = None,
    size_hectares: float | None = None,
) -> LiveResult:
    stamp = datetime(2026, 8, 24, tzinfo=UTC)
    return LiveResult(
        result_id=result_id,
        kind=kind,
        source_url=f"https://example.test/{result_id}",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status=status,
        name=name,
        size_hectares=size_hectares,
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


@pytest.mark.parametrize(
    ("question", "static_fragment"),
    (
        (
            "Why is the sky blue, and what wildfires are currently listed in B.C.?",
            "why is the sky blue",
        ),
        (
            "Explain Out of Control and show how many returned incidents have that status.",
            "explain out of control",
        ),
        (
            "Which current incidents are largest, and does largest mean most dangerous?",
            "does largest mean most dangerous",
        ),
        (
            "Why do wildfires create their own weather, and are any Fires of Note returned?",
            "why do wildfires create their own weather",
        ),
        (
            "Show current B.C. incidents and write a wildfire haiku.",
            "write a wildfire haiku",
        ),
    ),
)
def test_mixed_questions_keep_an_explicit_non_live_clause(
    question: str, static_fragment: str
) -> None:
    parsed = parse_request_intent(question)
    static = planned_static_subrequest(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert static is not None
    assert static_fragment in static.casefold()
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.static_subrequest == static
    assert any(
        call.name in {AgentTool.SEARCH_REVIEWED_GUIDANCE, AgentTool.ANSWER_GENERAL_BACKGROUND}
        for call in plan.tool_calls
    )


def test_sky_blue_mixed_uses_the_general_background_lane() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="Why is the sky blue, and what wildfires are currently listed in B.C.?"
        )
    )
    assert plan.tool_calls[-1].name == AgentTool.ANSWER_GENERAL_BACKGROUND
    assert "sky blue" in plan.tool_calls[-1].as_arguments()["query"].casefold()


def test_out_of_control_definition_clause_is_reviewed_guidance() -> None:
    parsed = parse_request_intent(
        "Explain Out of Control and show how many returned incidents have that status."
    )
    kinds = {clause.kind for clause in parsed.clauses}
    assert ClauseIntentKind.REVIEWED_GUIDANCE in kinds
    assert parsed.has_live_records


def test_province_wide_briefing_is_a_live_snapshot() -> None:
    question = "Give me a short province-wide wildfire briefing."
    assert live_layers_for_question(question)
    plan = plan_query(QueryRequest(question=question))
    assert plan.route == QueryRoute.LIVE
    agent = plan_agent_request(QueryRequest(question=question))
    assert agent.mode == AgentRequestMode.LIVE
    assert AgentTool.LIST_OFFICIAL_FIRES in {call.name for call in agent.tool_calls}


def test_evac_count_and_type_questions_own_evacuation_records() -> None:
    count_q = "How many current evacuation records were returned?"
    type_q = "Break down the returned evacuation records by type."
    assert is_evacuation_record_question(count_q)
    assert is_evacuation_record_question(type_q)
    assert LiveResultKind.EVACUATION in live_layers_for_question(count_q)
    assert LiveResultKind.EVACUATION in live_layers_for_question(type_q)
    records = [
        _record(result_id="evacuation:1", kind=LiveResultKind.EVACUATION, status="Order"),
        _record(result_id="evacuation:2", kind=LiveResultKind.EVACUATION, status="Alert"),
        _record(result_id="evacuation:3", kind=LiveResultKind.EVACUATION, status="Alert"),
    ]
    counted = official_analysis_answer(QueryRequest(question=count_q), records)
    assert counted is not None
    assert "3" in counted
    assert "evacuation" in counted.casefold()
    assert "0 incident records" not in counted
    grouped = evacuation_answer(
        QueryRequest(question=type_q),
        records,
        display_name=lambda item: item.name or item.result_id,
        nearby_radius_km=50.0,
    )
    assert "alert" in grouped.casefold()
    assert "order" in grouped.casefold()


def test_source_last_checked_is_a_freshness_live_question() -> None:
    question = "When were the wildfire and evacuation sources last checked?"
    assert is_freshness_question(question)
    layers = live_layers_for_question(question)
    assert LiveResultKind.INCIDENT in layers
    assert LiveResultKind.EVACUATION in layers
    stamp = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    records = [
        _record(result_id="incident:1", kind=LiveResultKind.INCIDENT),
        _record(result_id="evacuation:1", kind=LiveResultKind.EVACUATION, status="Alert"),
    ]
    records[0] = records[0].model_copy(
        update={"source_updated_at": stamp, "retrieved_at": stamp}
    )
    records[1] = records[1].model_copy(
        update={"source_updated_at": stamp, "retrieved_at": stamp}
    )
    answer = official_analysis_answer(QueryRequest(question=question), records)
    assert answer is not None
    assert "source update" in answer.casefold() or "retrieved" in answer.casefold()


@pytest.mark.parametrize(
    ("question", "topic"),
    (
        ("Where is the nearest official evacuation reception centre?", "reception centre"),
        ("Is the power out in the evacuation area?", "utility outage"),
        ("Is this provincial park closed because of wildfire?", "park closure"),
        ("Can I make an insurance claim for wildfire smoke damage?", "insurance boundary"),
        ("What is the live weather at this incident?", "weather or smoke forecast"),
    ),
)
def test_typed_handoffs_do_not_become_live_wildfire_dumps(question: str, topic: str) -> None:
    assert unsupported_live_topics(question) == (topic,)
    plan = plan_query(QueryRequest(question=question))
    assert plan.route == QueryRoute.LIVE
    agent = plan_agent_request(QueryRequest(question=question))
    assert agent.mode == AgentRequestMode.TERMINAL
    assert agent.tool_calls == ()
    links = related_live_links((topic,))
    assert links
    joined = " ".join(str(link.url) for link in links)
    if topic != "reception centre":
        assert "wildfiresituation" not in joined


def test_elderly_parent_leave_is_personalized_safety() -> None:
    request = QueryRequest(question="Should my elderly parent leave before an alert is issued?")
    plan = plan_query(request)
    assert plan.route == QueryRoute.PROHIBITED
    assert plan.boundary_reason == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert (
        live_layers_for_question(request.question) == () or plan.route == QueryRoute.PROHIBITED
    )


def test_packing_exclusion_is_not_a_personalized_evac_decision() -> None:
    plan = plan_query(QueryRequest(question="What should I leave out of an emergency bag?"))
    assert plan.route != QueryRoute.PROHIBITED


def test_flames_near_houses_uses_quote_only_911_capability() -> None:
    capability = resolve_capability("I see flames near houses. Should I call 9-1-1?")
    assert capability is not None
    assert capability.id == "immediate_danger_contact"
    assert capability.coverage_state == "quote_ready"


def test_non_emergency_fire_contact_still_does_not_bind_911() -> None:
    assert resolve_capability("Who should I contact about a fire near Kelowna?") is None


def test_tell_me_more_about_that_one_is_a_selected_record_followup() -> None:
    assert is_selected_record_followup("Tell me more about that one.")
    history = [
        ConversationTurn(role="user", content="What fires are near Kelowna?"),
        ConversationTurn(
            role="assistant",
            content="Quilpituk Creek is the closest official record, 12 km away.",
        ),
        ConversationTurn(role="user", content="Which one is closest?"),
        ConversationTurn(
            role="assistant",
            content="Quilpituk Creek is the closest official record.",
        ),
    ]
    request = QueryRequest(
        question="Tell me more about that one.",
        history=history,
        context=MapContext(),
    )
    plan = plan_agent_request(request)
    assert plan.mode in {AgentRequestMode.LIVE, AgentRequestMode.SELECTED}
    assert plan.live_layers or plan.tool_calls
    live = [
        _record(
            result_id="incident:quilpituk",
            kind=LiveResultKind.INCIDENT,
            name="Quilpituk Creek",
        ),
        _record(
            result_id="incident:other",
            kind=LiveResultKind.INCIDENT,
            name="Other Creek",
        ),
    ]
    assert selected_live_result_id(request, live) == "incident:quilpituk"
