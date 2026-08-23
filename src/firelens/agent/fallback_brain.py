"""Deterministic stand-in used only when the provider has no chat_turn."""

from __future__ import annotations

import re
from typing import Any

from firelens.agent.packet import AgentPacket
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    reviewed_guidance_intent,
    unsupported_live_topics,
)
from firelens.answering.live_analysis import compose_official_answer
from firelens.answering.live_request_intent import is_selected_live_request
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import LiveResultKind, QueryRequest

_GUIDANCE = re.compile(
    r"\b(?:kit|grab-and-go|go[- ]bags?|firesmart|prepare|preparing|preparedness|"
    r"precaution|precautions|emergency plan|what belongs|smoke preparedness|"
    r"pack(?:ing)?|what should i (?:take|do|pack))\b",
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


def confident_guidance_intent(question: str) -> bool:
    """Guidance or definition intent strong enough to prefetch reviewed RAG."""

    return bool(
        _GUIDANCE.search(question)
        or _DEFINITION.search(question)
        or (reviewed_guidance_intent(question) and not unsupported_live_topics(question))
    )


def should_prefetch_reviewed_guidance(question: str) -> bool:
    """Skip static prefetch on live-only questions so official records stay first."""

    if _GUIDANCE.search(question) or _DEFINITION.search(question):
        return True
    if live_layers_for_question(question):
        return False
    return confident_guidance_intent(question)


def heuristic_tool_calls(request: QueryRequest) -> list[dict[str, Any]]:
    """Offline tool choice for tests without a provider chat loop."""

    question = request.question
    calls: list[dict[str, Any]] = []
    location = request.location or coarse_location_from_question(question)
    place = location.label if location is not None else None
    layers = live_layers_for_question(question)
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
    if should_prefetch_reviewed_guidance(question):
        calls.append(
            {
                "name": AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
                "arguments": {"query": question},
            }
        )
    if not calls and should_prefetch_reviewed_guidance(question):
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
