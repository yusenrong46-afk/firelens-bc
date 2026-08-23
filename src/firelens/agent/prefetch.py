"""Concurrent official-layer and reviewed-guidance prefetch for one Ask."""

from __future__ import annotations

import asyncio
from typing import Any

from firelens.agent.failures import EXPECTED_TOOL_FAILURES, record_expected_failure
from firelens.agent.fallback_brain import (
    heuristic_tool_calls,
    should_prefetch_reviewed_guidance,
)
from firelens.agent.packet import AgentPacket
from firelens.agent.runtime_tools import execute_tool
from firelens.agent.tools import AgentTool
from firelens.answering.intent import live_query_requires_location
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_out_of_province_label,
)
from firelens.contracts import CoarseResolvedLocation, QueryRequest
from firelens.live import LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator


def needs_location(request: QueryRequest) -> bool:
    if request.location is not None:
        return False
    if coarse_location_from_question(request.question) is not None:
        return False
    return live_query_requires_location(request.question)


async def prefetch_selected(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> None:
    selected = request.context.selected_live_result_id
    if not selected:
        return
    if not (
        is_selected_live_request(request)
        or is_unsupported_selected_request(request)
        or is_distance_request(request)
    ):
        return
    try:
        await execute_tool(
            AgentTool.GET_OFFICIAL_FIRE.value,
            {"result_id": selected},
            request=request,
            live_coordinator=live_coordinator,
            static_service=static_service,
            packet=packet,
        )
    except EXPECTED_TOOL_FAILURES as exc:
        record_expected_failure(packet, exc)
        return


async def ensure_official_fetch(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> None:
    if packet.live_results:
        return
    if {"missing_selected_record", "unbound_selected_record"} & set(packet.unknown_topics):
        return
    live_tools = {
        AgentTool.LIST_OFFICIAL_FIRES.value,
        AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
        AgentTool.GET_OFFICIAL_FIRE.value,
    }
    calls = [call for call in heuristic_tool_calls(request) if call["name"] in live_tools]
    if not calls:
        return

    async def _run(call: dict[str, Any]) -> None:
        try:
            await execute_tool(
                call["name"],
                call.get("arguments") or {},
                request=request,
                live_coordinator=live_coordinator,
                static_service=static_service,
                packet=packet,
            )
        except EXPECTED_TOOL_FAILURES as exc:
            record_expected_failure(packet, exc)
            return

    await asyncio.gather(*(_run(call) for call in calls))


async def prefetch_reviewed_guidance(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> None:
    if packet.static_response is not None:
        return
    if not should_prefetch_reviewed_guidance(request.question):
        return
    try:
        await execute_tool(
            AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
            {"query": request.question},
            request=request,
            live_coordinator=live_coordinator,
            static_service=static_service,
            packet=packet,
        )
    except EXPECTED_TOOL_FAILURES as exc:
        record_expected_failure(packet, exc)
        return


async def prefetch_evidence(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> None:
    await prefetch_selected(request, live_coordinator, static_service, packet)
    await asyncio.gather(
        ensure_official_fetch(request, live_coordinator, static_service, packet),
        prefetch_reviewed_guidance(request, live_coordinator, static_service, packet),
    )


async def resolve_place(
    live_coordinator: LiveAnswerCoordinator,
    request: QueryRequest,
    packet: AgentPacket,
) -> None:
    location = request.location or coarse_location_from_question(request.question)
    if location is None or is_out_of_province_label(location.label):
        return
    try:
        latitude, longitude = await live_coordinator.live_service.resolve_location(location)
    except (LiveDataUnavailable, AttributeError, TypeError, ValueError):
        return
    packet.resolved_location = CoarseResolvedLocation(latitude=latitude, longitude=longitude)
