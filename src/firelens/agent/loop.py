"""Bounded Luna tool loop: prefetch, skip discarded static writes, veto, rewrite."""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import uuid4

from firelens.agent.chat import ChatTurn
from firelens.agent.compose import (
    compose_response,
    handoff_answer,
    no_substitute_response,
    quoted_guidance_response,
    request_with_plan_selection,
    request_with_selected,
    safety_response,
)
from firelens.agent.failures import EXPECTED_TOOL_FAILURES, record_expected_failure
from firelens.agent.fallback_brain import (
    fallback_write,
    heuristic_tool_calls,
    should_prefetch_reviewed_guidance,
)
from firelens.agent.loop_support import (
    assign_route,
    assistant_tool_request,
    missing_location_result,
    pure_static_ready,
    route_for,
    safe_execute,
    skip_owned_model_write,
    tools_used,
)
from firelens.agent.packet import AgentPacket
from firelens.agent.prefetch import needs_location, prefetch_evidence, resolve_place
from firelens.agent.prompts import OPENROUTER_TOOLS, SYSTEM_PROMPT
from firelens.agent.query_plan import AgentQueryPlan
from firelens.agent.rails import execution_allowed, output_rail_errors
from firelens.agent.runtime_tools import execute_tool
from firelens.agent.tools import AgentTool
from firelens.answering.intent import unsupported_live_topics
from firelens.answering.live_analysis import (
    official_analysis_answer,
    replace_ungrounded_live_hedge,
    strip_precise_coordinates,
)
from firelens.answering.live_distance import distance_answer
from firelens.answering.live_handoffs import related_live_links
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_prescriptive_evacuation_distance_request,
    is_unbound_distance_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import is_national_scope_question
from firelens.contracts import AskResponse, QueryRequest, QueryRoute
from firelens.errors import ProviderError
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.compiler import compiled_static_text
from firelens.publication.fallback import official_handoff_response

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
    query_plan: AgentQueryPlan,
) -> tuple[AskResponse, QueryRoute, tuple[AgentTool, ...], AgentPacket]:
    """Run one Ask through Luna (or the offline stand-in) and rails."""

    request = request_with_plan_selection(request, query_plan)
    packet = AgentPacket(query_plan=query_plan)
    unsupported = tuple(unsupported_live_topics(request.question))
    packet.related_links = related_live_links(unsupported)
    packet.unknown_topics.extend(unsupported)
    if is_national_scope_question(request.question):
        packet.unknown_topics.append("out_of_province_place")
    if is_unsupported_selected_request(request):
        packet.unknown_topics.append("prediction")
    if is_prescriptive_evacuation_distance_request(request):
        packet.policy.route = "deterministic_redirect"
        return (
            official_handoff_response(uuid4().hex),
            QueryRoute.RELATED,
            (),
            packet,
        )
    if (
        unsupported
        and not query_plan.live_layers
        and not should_prefetch_reviewed_guidance(request.question)
    ):
        # Unsupported live topics: owned handoff, no provider or record substitution.
        await resolve_place(live_coordinator, request, packet)
        packet.policy.route = "deterministic_redirect"
        return (
            compose_response(request, packet, handoff_answer(packet)),
            QueryRoute.LIVE,
            (),
            packet,
        )
    if needs_location(request):
        return missing_location_result(request, packet)
    if is_unbound_distance_request(request):
        packet.policy.route = "deterministic_redirect"
        return (
            no_substitute_response(request),
            QueryRoute.LIVE,
            (AgentTool.GET_OFFICIAL_FIRE,),
            packet,
        )
    await prefetch_evidence(request, live_coordinator, static_service, packet, query_plan)
    request = request_with_selected(request, packet)
    skip_provider = skip_owned_model_write(query_plan, packet)
    if provider is None or skip_provider:
        answer = await _offline_loop(request, live_coordinator, static_service, packet)
    else:
        try:
            answer = await _provider_loop(
                request, live_coordinator, static_service, provider, packet
            )
        except ProviderError:
            packet.policy.fallback_reason = "provider_error"
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
            static_answer=None,
        )
        if analysis:
            answer = analysis
    if packet.live_results:
        answer = replace_ungrounded_live_hedge(answer, fallback_write(request, packet))
    answer = strip_precise_coordinates(answer)
    if not packet.live_results and packet.related_links and packet.resolved_location is None:
        await resolve_place(live_coordinator, request, packet)
    errors = output_rail_errors(answer, packet)
    if (
        errors
        and set(errors) != {"unfetched_fire_name"}
        and provider is not None
        and packet.policy.consume_rewrite()
    ):
        try:
            answer = await _rewrite(provider, request, packet, answer, errors)
        except ProviderError:
            packet.policy.fallback_reason = "rewrite_provider_error"
            answer = fallback_write(request, packet)
        errors = output_rail_errors(answer, packet)
    if errors:
        if "safety_or_medical_language" in errors:
            quoted = quoted_guidance_response(request, packet)
            if quoted is not None:
                return quoted, route_for(packet), tools_used(packet), packet
            return (
                safety_response(request),
                QueryRoute.PROHIBITED,
                tools_used(packet),
                packet,
            )
        packet.policy.fallback_reason = "output_rail"
        answer = fallback_write(request, packet)
        if output_rail_errors(answer, packet):
            answer = "The official records available for this request do not report that fact."
    assign_route(packet)
    return (
        compose_response(request, packet, answer),
        route_for(packet),
        tools_used(packet),
        packet,
    )


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
        except EXPECTED_TOOL_FAILURES as exc:
            record_expected_failure(packet, exc)
            continue
    return fallback_write(request, packet)


async def _provider_loop(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    provider: ChatProvider,
    packet: AgentPacket,
) -> str:
    static = packet.static_response
    if static is not None and pure_static_ready(packet):
        packet.policy.route = "pure_static_accepted"
        return (static.answer or "").strip()
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
        if not packet.policy.consume_outer_write():
            return fallback_write(request, packet)
        packet.policy.route = (
            "ready_mixed" if packet.static_response is not None else "ready_live"
        )
        turn = await provider.chat_turn(messages, tools=None)
        return (turn.content or "").strip() or fallback_write(request, packet)
    packet.policy.route = "unresolved_tool_loop"
    for _ in range(MAX_TOOL_ROUNDS):
        if not packet.policy.consume_tool_round():
            break
        turn = await provider.chat_turn(messages, tools=OPENROUTER_TOOLS)
        if not turn.tool_calls:
            if packet.policy.consume_outer_write():
                return (turn.content or "").strip() or fallback_write(request, packet)
            return fallback_write(request, packet)
        messages.append(assistant_tool_request(turn.tool_calls))
        for call in turn.tool_calls:
            content = await safe_execute(
                call, request, live_coordinator, static_service, packet
            )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    if packet.policy.consume_outer_write():
        final = await provider.chat_turn(messages, tools=None)
        return (final.content or "").strip() or fallback_write(request, packet)
    return fallback_write(request, packet)


async def _rewrite(
    provider: ChatProvider,
    request: QueryRequest,
    packet: AgentPacket,
    previous: str,
    errors: list[str],
) -> str:
    compiled = compiled_static_text(packet)
    if compiled:
        return compiled
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
