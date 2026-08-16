"""Bounded Luna tool loop: fetch/RAG tools, write, veto, rewrite."""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import uuid4

from firelens.agent.chat import ChatToolCall, ChatTurn
from firelens.agent.fallback_brain import fallback_write, heuristic_tool_calls
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
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.live_distance import distance_answer, location_request
from firelens.answering.live_handoffs import related_live_links
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unbound_distance_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    CoarseResolvedLocation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
    render_claim_texts,
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
            _no_substitute_response(request),
            QueryRoute.LIVE,
            (AgentTool.GET_OFFICIAL_FIRE,),
        )
    await _prefetch_selected(request, live_coordinator, static_service, packet)
    await _ensure_official_fetch(request, live_coordinator, static_service, packet)
    if provider is None:
        answer = await _offline_loop(request, live_coordinator, static_service, packet)
    else:
        try:
            answer = await _provider_loop(
                request, live_coordinator, static_service, provider, packet
            )
        except ProviderError:
            answer = await _offline_loop(request, live_coordinator, static_service, packet)
    await _ensure_official_fetch(request, live_coordinator, static_service, packet)
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
            quoted = _quoted_guidance_response(request, packet)
            if quoted is not None:
                return quoted, _route_for(packet), _tools_used(packet)
            return (
                _safety_response(request),
                QueryRoute.PROHIBITED,
                _tools_used(packet),
            )
        answer = fallback_write(request, packet)
        if output_rail_errors(answer, packet):
            answer = "The official records available for this request do not report that fact."
    return _compose_response(request, packet, answer), _route_for(packet), _tools_used(packet)


async def _offline_loop(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: StaticAnswerService,
    packet: AgentPacket,
) -> str:
    calls = heuristic_tool_calls(request)
    if not calls:
        if packet.related_links:
            return _handoff_answer(packet)
        return (
            "That question is outside FireLens fire and preparedness sources. "
            "Ask about official wildfire records or reviewed guidance."
        )
    for call in calls:
        if not execution_allowed(call["name"]):
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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": request.question,
                    "selected_live_result_id": request.context.selected_live_result_id,
                    "place_label": request.location.label if request.location else None,
                    **(
                        {
                            "official_packet": packet.facts_for_model(),
                            "instruction": (
                                "Official records are already fetched. Write from "
                                "official_packet. Do not pass BC or British Columbia "
                                "as place_label."
                            ),
                        }
                        if packet.live_results
                        else {}
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]
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
                    "official_packet": packet.facts_for_model(),
                    "previous_answer_rejected_for": errors,
                    "instruction": (
                        "Rewrite using only official_packet. Remove safety advice, "
                        "unfetched fires, and civic addresses."
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
    """Fetch official layers when Luna skipped tools or used a province-wide label."""

    if packet.live_results:
        return
    if {"missing_selected_record", "unbound_selected_record"} & set(packet.unknown_topics):
        return
    live_tools = {
        AgentTool.LIST_OFFICIAL_FIRES.value,
        AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
        AgentTool.GET_OFFICIAL_FIRE.value,
    }
    for call in heuristic_tool_calls(request):
        if call["name"] not in live_tools:
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


def _quoted_guidance_response(request: QueryRequest, packet: AgentPacket) -> AskResponse | None:
    """Keep reviewed alert/order definitions when Luna's prose trips the safety rail."""

    static = packet.static_response
    if (
        static is None
        or static.response_mode not in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
        or static.validation is None
        or not static.validation.accepted
        or not static.claims
        or not static.evidence
    ):
        return None
    answer = static.answer
    if not answer:
        return None
    return _compose_response(request, packet, answer)


def _safety_response(request: QueryRequest) -> AskResponse:
    del request
    answer = "FireLens cannot provide personalized safety advice or evacuation decisions."
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer=answer,
        reason_code=ReasonCode.PERSONALIZED_SAFETY_DECISION,
        limitations=[answer],
    )


def _no_substitute_response(request: QueryRequest) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer=(
            "Select a mapped fire or perimeter before asking about a specific record. "
            "FireLens will not substitute a different nearby record."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        selected_live_result_id=request.context.selected_live_result_id,
        limitations=[
            "FireLens did not substitute a different nearby fire.",
            "FireLens did not substitute the nearest fire for an unbound reference.",
            "No matching record is not a safety determination.",
        ],
    )


def _handoff_answer(packet: AgentPacket) -> str:
    topics = (
        ", ".join(packet.unknown_topics) if packet.unknown_topics else "that live information"
    )
    if packet.related_links:
        titles = ", ".join(link.title for link in packet.related_links)
        return (
            f"FireLens is not connected to an official live source for {topics}. "
            f"Open the related official service for the current value: {titles}."
        )
    return "FireLens is not connected to an official live source for that information."


async def _resolve_place(
    live_coordinator: LiveAnswerCoordinator,
    request: QueryRequest,
    packet: AgentPacket,
) -> None:
    location = request.location or coarse_location_from_question(request.question)
    if location is None:
        return
    try:
        latitude, longitude = await live_coordinator.live_service.resolve_location(location)
    except (LiveDataUnavailable, AttributeError, TypeError, ValueError):
        return
    packet.resolved_location = CoarseResolvedLocation(latitude=latitude, longitude=longitude)


def _compose_response(
    request: QueryRequest,
    packet: AgentPacket,
    answer: str,
) -> AskResponse:
    return _with_packet_fields(request, packet, _build_ask_response(request, packet, answer))


_LAYER_UNAVAILABLE = (
    "Some official live layers were unavailable for this request. That is not an all-clear."
)


def _with_packet_fields(
    request: QueryRequest,
    packet: AgentPacket,
    response: AskResponse,
) -> AskResponse:
    updates: dict[str, Any] = {}
    limitations = list(response.limitations)
    if packet.unavailable_layers:
        updates["unavailable_layers"] = list(packet.unavailable_layers)
        if _LAYER_UNAVAILABLE not in limitations:
            limitations.append(_LAYER_UNAVAILABLE)
            updates["limitations"] = limitations
    if request.context.selected_live_result_id and not response.selected_live_result_id:
        updates["selected_live_result_id"] = request.context.selected_live_result_id
    if packet.resolved_location is not None and response.resolved_location is None:
        updates["resolved_location"] = packet.resolved_location
    return response.model_copy(update=updates) if updates else response


def _missing_selected(request: QueryRequest, packet: AgentPacket) -> bool:
    if (
        "missing_selected_record" in packet.unknown_topics
        or "unbound_selected_record" in packet.unknown_topics
    ):
        return True
    selected_id = request.context.selected_live_result_id
    if not selected_id:
        return False
    if not (
        is_selected_live_request(request)
        or is_unsupported_selected_request(request)
        or is_distance_request(request)
    ):
        return False
    return not any(item.result_id == selected_id for item in packet.live_results)


def _build_ask_response(
    request: QueryRequest,
    packet: AgentPacket,
    answer: str,
) -> AskResponse:
    static = packet.static_response
    live = packet.live_results
    links = packet.related_links
    if _missing_selected(request, packet):
        return _no_substitute_response(request)
    if is_unsupported_selected_request(request) and live:
        selected_id = request.context.selected_live_result_id
        selected = next((item for item in live if item.result_id == selected_id), None)
        if selected is None:
            return _no_substitute_response(request)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=answer,
            reason_code=ReasonCode.SCOPE_REDIRECT,
            limitations=[
                "FireLens did not infer a cause or prediction that the selected record does not state."
            ],
            related_links=[
                RelatedLink(
                    title="Selected official record",
                    url=selected.source_url,
                    description="Official source for the selected wildfire record.",
                )
            ],
            selected_live_result_id=selected.result_id,
        )
    if (
        live
        and static is not None
        and static.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
        and static.claims
        and static.evidence
        and static.validation is not None
        and static.validation.accepted
    ):
        freshness = aggregate_live_freshness(live)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static.trace_id,
            response_mode=ResponseMode.MIXED,
            answer=answer,
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading="Current official records",
                    text=answer,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                    heading="Reviewed preparedness guidance",
                    text=render_claim_texts(static.claims),
                ),
            ],
            claims=static.claims,
            evidence=static.evidence,
            live_results=live,
            aggregate_freshness=freshness,
            limitations=list(static.limitations),
            validation=static.validation,
            selected_live_result_id=request.context.selected_live_result_id,
            resolved_location=packet.resolved_location,
        )
    if live and links:
        freshness = aggregate_live_freshness(live)
        handoff = _handoff_answer(packet)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.MIXED,
            answer=f"{answer}\n\nRelated official information: {handoff}",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading="Current official records",
                    text=answer,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.OFFICIAL_HANDOFF,
                    heading="Related official information",
                    text=handoff,
                ),
            ],
            live_results=live,
            aggregate_freshness=freshness,
            related_links=links,
            resolved_location=packet.resolved_location,
            selected_live_result_id=request.context.selected_live_result_id,
            limitations=["This uses official records and is not a safety assessment."],
        )
    if live:
        freshness = aggregate_live_freshness(live)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.LIVE,
            answer=answer,
            live_results=live,
            aggregate_freshness=freshness,
            selected_live_result_id=request.context.selected_live_result_id,
            resolved_location=packet.resolved_location,
            limitations=["This uses official records and is not a safety assessment."],
        )
    if static is not None and links:
        topics = [topic for topic in packet.unknown_topics if topic != "prediction"]
        merged = supported_static_when_live_missing(
            static,
            _handoff_answer(packet),
            limitations=[
                "Unsupported live topics: " + ", ".join(topics)
                if topics
                else "FireLens did not invent a live feed it does not ingest."
            ],
            related_links=links,
            resolved_location=packet.resolved_location,
        )
        if merged is not None:
            return merged
    if static is not None:
        updates: dict[str, Any] = {}
        if request.context.selected_live_result_id and not static.selected_live_result_id:
            updates["selected_live_result_id"] = request.context.selected_live_result_id
        if packet.resolved_location is not None and static.resolved_location is None:
            updates["resolved_location"] = packet.resolved_location
        return static.model_copy(update=updates) if updates else static
    if links:
        handoff = _handoff_answer(packet)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=handoff,
            reason_code=ReasonCode.SCOPE_REDIRECT,
            related_links=links,
            resolved_location=packet.resolved_location,
            limitations=["FireLens did not invent a live feed it does not ingest."],
        )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=answer,
        reason_code=ReasonCode.SCOPE_REDIRECT,
        limitations=["No official record or reviewed passage supported a typed claim."],
    )
