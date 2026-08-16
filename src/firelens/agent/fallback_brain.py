"""Deterministic stand-in used only when the provider has no chat_turn."""

from __future__ import annotations

import re
from typing import Any

from firelens.agent.packet import AgentPacket
from firelens.agent.tools import AgentTool
from firelens.answering.intent import live_layers_for_question, unsupported_live_topics
from firelens.answering.live_analysis import compose_official_answer
from firelens.answering.live_request_intent import is_selected_live_request
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import QueryRequest

_FIRE_TOKEN = re.compile(
    r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?|perimeters?|hectares?|"
    r"closest|nearest|distribution|geography|evacuat)",
    re.IGNORECASE,
)
_GUIDANCE = re.compile(
    r"\b(?:kit|grab-and-go|go bag|firesmart|prepare|preparing|preparedness|"
    r"emergency plan|what belongs|smoke preparedness|pack(?:ing)?)\b",
    re.IGNORECASE,
)
_DEFINITION = re.compile(
    r"\b(?:explain|define|meaning|mean|difference|versus|vs\.?)\b.{0,80}"
    r"\b(?:alerts?|orders?)\b|"
    r"\b(?:alerts?|orders?)\b.{0,80}"
    r"\b(?:mean|meaning|difference|versus|vs\.?)\b",
    re.IGNORECASE,
)
_PREDICTION = re.compile(
    r"\b(?:when will|will it|predict|forecast|reach|spread to|be contained)\b",
    re.IGNORECASE,
)
_EVAC_LIST = re.compile(
    r"\b(?:evacuat|under\b.+\b(?:orders?|alerts?))\b",
    re.IGNORECASE,
)


def heuristic_tool_calls(request: QueryRequest) -> list[dict[str, Any]]:
    """Offline tool choice for tests without a provider chat loop."""

    question = request.question
    calls: list[dict[str, Any]] = []
    location = request.location or coarse_location_from_question(question)
    place = location.label if location is not None else None
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
    elif (
        (_FIRE_TOKEN.search(question) or _EVAC_LIST.search(question))
        and (live_layers_for_question(question) or not unsupported_live_topics(question))
        and not _DEFINITION.search(question)
    ):
        arguments: dict[str, Any] = {}
        if place:
            arguments["place_label"] = place
        if _FIRE_TOKEN.search(question) or not _EVAC_LIST.search(question):
            calls.append({"name": AgentTool.LIST_OFFICIAL_FIRES.value, "arguments": arguments})
        if _EVAC_LIST.search(question):
            calls.append(
                {
                    "name": AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
                    "arguments": arguments,
                }
            )
    if _GUIDANCE.search(question) or _DEFINITION.search(question):
        calls.append(
            {
                "name": AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
                "arguments": {"query": question},
            }
        )
    if not calls and not unsupported_live_topics(question):
        calls.append(
            {
                "name": AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
                "arguments": {"query": question},
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
