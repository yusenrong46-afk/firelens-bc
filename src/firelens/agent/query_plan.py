"""Immutable internal execution plan for one public agent request."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from firelens.agent.fallback_brain import planned_static_subrequest
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    unsupported_live_topics,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.live_handoffs import related_live_links
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_out_of_province_label,
    is_province_wide_label,
)
from firelens.contracts import (
    AskResponse,
    LiveResultKind,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)
from firelens.live import LiveDataErrorKind, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator


class AgentRequestMode(StrEnum):
    """The application-owned execution shape for one request."""

    STATIC = "static"
    LIVE = "live"
    MIXED = "mixed"
    SELECTED = "selected"
    TERMINAL = "terminal"


class AgentGeography(StrEnum):
    """The only geography scopes an internal plan may authorize."""

    NONE = "none"
    SELECTED_RECORD = "selected_record"
    LOCATION_RADIUS = "location_radius"
    PROVINCE_WIDE = "province_wide"


class AgentScopeResult(StrEnum):
    """Whether geography is bound or the request terminated explicitly."""

    READY = "ready"
    REQUIRES_INPUT = "requires_input"
    SCOPE_REDIRECT = "scope_redirect"


@dataclass(frozen=True, slots=True)
class PlannedToolCall:
    """One exact allowlisted call, represented without a mutable argument map."""

    name: AgentTool
    arguments: tuple[tuple[str, str], ...] = ()

    def as_arguments(self) -> dict[str, str]:
        return dict(self.arguments)

    def matches(self, name: str, arguments: dict[str, Any] | None) -> bool:
        if name != self.name.value:
            return False
        normalized = {
            str(key): str(value)
            for key, value in (arguments or {}).items()
            if value is not None
        }
        return normalized == self.as_arguments()


@dataclass(frozen=True, slots=True)
class AgentQueryPlan:
    """The sole authority for geography, layers, and tool dispatch this turn."""

    route: QueryRoute
    mode: AgentRequestMode
    live_layers: tuple[LiveResultKind, ...]
    geography: AgentGeography
    location_label: str | None
    static_subrequest: str | None
    tool_calls: tuple[PlannedToolCall, ...]
    scope_result: AgentScopeResult = AgentScopeResult.READY
    terminal_response: AskResponse | None = None

    def __post_init__(self) -> None:
        if (
            self.mode in {AgentRequestMode.LIVE, AgentRequestMode.MIXED}
            and not self.live_layers
        ):
            raise ValueError("live and mixed plans require at least one live layer")
        if self.mode == AgentRequestMode.MIXED and not self.static_subrequest:
            raise ValueError("mixed plans require an exact static subrequest")
        if self.mode == AgentRequestMode.TERMINAL and self.terminal_response is None:
            raise ValueError("terminal plans require an application-owned response")
        partial_redirect = (
            self.mode == AgentRequestMode.STATIC
            and self.route == QueryRoute.RELATED
            and self.scope_result == AgentScopeResult.SCOPE_REDIRECT
        )
        if (
            self.mode != AgentRequestMode.TERMINAL
            and self.scope_result != AgentScopeResult.READY
            and not partial_redirect
        ):
            raise ValueError("non-terminal plans must have ready scope")

    def authorizes(self, name: str, arguments: dict[str, Any] | None) -> bool:
        return any(call.matches(name, arguments) for call in self.tool_calls)

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        """Return the bounded deterministic projection used by offline evidence."""

        del mode
        return {
            "route": self.route.value,
            "mode": self.mode.value,
            "live_layers": [layer.value for layer in self.live_layers],
            "geography": self.geography.value,
            "location_label": self.location_label,
            "static_subrequest": self.static_subrequest,
            "scope_result": self.scope_result.value,
            "tool_calls": [
                {"name": call.name.value, "arguments": call.as_arguments()}
                for call in self.tool_calls
            ],
            "terminal_response_mode": (
                self.terminal_response.response_mode.value
                if self.terminal_response is not None
                else None
            ),
        }


def _location_prompt(request: QueryRequest, *, unresolved: bool) -> AskResponse:
    if unresolved:
        answer = (
            "FireLens could not match that place to a British Columbia community. "
            "Enter a BC community name (for example Kelowna or Prince George) or "
            "share an approximate location to continue."
        )
        limitation = (
            "The place label did not resolve to a BC community, so no official "
            "records were fetched."
        )
    else:
        answer = (
            "A BC community or approximate location is needed before FireLens can "
            "look up current official records for this request."
        )
        limitation = "No official records were fetched because a location is required."
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=answer,
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Enter a BC community FireLens can look up.",
            continuation_question=request.question,
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[limitation],
    )


def _scope_redirect(request: QueryRequest, topics: tuple[str, ...]) -> AskResponse:
    del request
    links = related_live_links(topics)
    if topics:
        answer = (
            "FireLens is not connected to an official live source for "
            f"{', '.join(topics)}. Open the related official service for the current value."
        )
        limitations = ["FireLens did not substitute unrelated wildfire records."]
    else:
        answer = (
            "FireLens reads official British Columbia wildfire sources only. Use the "
            "relevant jurisdiction's official wildfire or emergency service for current records."
        )
        limitations = ["FireLens covers official British Columbia layers only."]
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=answer,
        reason_code=ReasonCode.SCOPE_REDIRECT,
        related_links=links,
        limitations=limitations,
    )


def _unbound_live_redirect(request: QueryRequest) -> AskResponse:
    del request
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            "Select a mapped official record or name a British Columbia community "
            "before asking about that current fire. FireLens did not substitute a record."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No current record was fetched for an unbound reference."],
    )


def _call(name: AgentTool, **arguments: str) -> PlannedToolCall:
    return PlannedToolCall(name=name, arguments=tuple(sorted(arguments.items())))


def _live_calls(
    layers: tuple[LiveResultKind, ...],
    *,
    geography: AgentGeography,
    location_label: str | None,
) -> list[PlannedToolCall]:
    arguments = (
        {"place_label": location_label}
        if geography == AgentGeography.LOCATION_RADIUS and location_label is not None
        else {}
    )
    calls: list[PlannedToolCall] = []
    if any(layer in {LiveResultKind.INCIDENT, LiveResultKind.PERIMETER} for layer in layers):
        calls.append(_call(AgentTool.LIST_OFFICIAL_FIRES, **arguments))
    if LiveResultKind.EVACUATION in layers:
        calls.append(_call(AgentTool.LIST_OFFICIAL_EVACUATIONS, **arguments))
    return calls


def plan_agent_request(request: QueryRequest) -> AgentQueryPlan:
    """Create the deterministic plan projection before external place resolution."""

    public_plan = plan_query(request)
    selected = request.context.selected_live_result_id
    if selected and (
        is_selected_live_request(request)
        or is_unsupported_selected_request(request)
        or is_distance_request(request)
    ):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.SELECTED,
            live_layers=(),
            geography=AgentGeography.SELECTED_RECORD,
            location_label=None,
            static_subrequest=None,
            tool_calls=(_call(AgentTool.GET_OFFICIAL_FIRE, result_id=selected),),
        )

    topics = unsupported_live_topics(request.question)
    layers = live_layers_for_question(request.question)
    parsed_intent = parse_request_intent(request.question)
    supported_live_clause = parsed_intent.has_live_records
    if topics and not supported_live_clause:
        layers = ()
    static_query = planned_static_subrequest(request.question)
    location = request.location or coarse_location_from_question(request.question)
    actual_live_request = bool(
        layers
        or parsed_intent.has_live_records
        or public_plan.route == QueryRoute.LIVE
        or topics
    )
    outside_bc_scope = bool(
        parsed_intent.requests_non_bc_scope
        or (location is not None and is_out_of_province_label(location.label))
    )
    if actual_live_request and outside_bc_scope:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=layers,
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=static_query,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_scope_redirect(request, ()),
        )
    if not layers:
        if topics and static_query is not None:
            return AgentQueryPlan(
                route=QueryRoute.RELATED,
                mode=AgentRequestMode.STATIC,
                live_layers=(),
                geography=AgentGeography.NONE,
                location_label=None,
                static_subrequest=static_query,
                tool_calls=(_call(AgentTool.SEARCH_REVIEWED_GUIDANCE, query=static_query),),
                scope_result=AgentScopeResult.SCOPE_REDIRECT,
            )
        if public_plan.route == QueryRoute.LIVE or topics:
            return AgentQueryPlan(
                route=QueryRoute.LIVE,
                mode=AgentRequestMode.TERMINAL,
                live_layers=(),
                geography=AgentGeography.NONE,
                location_label=None,
                static_subrequest=static_query,
                tool_calls=(),
                scope_result=AgentScopeResult.SCOPE_REDIRECT,
                terminal_response=(
                    _scope_redirect(request, topics)
                    if topics
                    else _unbound_live_redirect(request)
                ),
            )
        return AgentQueryPlan(
            route=public_plan.route,
            mode=AgentRequestMode.STATIC,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=static_query,
            tool_calls=(
                (_call(AgentTool.SEARCH_REVIEWED_GUIDANCE, query=static_query),)
                if static_query is not None
                else ()
            ),
        )

    if location is None and live_query_requires_location(request.question):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=layers,
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=static_query,
            tool_calls=(),
            scope_result=AgentScopeResult.REQUIRES_INPUT,
            terminal_response=_location_prompt(request, unresolved=False),
        )

    geography = (
        AgentGeography.LOCATION_RADIUS
        if location is not None and not is_province_wide_label(location.label)
        else AgentGeography.PROVINCE_WIDE
    )
    location_label = (
        location.label
        if location is not None and geography == AgentGeography.LOCATION_RADIUS
        else None
    )

    calls = _live_calls(layers, geography=geography, location_label=location_label)
    mode = AgentRequestMode.MIXED if static_query else AgentRequestMode.LIVE
    if static_query:
        calls.append(_call(AgentTool.SEARCH_REVIEWED_GUIDANCE, query=static_query))
    return AgentQueryPlan(
        route=QueryRoute.LIVE,
        mode=mode,
        live_layers=layers,
        geography=geography,
        location_label=location_label,
        static_subrequest=static_query,
        tool_calls=tuple(calls),
    )


async def build_agent_query_plan(
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
) -> AgentQueryPlan:
    """Build and externally bind the one internal execution plan for this request."""

    plan = plan_agent_request(request)
    if (
        plan.mode == AgentRequestMode.TERMINAL
        or plan.geography != AgentGeography.LOCATION_RADIUS
        or plan.location_label is None
    ):
        return plan
    location = request.location or coarse_location_from_question(request.question)
    if location is None:
        return plan
    try:
        await live_coordinator.live_service.resolve_location(location)
    except LiveDataUnavailable as exc:
        if exc.kind != LiveDataErrorKind.NOT_FOUND:
            return plan
    except (AttributeError, TypeError, ValueError):
        pass
    else:
        return plan
    if plan.mode == AgentRequestMode.MIXED:
        return plan
    return AgentQueryPlan(
        route=QueryRoute.LIVE,
        mode=AgentRequestMode.TERMINAL,
        live_layers=plan.live_layers,
        geography=AgentGeography.LOCATION_RADIUS,
        location_label=plan.location_label,
        static_subrequest=plan.static_subrequest,
        tool_calls=(),
        scope_result=AgentScopeResult.REQUIRES_INPUT,
        terminal_response=_location_prompt(request, unresolved=True),
    )
