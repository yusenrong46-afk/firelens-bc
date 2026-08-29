"""Concurrent official-layer and reviewed-guidance prefetch for one Ask."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from firelens.agent.budget import tool_fingerprint
from firelens.agent.failures import EXPECTED_TOOL_FAILURES, record_expected_failure
from firelens.agent.fallback_brain import (
    heuristic_tool_calls,
    should_prefetch_reviewed_guidance,
)
from firelens.agent.packet import AgentPacket
from firelens.agent.query_plan import AgentQueryPlan
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
    plan: AgentQueryPlan | None = None,
) -> None:
    if plan is not None:
        workers: list[Coroutine[Any, Any, AgentPacket]] = []
        for call in plan.tool_calls:
            arguments = call.as_arguments()
            fingerprint = tool_fingerprint(call.name.value, arguments)
            if fingerprint in packet.tool_fingerprints:
                packet.policy.repeated_tool_dispatch += 1
                continue
            if not packet.policy.consume_tool_call():
                continue
            packet.tool_fingerprints.append(fingerprint)

            async def _run_planned_call(
                name: str = call.name.value,
                call_arguments: dict[str, Any] = arguments,
            ) -> AgentPacket:
                isolated = AgentPacket(query_plan=plan)
                isolated.policy.deadline = packet.policy.deadline
                isolated.policy.cancelled = packet.policy.cancelled
                try:
                    await execute_tool(
                        name,
                        call_arguments,
                        request=request,
                        live_coordinator=live_coordinator,
                        static_service=static_service,
                        packet=isolated,
                    )
                except EXPECTED_TOOL_FAILURES as exc:
                    record_expected_failure(isolated, exc)
                return isolated

            workers.append(_run_planned_call())

        for isolated in await _gather_cancel_on_error(workers):
            _merge_isolated_packet(packet, isolated)
        return
    await prefetch_selected(request, live_coordinator, static_service, packet)
    await ensure_official_fetch(request, live_coordinator, static_service, packet)
    await prefetch_reviewed_guidance(request, live_coordinator, static_service, packet)


async def _gather_cancel_on_error(
    workers: list[Coroutine[Any, Any, AgentPacket]],
) -> list[AgentPacket]:
    """Run independent plan calls together and cancel siblings on interruption."""

    tasks = [asyncio.create_task(worker) for worker in workers]
    if not tasks:
        return []
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _merge_isolated_packet(packet: AgentPacket, isolated: AgentPacket) -> None:
    """Merge concurrent tool results in immutable plan order."""

    seen_results = {item.result_id for item in packet.live_results}
    for result in isolated.live_results:
        if result.result_id not in seen_results:
            packet.live_results.append(result)
            seen_results.add(result.result_id)
    if isolated.static_response is not None:
        packet.static_response = isolated.static_response
    packet.tool_names.extend(isolated.tool_names)
    for topic in isolated.unknown_topics:
        if topic not in packet.unknown_topics:
            packet.unknown_topics.append(topic)
    if isolated.resolved_location is not None:
        packet.resolved_location = isolated.resolved_location
    for link in isolated.related_links:
        if link not in packet.related_links:
            packet.related_links.append(link)
    if isolated.roster_total is not None:
        packet.roster_total = max(packet.roster_total or 0, isolated.roster_total)
    packet.mark_unavailable(isolated.unavailable_layers)
    if isolated.retrieved_at is not None and (
        packet.retrieved_at is None or isolated.retrieved_at > packet.retrieved_at
    ):
        packet.retrieved_at = isolated.retrieved_at
    for _ in range(isolated.policy.retrieval_cycles):
        packet.policy.consume_retrieval_cycle()
    for _ in range(isolated.policy.grounded_generations):
        packet.policy.consume_grounded_generation()
    if isolated.policy.fallback_reason is not None:
        packet.policy.fallback_reason = isolated.policy.fallback_reason
    if isolated.policy.cache_used is not None:
        packet.policy.cache_used = isolated.policy.cache_used
    for stage in isolated.policy.provider_stages:
        packet.policy.record_stage(stage)


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
    except LiveDataUnavailable:
        return
    packet.resolved_location = CoarseResolvedLocation(latitude=latitude, longitude=longitude)
