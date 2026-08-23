"""Tool-loop helpers kept out of the public Ask orchestrator."""

from __future__ import annotations

import json
from typing import Any

from firelens.agent.budget import tool_fingerprint
from firelens.agent.chat import ChatToolCall
from firelens.agent.failures import EXPECTED_TOOL_FAILURES, record_expected_failure
from firelens.agent.packet import AgentPacket
from firelens.agent.rails import execution_allowed
from firelens.agent.runtime_tools import execute_tool
from firelens.agent.tools import AgentTool
from firelens.contracts import QueryRequest, QueryRoute
from firelens.live_answering import LiveAnswerCoordinator


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
    fingerprint = tool_fingerprint(call.name, call.arguments)
    if fingerprint in packet.tool_fingerprints:
        packet.policy.repeated_tool_dispatch += 1
        return json.dumps({"error": "duplicate_tool_dispatch"})
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
