"""One bounded agent over official live, reviewed, and general-answer tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from firelens.agent.budget import RequestExecutionPolicy
from firelens.agent.loop import run_agent_loop
from firelens.agent.query_plan import AgentRequestMode, build_agent_query_plan
from firelens.agent.rails import input_seatbelt
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    reviewed_guidance_intent,
)
from firelens.answering.location_intent import (
    asks_for_personal_location,
    coarse_location_from_question,
)
from firelens.answering.responses import safe_abstention
from firelens.contracts import (
    AskResponse,
    EvidenceStatus,
    LiveResultKind,
    LocationInput,
    QueryRequest,
    QueryRoute,
    ResponseMode,
)
from firelens.live_answering import LiveAnswerCoordinator

_PLACE_CORRECTION_PATTERNS = (
    re.compile(
        r"^(?:i\s+(?:mean|meant)|actually|no[,]?\s*wait[,]?)\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)(?:\s+(?:not|instead of)\b.*)?[.?!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<place>[a-z][a-z .'-]{1,80}?)\s+(?:not|instead of)\s+"
        r"[a-z][a-z .'-]{1,80}[.?!]*$",
        re.IGNORECASE,
    ),
)


class StaticAnswerService(Protocol):
    async def ask(
        self,
        request: QueryRequest,
        *,
        allow_live: bool = True,
        prefer_reviewed_quotes: bool = False,
    ) -> AskResponse: ...


@dataclass(frozen=True)
class AgentExecution:
    response: AskResponse
    route: QueryRoute
    tools: tuple[AgentTool, ...]
    policy: RequestExecutionPolicy = field(default_factory=RequestExecutionPolicy)


def _static_tool(response: AskResponse) -> AgentTool:
    if response.response_mode in {
        ResponseMode.GROUNDED,
        ResponseMode.PARTIAL,
        ResponseMode.CONFLICT,
    }:
        return AgentTool.SEARCH_REVIEWED_GUIDANCE
    return AgentTool.ANSWER_GENERAL_BACKGROUND


def _live_tools(request: QueryRequest, response: AskResponse) -> tuple[AgentTool, ...]:
    tools: list[AgentTool] = []
    if LiveAnswerCoordinator.is_selected_live_request(
        request
    ) or LiveAnswerCoordinator.is_unsupported_selected_request(request):
        tools.append(AgentTool.GET_OFFICIAL_FIRE)
    else:
        kinds = {result.kind for result in response.live_results}
        if LiveResultKind.INCIDENT in kinds or LiveResultKind.PERIMETER in kinds:
            tools.append(AgentTool.LIST_OFFICIAL_FIRES)
        if LiveResultKind.EVACUATION in kinds:
            tools.append(AgentTool.LIST_OFFICIAL_EVACUATIONS)
    claim_statuses = {claim.evidence_status for claim in response.claims}
    if EvidenceStatus.VERIFIED_CORPUS in claim_statuses:
        tools.append(AgentTool.SEARCH_REVIEWED_GUIDANCE)
    if EvidenceStatus.GENERAL_BACKGROUND in claim_statuses:
        tools.append(AgentTool.ANSWER_GENERAL_BACKGROUND)
    return tuple(dict.fromkeys(tools))


def _live_place_correction(request: QueryRequest) -> QueryRequest | None:
    """Reapply a terse place correction only to the latest live user task."""

    place: str | None = None
    for pattern in _PLACE_CORRECTION_PATTERNS:
        match = pattern.match(request.question.strip())
        if match is not None:
            place = match.group("place").strip(" .?!'\"")
            break
    if place is None:
        return None
    previous_questions = [turn.content for turn in request.history if turn.role == "user"]
    if not previous_questions:
        return None
    previous = previous_questions[-1]
    previous_request = QueryRequest(question=previous)
    if plan_query(previous_request).route != QueryRoute.LIVE and not live_layers_for_question(
        previous
    ):
        return None
    if asks_for_personal_location(place):
        previous_location = coarse_location_from_question(previous)
        corrected_question = previous
        if previous_location is not None and previous_location.label is not None:
            corrected_question = re.sub(
                re.escape(previous_location.label),
                "my place",
                previous,
                count=1,
                flags=re.IGNORECASE,
            )
        if corrected_question == previous:
            layers = set(live_layers_for_question(previous))
            if LiveResultKind.EVACUATION in layers:
                corrected_question = "Show current evacuation alerts and orders near my place."
            elif layers == {LiveResultKind.PERIMETER}:
                corrected_question = "Show the current wildfire perimeters near my place."
            else:
                corrected_question = "Show current wildfires near my place."
        return request.model_copy(
            update={
                "question": corrected_question,
                "location": None,
            }
        )
    if reviewed_guidance_intent(place):
        return None
    parsed_place = coarse_location_from_question(f"map {place}")
    if parsed_place is None or parsed_place.label is None:
        return None
    place = parsed_place.label
    try:
        location = LocationInput(label=place)
    except ValueError:
        return None
    return request.model_copy(
        update={
            "question": previous,
            "location": location,
        }
    )


class FireLensAgent:
    """Select and execute only application-owned tools for one public request."""

    def __init__(
        self,
        static_service: StaticAnswerService,
        live_coordinator: LiveAnswerCoordinator,
    ) -> None:
        self.static_service = static_service
        self.live_coordinator = live_coordinator

    async def answer(self, request: QueryRequest) -> AgentExecution:
        seatbelt = input_seatbelt(request)
        if seatbelt is not None:
            reason, answer = seatbelt
            policy = RequestExecutionPolicy(route="prohibited")
            return AgentExecution(
                response=safe_abstention(
                    uuid4().hex,
                    answer=answer,
                    reason_code=reason,
                    limitations=[answer],
                ),
                route=QueryRoute.PROHIBITED,
                tools=(),
                policy=policy,
            )
        effective_request = _live_place_correction(request) or request
        agent_plan = await build_agent_query_plan(effective_request, self.live_coordinator)
        if agent_plan.mode == AgentRequestMode.TERMINAL:
            assert agent_plan.terminal_response is not None
            return AgentExecution(
                response=agent_plan.terminal_response,
                route=agent_plan.route,
                tools=(),
                policy=RequestExecutionPolicy(route="requires_input"),
            )
        if agent_plan.route == QueryRoute.CAPABILITY:
            response = await self.static_service.ask(effective_request)
            return AgentExecution(
                response=response,
                route=QueryRoute.CAPABILITY,
                tools=(_static_tool(response),),
                policy=RequestExecutionPolicy(route="capability"),
            )
        provider = getattr(self.static_service, "provider", None)
        response, route, tools, packet = await run_agent_loop(
            effective_request,
            live_coordinator=self.live_coordinator,
            static_service=self.static_service,
            provider=provider if hasattr(provider, "chat_turn") else None,
            query_plan=agent_plan,
        )
        if response.response_mode == ResponseMode.LIVE:
            route = QueryRoute.LIVE
        if not tools and response.live_results:
            tools = _live_tools(effective_request, response)
        return AgentExecution(response=response, route=route, tools=tools, policy=packet.policy)
