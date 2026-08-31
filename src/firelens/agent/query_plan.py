"""Immutable internal execution plan for one public agent request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from firelens.agent.fallback_brain import planned_static_subrequest
from firelens.agent.query_plan_boundaries import (
    absence_all_clear_boundary as _absence_all_clear_boundary,
)
from firelens.agent.query_plan_boundaries import (
    empty_map_location_prompt as _empty_map_location_prompt,
)
from firelens.agent.query_plan_boundaries import (
    evacuation_alert_distance_boundary as _evacuation_alert_distance_boundary,
)
from firelens.agent.query_plan_boundaries import (
    is_personal_travel_or_fuel_decision as _is_personal_travel_or_fuel_decision,
)
from firelens.agent.query_plan_boundaries import (
    location_prompt as _location_prompt,
)
from firelens.agent.query_plan_boundaries import (
    multi_place_comparison_limit as _multi_place_comparison_limit,
)
from firelens.agent.query_plan_boundaries import (
    record_reference_prompt as _record_reference_prompt,
)
from firelens.agent.query_plan_boundaries import (
    scope_redirect as _scope_redirect,
)
from firelens.agent.query_plan_boundaries import (
    selection_prompt as _selection_prompt,
)
from firelens.agent.query_plan_boundaries import (
    smoke_observation_location_prompt as _smoke_observation_location_prompt,
)
from firelens.agent.query_plan_boundaries import (
    travel_or_fuel_boundary as _travel_or_fuel_boundary,
)
from firelens.agent.query_plan_boundaries import (
    unbound_live_redirect as _unbound_live_redirect,
)
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    continues_prior_live_place,
    conversation_planning_question,
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    prefers_general_background,
    prior_anchor_user_question,
    unsupported_live_topics,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_patterns import is_unresolved_smoke_observation
from firelens.answering.intent_refresh import is_live_refresh_request
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.live_request_intent import (
    requires_selected_live_record,
    uses_selected_live_binding,
)
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_multi_place_fire_comparison,
    is_out_of_province_label,
    is_province_wide_label,
    is_province_wide_question,
)
from firelens.contracts import (
    AskResponse,
    LiveResultKind,
    LocationInput,
    QueryRequest,
    QueryRoute,
)
from firelens.live import LiveDataErrorKind, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator
from firelens.live_support import (
    official_fire_centre_from_question,
    official_fire_centre_label,
)


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


_VISIBLE_ORDINAL = re.compile(
    r"\b(?:the\s+)?(?P<rank>first|second|third|1st|2nd|3rd)\s+"
    r"(?:one|fire|wildfire|incident|record)\b",
    re.IGNORECASE,
)
_VISIBLE_ORDINAL_INDEX = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
}

# These questions use wildfire language as a metaphor, not as a request for
# current incident records. Keep this small and explicit: a generic mention of
# "market" must not override a genuine current-fire request.
_FINANCE_FIRE_METAPHOR = re.compile(
    r"\b(?:stock(?:[-\s]?market)?|share(?:s| price)?|portfolio|trading|investing)\b"
    r".{0,80}\b(?:wildfire|fire)\b|"
    r"\b(?:wildfire|fire)\b.{0,80}"
    r"\b(?:stock(?:[-\s]?market)?|share(?:s| price)?|portfolio|trading|investing)\b",
    re.IGNORECASE,
)

# A distance-free premise about apparent absence is not evidence that an area
# is safe. Handle it before live dispatch so an unsupported all-clear inference
# cannot turn into an unrelated province-wide roster.
_ABSENCE_ALL_CLEAR_PREMISE = re.compile(
    r"\b(?:no|zero)\s+(?:active\s+)?(?:fires?|wildfires?|incidents?)\b.{0,100}"
    r"\b(?:nothing\s+to\s+worry\s+about|safe|all[-\s]?clear|no\s+(?:risk|danger|threat))\b",
    re.IGNORECASE,
)

_UNBOUND_RECORD_REFERENCE = re.compile(
    r"\bwhich\s+(?:official\s+)?record\b.{0,80}\b(?:refer(?:ring)?|mean|mentioned)\b",
    re.IGNORECASE,
)
_VAGUE_LOCAL_LIVE_CONCERN = re.compile(
    r"\b(?:worry|concern(?:ed)?)\b.{0,48}\b(?:near|around|in)\s+[a-z]",
    re.IGNORECASE,
)


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


def _call(name: AgentTool, **arguments: str) -> PlannedToolCall:
    return PlannedToolCall(name=name, arguments=tuple(sorted(arguments.items())))


def _visible_ordinal_result_id(request: QueryRequest) -> str | None:
    match = _VISIBLE_ORDINAL.search(request.question)
    if match is None:
        return None
    index = _VISIBLE_ORDINAL_INDEX[match.group("rank").casefold()]
    visible = request.context.visible_live_result_ids
    return visible[index] if index < len(visible) else None


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

    question = request.question
    if _FINANCE_FIRE_METAPHOR.search(question):
        return AgentQueryPlan(
            route=QueryRoute.TANGENT,
            mode=AgentRequestMode.STATIC,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
        )
    # A stated community is a request to check that bounded live layer, not a
    # license to assume an all-clear.  The response rail still corrects the
    # inference after the official lookup.  Without a location, stop before a
    # province-wide roster could be misread as a local safety determination.
    absence_location = coarse_location_from_question(question) or request.location
    if _ABSENCE_ALL_CLEAR_PREMISE.search(question) and absence_location is None:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_absence_all_clear_boundary(),
        )
    if re.search(r"\bignore\b.{0,60}\bevacuation\s+alert\b", question, re.IGNORECASE):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_evacuation_alert_distance_boundary(),
        )
    if _is_personal_travel_or_fuel_decision(question):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_travel_or_fuel_boundary(),
        )
    if (
        is_unresolved_smoke_observation(question)
        and request.location is None
        and coarse_location_from_question(question) is None
    ):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.REQUIRES_INPUT,
            terminal_response=_smoke_observation_location_prompt(),
        )
    public_plan = plan_query(request)
    if public_plan.route == QueryRoute.TANGENT and prefers_general_background(request):
        return AgentQueryPlan(
            route=QueryRoute.TANGENT,
            mode=AgentRequestMode.STATIC,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
        )
    selected = request.context.selected_live_result_id
    ordinal_selected = _visible_ordinal_result_id(request)
    if selected is None and ordinal_selected is not None:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.SELECTED,
            live_layers=(),
            geography=AgentGeography.SELECTED_RECORD,
            location_label=None,
            static_subrequest=None,
            tool_calls=(_call(AgentTool.GET_OFFICIAL_FIRE, result_id=ordinal_selected),),
        )
    if selected and uses_selected_live_binding(request):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.SELECTED,
            live_layers=(),
            geography=AgentGeography.SELECTED_RECORD,
            location_label=None,
            static_subrequest=None,
            tool_calls=(_call(AgentTool.GET_OFFICIAL_FIRE, result_id=selected),),
        )

    if _UNBOUND_RECORD_REFERENCE.search(question):
        if selected is not None:
            return AgentQueryPlan(
                route=QueryRoute.LIVE,
                mode=AgentRequestMode.SELECTED,
                live_layers=(),
                geography=AgentGeography.SELECTED_RECORD,
                location_label=None,
                static_subrequest=None,
                tool_calls=(_call(AgentTool.GET_OFFICIAL_FIRE, result_id=selected),),
            )
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_record_reference_prompt(),
        )

    if requires_selected_live_record(request):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=_selection_prompt(),
        )

    planning_question = conversation_planning_question(request)
    topics = unsupported_live_topics(planning_question)
    layers = live_layers_for_question(planning_question)
    if (
        not layers
        and is_unresolved_smoke_observation(question)
        and (
            request.location is not None or coarse_location_from_question(question) is not None
        )
    ):
        layers = (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    if (
        not layers
        and _VAGUE_LOCAL_LIVE_CONCERN.search(question)
        and coarse_location_from_question(question) is not None
    ):
        layers = (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    parsed_intent = parse_request_intent(planning_question)
    supported_live_clause = parsed_intent.has_live_records
    if topics and not supported_live_clause:
        layers = ()
    static_query = planned_static_subrequest(planning_question)
    multi_place_comparison = is_multi_place_fire_comparison(request.question)
    if multi_place_comparison and request.location is None:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=layers,
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=static_query,
            tool_calls=(),
            scope_result=AgentScopeResult.REQUIRES_INPUT,
            terminal_response=_multi_place_comparison_limit(request),
        )
    question_location = coarse_location_from_question(request.question)
    explicit_fire_centre = official_fire_centre_from_question(request.question)
    if explicit_fire_centre is not None:
        # An official Fire Centre is an administrative source field, not a
        # community. Preserve it for the exact roster filter and never ask the
        # community geocoder to resolve it.
        location = LocationInput(label=explicit_fire_centre)
    elif is_province_wide_question(request.question):
        # A current, explicit BC-wide ask outranks retained map state.  Decide
        # that before geocoding so a stale unresolved community cannot turn a
        # valid provincial analysis into a location prompt.
        location = None
    elif multi_place_comparison:
        # The continuation control carries the single community the user chose.
        # It must outrank the two place names in the original comparison or the
        # unchanged continuation would loop back into the same terminal plan.
        location = request.location
    elif question_location is not None:
        # A current explicit community also outranks stale retained state.
        location = question_location
    else:
        location = request.location
    if (
        location is None
        and not is_province_wide_question(request.question)
        and (continues_prior_live_place(request) or is_live_refresh_request(request.question))
    ):
        prior = prior_anchor_user_question(request)
        if prior:
            location = coarse_location_from_question(prior)
    if location is None and not is_province_wide_question(request.question):
        location = coarse_location_from_question(planning_question)
    if is_empty_map_safety_inference(planning_question) and location is None:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=layers,
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.REQUIRES_INPUT,
            terminal_response=_empty_map_location_prompt(request),
        )
    named = extracted_located_fire_name(planning_question)
    if named and location is not None and location.label is not None:
        named_key = " ".join(re.sub(r"[^a-z0-9]+", " ", named.casefold()).split())
        place_key = " ".join(re.sub(r"[^a-z0-9]+", " ", location.label.casefold()).split())
        if named_key == place_key or named_key in place_key or place_key in named_key:
            location = None
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
            terminal_response=_scope_redirect(()),
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
                    _scope_redirect(topics) if topics else _unbound_live_redirect()
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
        if location is not None
        and location.label is not None
        and geography == AgentGeography.LOCATION_RADIUS
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
    if official_fire_centre_label(plan.location_label) is not None:
        return plan
    question_location = coarse_location_from_question(request.question)
    if question_location is not None and question_location.label == plan.location_label:
        location = question_location
    elif request.location is not None and request.location.label == plan.location_label:
        location = request.location
    else:
        location = LocationInput(label=plan.location_label)
    try:
        await live_coordinator.live_service.resolve_location(location)
    except LiveDataUnavailable as exc:
        if exc.kind != LiveDataErrorKind.NOT_FOUND:
            return plan
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
