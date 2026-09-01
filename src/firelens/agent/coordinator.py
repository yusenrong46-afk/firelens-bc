"""One bounded agent over official live, reviewed, and general-answer tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from firelens.agent.budget import RequestExecutionPolicy
from firelens.agent.loop import run_agent_loop
from firelens.agent.query_plan import AgentRequestMode, AgentScopeResult, build_agent_query_plan
from firelens.agent.rails import input_seatbelt
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    reviewed_guidance_intent,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_patterns import is_personalized_route_request
from firelens.answering.live_handoffs import official_safety_links
from firelens.answering.live_request_intent import (
    is_prescriptive_evacuation_distance_request,
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
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)
from firelens.guidance_capabilities import resolve_capability
from firelens.live_answering import LiveAnswerCoordinator

_PLACE_CORRECTION_PATTERNS = (
    re.compile(
        r"^(?:i\s+(?:mean|meant)|"
        r"actually(?:[,]?\s+i\s+(?:mean|meant))?|"
        r"no[,]?\s*wait[,]?)\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)(?:\s+(?:not|instead)(?:\s+of)?\b.*)?[.?!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<place>[a-z][a-z .'-]{1,80}?)\s+(?:not|instead of)\s+"
        r"[a-z][a-z .'-]{1,80}[.?!]*$",
        re.IGNORECASE,
    ),
)

_ANSWER_MISMATCH_CORRECTION = re.compile(
    r"^(?:"
    r"(?:your|that|this)\s+(?:answer|response)\s+"
    r"(?:has|had)\s+nothing\s+to\s+do\s+with\s+(?:my|the)\s+question|"
    r"(?:your|that|this)\s+(?:answer|response)\s+"
    r"(?:did\s+not|didn't|does\s+not|doesn't)\s+"
    r"(?:answer|address|match)\s+(?:my|the)\s+question|"
    r"you\s+misunderstood\s+(?:my|the)\s+question|"
    r"that\s+is\s+not\s+what\s+i\s+asked"
    r")[.?!]*$",
    re.IGNORECASE,
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
    if reviewed_guidance_intent(place) or parse_request_intent(place).has_prefetchable_guidance:
        return None
    parsed_place = coarse_location_from_question(f"map {place}")
    if parsed_place is None or parsed_place.label is None:
        return None
    place = parsed_place.label
    try:
        location = LocationInput(label=place)
    except ValueError:
        return None
    corrected_question = previous
    previous_location = coarse_location_from_question(previous)
    if previous_location is not None and previous_location.label is not None:
        corrected_question = re.sub(
            re.escape(previous_location.label),
            place,
            previous,
            count=1,
            flags=re.IGNORECASE,
        )
    return request.model_copy(
        update={
            "question": corrected_question,
            "location": location,
        }
    )


def _answer_mismatch_correction(request: QueryRequest) -> QueryRequest | None:
    """Retry the last user task after an explicit answer-mismatch correction."""

    if _ANSWER_MISMATCH_CORRECTION.match(request.question.strip()) is None:
        return None
    previous_questions = [turn.content for turn in request.history if turn.role == "user"]
    if not previous_questions:
        return None
    previous = previous_questions[-1].strip()
    if not previous or _ANSWER_MISMATCH_CORRECTION.match(previous) is not None:
        return None
    return request.model_copy(update={"question": previous})


def _useful_safety_boundary(
    request: QueryRequest,
    *,
    reason: ReasonCode,
    default_answer: str,
) -> AskResponse:
    """Block the decision while preserving one deterministic official next step."""

    if reason != ReasonCode.PERSONALIZED_SAFETY_DECISION:
        return safe_abstention(
            uuid4().hex,
            answer=default_answer,
            reason_code=reason,
            limitations=[default_answer],
        )
    if is_personalized_route_request(request.question):
        answer = (
            "FireLens cannot choose an evacuation road or route. Follow instructions "
            "from the issuing local authority, and check EmergencyInfoBC and DriveBC "
            "for current evacuation information and road conditions."
        )
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=answer,
            reason_code=reason,
            related_links=official_safety_links(include_road_conditions=True),
            limitations=["FireLens did not recommend or rank an evacuation route."],
        )
    stated_location = request.location or coarse_location_from_question(request.question)
    if stated_location is not None:
        place = stated_location.label or "the provided location"
        answer = (
            "FireLens cannot decide whether you should evacuate. You can ask it to "
            f"check official evacuation alerts and orders for {place}; always follow "
            "instructions from the issuing local authority."
        )
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=answer,
            reason_code=reason,
            related_links=official_safety_links(),
            limitations=[
                "Official evacuation records do not replace instructions from the issuing authority."
            ],
        )
    answer = (
        "FireLens cannot decide whether you should evacuate. It can check official "
        "evacuation alerts and orders for a BC community; always follow instructions "
        "from the issuing local authority."
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=answer,
        reason_code=reason,
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Enter a BC community FireLens can check for official evacuation records.",
            continuation_question=("Show current evacuation alerts and orders near my place."),
        ),
        related_links=official_safety_links(),
        limitations=[
            "Official evacuation records do not replace instructions from the issuing authority."
        ],
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
                response=_useful_safety_boundary(
                    request,
                    reason=reason,
                    default_answer=answer,
                ),
                route=QueryRoute.PROHIBITED,
                tools=(),
                policy=policy,
            )
        place_label = request.location.label if request.location is not None else None
        capability = resolve_capability(request.question, place_label=place_label)
        if capability is not None and capability.source_mode == "corpus":
            # A registry-validated corpus capability carries its own exact
            # source bindings.  Keep the original request and avoid the outer
            # agent loop, whose model prose and tool selection cannot add
            # publication authority.
            response = await self.static_service.ask(
                request,
                allow_live=False,
                prefer_reviewed_quotes=True,
            )
            return AgentExecution(
                response=response,
                route=QueryRoute.RELATED,
                tools=(_static_tool(response),),
                policy=RequestExecutionPolicy(route="validated_capability"),
            )
        effective_request = (
            _live_place_correction(request) or _answer_mismatch_correction(request) or request
        )
        agent_plan = await build_agent_query_plan(effective_request, self.live_coordinator)
        if (
            agent_plan.mode == AgentRequestMode.SELECTED
            and effective_request.context.selected_live_result_id is None
            and agent_plan.tool_calls
        ):
            selected_id = agent_plan.tool_calls[0].as_arguments().get("result_id")
            if selected_id:
                effective_request = effective_request.model_copy(
                    update={
                        "context": effective_request.context.model_copy(
                            update={"selected_live_result_id": selected_id}
                        )
                    }
                )
        if agent_plan.mode == AgentRequestMode.TERMINAL:
            assert agent_plan.terminal_response is not None
            terminal_route = (
                "requires_input"
                if agent_plan.scope_result == AgentScopeResult.REQUIRES_INPUT
                else "deterministic_redirect"
            )
            return AgentExecution(
                response=agent_plan.terminal_response,
                route=agent_plan.route,
                tools=(),
                policy=RequestExecutionPolicy(route=terminal_route),
            )
        if agent_plan.route == QueryRoute.CAPABILITY:
            response = await self.static_service.ask(effective_request)
            return AgentExecution(
                response=response,
                route=QueryRoute.CAPABILITY,
                tools=(_static_tool(response),),
                policy=RequestExecutionPolicy(route="capability"),
            )
        if (
            agent_plan.mode == AgentRequestMode.STATIC
            and not agent_plan.tool_calls
            and agent_plan.route in {QueryRoute.RELATED, QueryRoute.TANGENT}
            and not is_prescriptive_evacuation_distance_request(effective_request)
        ):
            # The static service already owns both reviewed-corpus answers and
            # validated, visibly labelled general background.  Sending an
            # ordinary non-live question through the outer tool loop instead
            # loses that distinction and can collapse a real corpus match into
            # a generic scope redirect.
            response = await self.static_service.ask(
                effective_request,
                allow_live=False,
                prefer_reviewed_quotes=True,
            )
            return AgentExecution(
                response=response,
                route=agent_plan.route,
                tools=(_static_tool(response),),
                policy=RequestExecutionPolicy(route="static_service"),
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
