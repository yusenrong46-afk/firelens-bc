"""V5 public regressions and compositional routing boundary controls."""

from __future__ import annotations

import pytest

from firelens.agent.query_plan import AgentGeography, AgentRequestMode, plan_agent_request
from firelens.answering.intent import plan_query
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.request_grammar import parse_request_facets
from firelens.contracts import QueryRequest, QueryRoute, ResponseMode


@pytest.mark.parametrize(
    ("question", "place", "static_subrequest"),
    (
        (
            "List fires around Trail, also emergency-kit checklist.",
            "Trail",
            "emergency-kit checklist",
        ),
        (
            "Map fires near Salmon Arm with evacuation-alert definitions.",
            "Salmon Arm",
            "evacuation-alert definitions",
        ),
        (
            "BC current fires plus grab-and-go bag contents.",
            None,
            "grab-and-go bag contents",
        ),
    ),
)
def test_v5_public_mixed_guidance_preserves_both_lanes(
    question: str,
    place: str | None,
    static_subrequest: str,
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == (
        AgentGeography.LOCATION_RADIUS if place else AgentGeography.PROVINCE_WIDE
    )
    assert plan.location_label == place
    assert plan.static_subrequest == static_subrequest
    assert [call.name.value for call in plan.tool_calls] == [
        "list_official_fires",
        "search_reviewed_guidance",
    ]


@pytest.mark.parametrize(
    ("question", "static_subrequest"),
    (
        (
            "Show fires near Golden with smoke-readiness tips.",
            "smoke-readiness tips",
        ),
        (
            "List wildfires around Hope and emergency kit contents.",
            "emergency kit contents",
        ),
        (
            "Current B.C. fires also advice for a go-bag.",
            "advice for a go-bag",
        ),
    ),
)
def test_compound_guidance_paraphrases_split_without_location_widening(
    question: str, static_subrequest: str
) -> None:
    facets = parse_request_facets(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert len(facets.clauses) == 2
    assert len(facets.live_clauses) == 1
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.static_subrequest == static_subrequest


def test_v5_public_canada_possessive_live_status_redirects_without_bc_tools() -> None:
    plan = plan_agent_request(QueryRequest(question="What is Canada's wildfire status today?"))

    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.tool_calls == ()
    assert plan.terminal_response is not None
    assert plan.terminal_response.response_mode == ResponseMode.SCOPE_REDIRECT


@pytest.mark.parametrize(
    "question",
    (
        "Compare historic wildfire ecology across Canada.",
        "Explain Canada's wildfire ecology.",
        "Summarize archival fire research throughout Canada.",
    ),
)
def test_static_or_historical_canada_questions_do_not_become_live_redirects(
    question: str,
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.mode == AgentRequestMode.STATIC
    assert plan.route != QueryRoute.LIVE
    assert plan.tool_calls == ()


@pytest.mark.parametrize(
    ("question", "place"),
    (
        (
            "The wildfire map is blank near Nanaimo, so there is no threat, correct?",
            "Nanaimo",
        ),
        ("No markers show around Castlegar; can we assume it is safe?", "Castlegar"),
        ("Search returned zero fires near Invermere. Is that an all-clear?", "Invermere"),
        (
            "The incident view is empty near 100 Mile House; does that prove no danger?",
            "100 Mile House",
        ),
        (
            "No pins are visible around Kitimat, so residents can stay, right?",
            "Kitimat",
        ),
    ),
)
def test_v5_public_empty_operational_view_never_becomes_all_clear(
    question: str, place: str
) -> None:
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert is_empty_map_safety_inference(question)
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert location is not None and location.label == place
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place


@pytest.mark.parametrize(
    "question",
    (
        "The historical fire map is blank for 1950; was the archive complete?",
        "A database search returned zero rows; is there a risk of data loss?",
        "The mock UI map is empty; should the test fixture show a warning?",
        "No chart markers show in my research notebook; is the data safe?",
    ),
)
def test_empty_view_composition_has_historical_data_and_ui_guards(question: str) -> None:
    assert not is_empty_map_safety_inference(question)


@pytest.mark.parametrize(
    "question",
    (
        "How do I add a pin to the wildfire map near Kelowna?",
        "How can I remove a marker from the fire map?",
        "Please place a pin on the incident map.",
    ),
)
def test_map_pin_operations_are_product_help_not_live_record_queries(question: str) -> None:
    facets = parse_request_facets(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert not facets.has_current_live_fire
    assert plan.route != QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.tool_calls == ()
