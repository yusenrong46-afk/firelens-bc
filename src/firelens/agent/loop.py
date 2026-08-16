"""Bounded Luna tool loop: prefetch, single write when facts are ready, veto, rewrite."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from firelens.agent.chat import ChatToolCall, ChatTurn
from firelens.agent.compose import (
    compose_response,
    handoff_answer,
    no_substitute_response,
    quoted_guidance_response,
    safety_response,
)
from firelens.agent.fallback_brain import (
    confident_guidance_intent,
    fallback_write,
    heuristic_tool_calls,
)
from firelens.agent.packet import AgentPacket
from firelens.agent.prompts import OPENROUTER_TOOLS, SYSTEM_PROMPT
from firelens.agent.rails import execution_allowed, output_rail_errors
from firelens.agent.runtime_tools import execute_tool
from firelens.agent.tools import AgentTool
from firelens.answering.intent import live_query_requires_location, unsupported_live_topics
from firelens.answering.live_analysis import (
    official_analysis_answer,
    replace_ungrounded_live_hedge,
    strip_precise_coordinates,
)
from firelens.answering.live_distance import distance_answer, location_request
from firelens.answering.live_handoffs import related_live_links
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unbound_distance_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_national_scope_question,
    is_out_of_province_label,
)
from firelens.contracts import (
    AskResponse,
    CoarseResolvedLocation,
    QueryRequest,
    QueryRoute,
)
from firelens.errors import ProviderError
from firelens.live import LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator

MAX_TOOL_ROUNDS = 2


class ChatProvider(Protocol):
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn: ...


class StaticAnswerService(Protocol):
    async def ask(
        self,
        request: QueryRequest,
        *,
        allow_live: bool = True,
        prefer_reviewed_quotes: bool = False,
    ) -> AskResponse: ...


async def run_agent_loop(
    request: QueryRequest,
    *,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    provider: ChatProvider | None,
) -> tuple[AskResponse, QueryRoute, tuple[AgentTool, ...]]:
    """Run one Ask through Luna (or the offline stand-in) and rails."""

    packet = AgentPacket()
    unsupported = unsupported_live_topics(request.question)
    packet.related_links = related_live_links(unsupported)
    packet.unknown_topics.extend(unsupported)
    if is_national_scope_question(request.question):
        packet.unknown_topics.append("out_of_province_place")
    if is_unsupported_selected_request(request):
        packet.unknown_topics.append("prediction")
    if _needs_location(request):
        tool = (
            AgentTool.GET_OFFICIAL_FIRE
            if request.context.selected_live_result_id
            else AgentTool.LIST_OFFICIAL_FIRES
        )
        return location_request(request), QueryRoute.LIVE, (tool,)
    if is_unbound_distance_request(request):
        return (
            no_substitute_response(request),
            QueryRoute.LIVE,
            (AgentTool.GET_OFFICIAL_FIRE,),
        )
    await _prefetch_selected(request, live_coordinator, static_service, packet)
    # Confident heuristics prefetch official layers and reviewed guidance
    # concurrently so a ready packet needs exactly one provider write call.
    await asyncio.gather(
        _ensure_official_fetch(request, live_coordinator, static_service, packet),
        _prefetch_reviewed_guidance(request, live_coordinator, static_service, packet),
    )
    if provider is None:
        answer = await _offline_loop(request, live_coordinator, static_service, packet)
    else:
        try:
            answer = await _provider_loop(
                request, live_coordinator, static_service, provider, packet
            )
        except ProviderError:
            answer = await _offline_loop(request, live_coordinator, static_service, packet)
    if packet.live_results and not answer.strip():
        answer = fallback_write(request, packet)
    if is_distance_request(request) and packet.live_results:
        composed = distance_answer(request, packet.live_results)
        if composed:
            answer = composed
    else:
        analysis = official_analysis_answer(
            request,
            packet.live_results,
            roster_total=packet.roster_total,
            static_answer=(
                packet.static_response.answer if packet.static_response is not None else None
            ),
        )
        if analysis:
            answer = analysis
    if packet.live_results:
        answer = replace_ungrounded_live_hedge(answer, fallback_write(request, packet))
    answer = strip_precise_coordinates(answer)
    if not packet.live_results and packet.related_links and packet.resolved_location is None:
        await _resolve_place(live_coordinator, request, packet)
    errors = output_rail_errors(answer, packet)
    if errors and provider is not None:
        try:
            answer = await _rewrite(provider, request, packet, answer, errors)
        except ProviderError:
            answer = fallback_write(request, packet)
        errors = output_rail_errors(answer, packet)
    if errors:
        if "safety_or_medical_language" in errors:
            quoted = quoted_guidance_response(request, packet)
            if quoted is not None:
                return quoted, _route_for(packet), _tools_used(packet)
            return (
                safety_response(request),
                QueryRoute.PROHIBITED,
                _tools_used(packet),
            )
        answer = fallback_write(request, packet)
        if output_rail_errors(answer, packet):
            answer = "The official records available for this request do not report that fact."
    return compose_response(request, packet, answer), _route_for(packet), _tools_used(packet)


async def _offline_loop(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    packet: AgentPacket,
) -> str:
    calls = heuristic_tool_calls(request)
    if not calls:
        if packet.related_links:
            return handoff_answer(packet)
        return (
            "That question is outside FireLens fire and preparedness sources. "
            "Ask about official wildfire records or reviewed guidance."
        )
    for call in calls:
        if not execution_allowed(call["name"]):
            continue
        if call["name"] in packet.tool_names:
            continue
        if (
            call["name"] == AgentTool.SEARCH_REVIEWED_GUIDANCE.value
            and packet.static_response is not None
        ):
            continue
        try:
            await execute_tool(
                call["name"],
                call.get("arguments") or {},
                request=request,
                live_coordinator=live_coordinator,
                static_service=static_service,
                packet=packet,
            )
        except Exception:
            continue
    return fallback_write(request, packet)


async def _provider_loop(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    provider: ChatProvider,
    packet: AgentPacket,
) -> str:
    packet_ready = bool(packet.live_results or packet.static_response is not None)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": request.question,
                    "history": [turn.model_dump(mode="json") for turn in request.history],
                    "selected_live_result_id": request.context.selected_live_result_id,
                    "place_label": request.location.label if request.location else None,
                    **(
                        {
                            "official_packet": packet.facts_for_model(),
                            "instruction": (
                                "Official records are already fetched. Write from "
                                "official_packet. Do not pass BC or British Columbia "
                                "as place_label. Use history only to resolve this "
                                "turn's referents."
                            ),
                        }
                        if packet_ready
                        else {}
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]
    if packet_ready:
        # Fast path: this turn's facts are already fetched and verified, so
        # Luna gets exactly one write call and no tools to re-dispatch.
        turn = await provider.chat_turn(messages, tools=None)
        return (turn.content or "").strip() or fallback_write(request, packet)
    for _ in range(MAX_TOOL_ROUNDS):
        turn = await provider.chat_turn(messages, tools=OPENROUTER_TOOLS)
        if not turn.tool_calls:
            return (turn.content or "").strip() or fallback_write(request, packet)
        messages.append(_assistant_tool_request(turn.tool_calls))
        for call in turn.tool_calls:
            content = await _safe_execute(
                call, request, live_coordinator, static_service, packet
            )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    final = await provider.chat_turn(messages, tools=None)
    return (final.content or "").strip() or fallback_write(request, packet)


async def _rewrite(
    provider: ChatProvider,
    request: QueryRequest,
    packet: AgentPacket,
    previous: str,
    errors: list[str],
) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": request.question,
                    "history": [turn.model_dump(mode="json") for turn in request.history],
                    "official_packet": packet.facts_for_model(),
                    "previous_answer_rejected_for": errors,
                    "instruction": (
                        "Rewrite using only official_packet. Remove safety advice, "
                        "unfetched fires, and civic addresses. Use history only to "
                        "resolve this turn's referents."
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]
    turn = await provider.chat_turn(messages, tools=None)
    return (turn.content or "").strip() or previous


async def _safe_execute(
    call: ChatToolCall,
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
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
    except Exception as exc:
        return json.dumps({"error": type(exc).__name__})


def _assistant_tool_request(calls: tuple[ChatToolCall, ...]) -> dict[str, Any]:
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


def _tools_used(packet: AgentPacket) -> tuple[AgentTool, ...]:
    tools: list[AgentTool] = []
    for name in packet.tool_names:
        try:
            tools.append(AgentTool(name))
        except ValueError:
            continue
    return tuple(dict.fromkeys(tools))


def _route_for(packet: AgentPacket) -> QueryRoute:
    if packet.live_results:
        return QueryRoute.LIVE
    return QueryRoute.RELATED


async def _ensure_official_fetch(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    packet: AgentPacket,
) -> None:
    """Fetch official layers the heuristics are confident about, concurrently."""

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
        except Exception:
            return

    await asyncio.gather(*(_run(call) for call in calls))


async def _prefetch_reviewed_guidance(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    packet: AgentPacket,
) -> None:
    """Run the reviewed-guidance RAG early when the intent is unambiguous."""

    if packet.static_response is not None:
        return
    if not confident_guidance_intent(request.question):
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
    except Exception:
        return


async def _prefetch_selected(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
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
    except Exception:
        return


def _needs_location(request: QueryRequest) -> bool:
    if request.location is not None:
        return False
    if coarse_location_from_question(request.question) is not None:
        return False
    return live_query_requires_location(request.question)


async def _resolve_place(
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
