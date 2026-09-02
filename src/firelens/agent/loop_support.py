"""Tool-loop helpers kept out of the public Ask orchestrator."""

from __future__ import annotations

import json
from typing import Any

from firelens.agent.chat import ChatToolCall
from firelens.agent.failures import EXPECTED_TOOL_FAILURES, record_expected_failure
from firelens.agent.packet import AgentPacket
from firelens.agent.query_plan import AgentQueryPlan, AgentRequestMode
from firelens.agent.rails import execution_allowed
from firelens.agent.runtime_tools import execute_tool
from firelens.agent.tools import AgentTool
from firelens.answering.live_distance import location_request
from firelens.contracts import AskResponse, QueryRequest, QueryRoute
from firelens.live_answering import LiveAnswerCoordinator


def skip_owned_model_write(query_plan: AgentQueryPlan, packet: AgentPacket) -> bool:
    """Skip Luna when official records already own the answer."""

    if query_plan.mode in {AgentRequestMode.LIVE, AgentRequestMode.SELECTED}:
        packet.policy.route = "ready_live"
        return True
    if query_plan.mode == AgentRequestMode.MIXED:
        # Mixed answers are application-composed: successful clauses stay
        # labelled, and an unestablished clause is named instead of dropped.
        if packet.live_results:
            packet.policy.route = "ready_mixed"
            return True
        return False
    skip = bool(packet.live_results and packet.static_response is None) or (
        not query_plan.tool_calls and packet.static_response is None
    )
    if skip and packet.live_results and packet.static_response is None:
        packet.policy.route = "ready_live"
    elif skip and not packet.live_results:
        packet.policy.route = packet.policy.route or "deterministic_redirect"
    return skip


def accepted_reviewed_publication(packet: AgentPacket) -> bool:
    """Return whether the packet can render reviewed guidance without model prose."""

    static = packet.static_response
    return bool(
        static is not None
        and static.response_mode.value in {"grounded", "partial"}
        and static.claims
        and static.evidence
        and static.validation is not None
        and static.validation.accepted
    )


def missing_location_result(
    request: QueryRequest, packet: AgentPacket
) -> tuple[AskResponse, QueryRoute, tuple[AgentTool, ...], AgentPacket]:
    packet.policy.route = "missing_location"
    tool = (
        AgentTool.GET_OFFICIAL_FIRE
        if request.context.selected_live_result_id
        else AgentTool.LIST_OFFICIAL_FIRES
    )
    return location_request(request), QueryRoute.LIVE, (tool,), packet


def pure_static_ready(packet: AgentPacket) -> bool:
    static = packet.static_response
    return (
        static is not None
        and not packet.live_results
        and static.response_mode.value in {"grounded", "partial"}
        and static.validation is not None
        and static.validation.accepted
    )


async def safe_execute(
    call: ChatToolCall,
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> str:
    if not execution_allowed(call.name):
        return json.dumps({"error": "tool_not_allowlisted"})
    try:
        return await execute_tool(
            call.name,
            call.arguments,
            request=request,
            live_coordinator=live_coordinator,
            static_service=static_service,
            packet=packet,
        )
    except EXPECTED_TOOL_FAILURES as exc:
        return json.dumps(record_expected_failure(packet, exc))


def assistant_tool_request(calls: tuple[ChatToolCall, ...]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in calls
        ],
    }


def tools_used(packet: AgentPacket) -> tuple[AgentTool, ...]:
    tools: list[AgentTool] = []
    for name in packet.tool_names:
        try:
            tools.append(AgentTool(name))
        except ValueError:
            continue
    return tuple(dict.fromkeys(tools))


def route_for(packet: AgentPacket) -> QueryRoute:
    if packet.live_results:
        return QueryRoute.LIVE
    return QueryRoute.RELATED


def assign_route(packet: AgentPacket) -> None:
    if packet.policy.route:
        return
    if packet.live_results and packet.static_response is not None:
        packet.policy.route = "ready_mixed"
    elif packet.live_results:
        packet.policy.route = "ready_live"
    elif packet.static_response is not None:
        packet.policy.route = "pure_static_accepted"
    else:
        packet.policy.route = "deterministic_redirect"
