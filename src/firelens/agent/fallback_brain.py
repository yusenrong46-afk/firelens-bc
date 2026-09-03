"""Deterministic stand-in used only when the provider has no chat_turn."""

from __future__ import annotations

import re
from typing import Any

from firelens.agent.packet import AgentPacket
from firelens.agent.tools import AgentTool
from firelens.answering.clause_boundaries import is_boundary_clause
from firelens.answering.intent import (
    conversation_planning_question,
    live_layers_for_question,
    reviewed_guidance_intent,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_refresh import is_live_refresh_request
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_analysis import compose_official_answer
from firelens.answering.live_request_intent import is_selected_live_request
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.unsupported_live import unsupported_live_topics
from firelens.contracts import LiveResultKind, QueryRequest

_PREDICTION = re.compile(
    r"\b(?:when will|will it|predict|forecast|reach|spread to|be contained)\b",
    re.IGNORECASE,
)


def confident_guidance_intent(question: str) -> bool:
    """Guidance or definition intent strong enough to prefetch reviewed RAG."""

    return reviewed_guidance_intent(question)


def should_prefetch_reviewed_guidance(question: str) -> bool:
    """Skip static prefetch on live-only questions so official records stay first."""

    parsed = parse_request_intent(question)
    if live_layers_for_question(question) and not parsed.has_reviewed_guidance:
        return False
    return reviewed_guidance_intent(question) or parsed.has_prefetchable_guidance


def planned_static_subrequest(question: str) -> str | None:
    """Preserve the exact non-live clause for static or mixed execution."""

    if is_empty_map_safety_inference(question):
        return None
    parsed = parse_request_intent(question)
    layers = live_layers_for_question(question)
    if layers or parsed.has_live_records:
        if is_live_refresh_request(question) and not parsed.has_reviewed_guidance:
            return None
        static_text = parsed.reviewed_guidance_text or parsed.static_subrequest_text
        if static_text is None:
            return None
        if len(parsed.clauses) == 1 and not parsed.has_reviewed_guidance:
            return None
        # A declined decision, an unavailable comparison or a handoff topic is
        # answered by its own section, never by the model.
        if is_boundary_clause(static_text):
            return None
        return static_text
    if unsupported_live_topics(question):
        return parsed.reviewed_guidance_text
    if should_prefetch_reviewed_guidance(question):
        return question
    return None


def planned_static_tool(question: str) -> AgentTool | None:
    """Choose reviewed retrieval or labelled general background for a static clause."""

    static_query = planned_static_subrequest(question)
    if static_query is None:
        return None
    parsed_static = parse_request_intent(static_query)
    parsed_full = parse_request_intent(question)
    if (
        parsed_static.has_reviewed_guidance
        or reviewed_guidance_intent(static_query)
        or parsed_full.has_reviewed_guidance
        or reviewed_guidance_intent(question)
        or parsed_full.has_prefetchable_guidance
    ):
        return AgentTool.SEARCH_REVIEWED_GUIDANCE
    return AgentTool.ANSWER_GENERAL_BACKGROUND


def heuristic_tool_calls(request: QueryRequest) -> list[dict[str, Any]]:
    """Offline tool choice for tests without a provider chat loop."""

    question = conversation_planning_question(request)
    calls: list[dict[str, Any]] = []
    location = request.location or coarse_location_from_question(question)
    place = location.label if location is not None else None
    layers = live_layers_for_question(question)
    static_query = planned_static_subrequest(question)
    if request.context.selected_live_result_id and (
        _PREDICTION.search(question)
        or is_selected_live_request(request)
        or re.search(r"\b(?:this|that|selected|it|its|source|size|status)\b", question, re.I)
    ):
        calls.append(
            {
                "name": AgentTool.GET_OFFICIAL_FIRE.value,
                "arguments": {"result_id": request.context.selected_live_result_id},
            }
        )
    elif layers:
        arguments: dict[str, Any] = {}
        if place:
            arguments["place_label"] = place
        if LiveResultKind.INCIDENT in layers or LiveResultKind.PERIMETER in layers:
            calls.append({"name": AgentTool.LIST_OFFICIAL_FIRES.value, "arguments": arguments})
        if LiveResultKind.EVACUATION in layers:
            calls.append(
                {
                    "name": AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
                    "arguments": arguments,
                }
            )
    if static_query is not None:
        static_tool = planned_static_tool(question) or AgentTool.SEARCH_REVIEWED_GUIDANCE
        calls.append(
            {
                "name": static_tool.value,
                "arguments": {"query": static_query},
            }
        )
    return calls


def fallback_write(request: QueryRequest, packet: AgentPacket) -> str:
    """Analyze official records without a model. Used by FakeProvider and tests."""

    if _PREDICTION.search(request.question) and request.context.selected_live_result_id:
        return (
            "The selected official record does not contain the fields needed to "
            "answer that causal or predictive question. Open the selected official "
            "record for the fields its publishing authority provides."
        )
    static_answer = (
        packet.static_response.answer
        if packet.static_response is not None and packet.static_response.answer
        else None
    )
    return compose_official_answer(
        request,
        packet.live_results,
        roster_total=packet.roster_total,
        static_answer=static_answer,
    )
