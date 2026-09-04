"""Immutable internal execution plan for one public agent request."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

import firelens.agent.query_plan_boundaries as boundary
from firelens.agent.fallback_brain import planned_static_subrequest, planned_static_tool
from firelens.agent.tools import AgentTool
from firelens.answering.clause_boundaries import clause_boundaries, wants_evacuation_records
from firelens.answering.intent import (
    continues_prior_live_place,
    conversation_planning_question,
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    prefers_general_background,
    prior_anchor_user_question,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_conversation import is_selected_record_followup
from firelens.answering.intent_patterns import is_unresolved_smoke_observation
from firelens.answering.intent_refresh import is_live_refresh_request
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_named_fire import (
    extracted_located_fire_name,
    requested_fire_identity,
)
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
    place_mention_for_question,
)
from firelens.answering.unsupported_live import (
    has_independent_supported_live_clause,
    unsupported_live_topics,
)
from firelens.contracts import (
    AnswerSection,
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
    official_fire_centres_from_question,
)
from firelens.understanding.place import PlaceKind
from firelens.understanding.reference import ordinal_label, ordinal_reference


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
    # Clauses answered by saying what FireLens will not or cannot do; the
    # composer adds each as its own section so no clause is dropped.
    boundaries: tuple[AnswerSection, ...] = ()
    # The fire the person named, in their words ("Phantom Ridge", "K51402").
    asked_fire_name: str | None = None

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

    @property
    def selected_result_id(self) -> str | None:
        """The exact record a SELECTED plan is about; the request context mirrors it."""

        if self.mode != AgentRequestMode.SELECTED:
            return None
        for call in self.tool_calls:
            if call.name == AgentTool.GET_OFFICIAL_FIRE:
                return call.as_arguments().get("result_id")
        return None

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
            "boundaries": [section.kind.value for section in self.boundaries],
        }


def _call(name: AgentTool, **arguments: str) -> PlannedToolCall:
    return PlannedToolCall(name=name, arguments=tuple(sorted(arguments.items())))


def _static_call(question: str, static_query: str) -> PlannedToolCall:
    tool = planned_static_tool(question) or AgentTool.SEARCH_REVIEWED_GUIDANCE
    return _call(tool, query=static_query)


def _selected_record_plan(result_id: str) -> AgentQueryPlan:
    return AgentQueryPlan(
        route=QueryRoute.LIVE,
        mode=AgentRequestMode.SELECTED,
        live_layers=(),
        geography=AgentGeography.SELECTED_RECORD,
        location_label=None,
        static_subrequest=None,
        tool_calls=(_call(AgentTool.GET_OFFICIAL_FIRE, result_id=result_id),),
    )


def _terminal_plan(response: AskResponse) -> AgentQueryPlan:
    return AgentQueryPlan(
        route=QueryRoute.LIVE,
        mode=AgentRequestMode.TERMINAL,
        live_layers=(),
        geography=AgentGeography.NONE,
        location_label=None,
        static_subrequest=None,
        tool_calls=(),
        scope_result=AgentScopeResult.SCOPE_REDIRECT,
        terminal_response=response,
    )


def _ordinal_plan(request: QueryRequest) -> AgentQueryPlan | None:
    """ "The second one" counts through the list the person is looking at.

    The client sends that list as `visible_live_result_ids`, in display order.
    A position inside it binds that exact record, even when another record is
    selected; a position outside it, or an ordinal with a selection but no list,
    gets an explicit clarification. Without a list or a selection the planner
    falls through to the conversation-history path.
    """

    index = ordinal_reference(request.question)
    if index is None:
        return None
    visible = request.context.visible_live_result_ids
    if visible:
        if index < len(visible):
            return _selected_record_plan(visible[index])
        return _terminal_plan(
            boundary.ordinal_out_of_list_prompt(ordinal_label(index), len(visible))
        )
    if request.context.selected_live_result_id:
        return _terminal_plan(boundary.ordinal_without_list_prompt(ordinal_label(index)))
    return None


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
    """Create the deterministic plan projection before external place resolution.

    Clauses the plan declines or cannot serve travel with it as boundaries. A
    declined evacuation decision beside a located records clause also fetches
    the official evacuation records for that place: the fact the person can
    have, next to the decision they must make with the issuing authority.
    """

    plan = _plan_request_body(request)
    if plan.mode == AgentRequestMode.TERMINAL:
        return plan
    plan = replace(plan, asked_fire_name=requested_fire_identity(request))
    boundaries = clause_boundaries(conversation_planning_question(request))
    if not boundaries:
        return plan
    layers = plan.live_layers
    calls = plan.tool_calls
    if (
        wants_evacuation_records(boundaries)
        and plan.geography == AgentGeography.LOCATION_RADIUS
        and LiveResultKind.EVACUATION not in layers
    ):
        layers = (*layers, LiveResultKind.EVACUATION)
        calls = (
            *calls,
            *_live_calls(
                (LiveResultKind.EVACUATION,),
                geography=plan.geography,
                location_label=plan.location_label,
            ),
        )
    return replace(plan, live_layers=layers, tool_calls=calls, boundaries=boundaries)


def _plan_request_body(request: QueryRequest) -> AgentQueryPlan:
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
            terminal_response=boundary.absence_all_clear_boundary(),
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
            terminal_response=boundary.evacuation_alert_distance_boundary(),
        )
    if boundary.is_personal_travel_or_fuel_decision(question):
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=(),
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=None,
            tool_calls=(),
            scope_result=AgentScopeResult.SCOPE_REDIRECT,
            terminal_response=boundary.travel_or_fuel_boundary(),
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
            terminal_response=boundary.smoke_observation_location_prompt(),
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
    ordinal_plan = _ordinal_plan(request)
    if ordinal_plan is not None:
        return ordinal_plan
    if selected and uses_selected_live_binding(request):
        return _selected_record_plan(selected)
    if selected is None and is_selected_record_followup(request.question):
        prior = prior_anchor_user_question(request)
        prior_layers = live_layers_for_question(prior) if prior else ()
        prior_location = coarse_location_from_question(prior) if prior else None
        if prior_layers:
            geography = (
                AgentGeography.LOCATION_RADIUS
                if prior_location is not None
                and prior_location.label is not None
                and not is_province_wide_label(prior_location.label)
                else AgentGeography.PROVINCE_WIDE
            )
            location_label = (
                prior_location.label
                if prior_location is not None and geography == AgentGeography.LOCATION_RADIUS
                else None
            )
            return AgentQueryPlan(
                route=QueryRoute.LIVE,
                mode=AgentRequestMode.LIVE,
                live_layers=prior_layers,
                geography=geography,
                location_label=location_label,
                static_subrequest=None,
                tool_calls=tuple(
                    _live_calls(
                        prior_layers,
                        geography=geography,
                        location_label=location_label,
                    )
                ),
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
            terminal_response=boundary.record_reference_prompt(),
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
            terminal_response=boundary.selection_prompt(),
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
    if topics and not has_independent_supported_live_clause(planning_question):
        layers = ()
    static_query = planned_static_subrequest(planning_question)
    multi_place_comparison = (
        is_multi_place_fire_comparison(request.question)
        and not parsed_intent.requests_non_bc_scope  # "from Atlantic to Pacific" is scope
    )
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
            terminal_response=boundary.multi_place_comparison_limit(request),
        )
    question_location = coarse_location_from_question(request.question)
    named_fire_centres = official_fire_centres_from_question(request.question)
    if len(named_fire_centres) > 1 and request.location is None:
        return AgentQueryPlan(
            route=QueryRoute.LIVE,
            mode=AgentRequestMode.TERMINAL,
            live_layers=layers,
            geography=AgentGeography.NONE,
            location_label=None,
            static_subrequest=static_query,
            tool_calls=(),
            scope_result=AgentScopeResult.REQUIRES_INPUT,
            terminal_response=boundary.multiple_fire_centre_clarification(
                request, named_fire_centres
            ),
        )
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
            terminal_response=boundary.empty_map_location_prompt(request),
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
    question_place = place_mention_for_question(request.question)
    outside_bc_scope = bool(
        parsed_intent.requests_non_bc_scope
        or (location is not None and is_out_of_province_label(location.label))
        or (
            question_location is None
            and question_place is not None
            and question_place.kind == PlaceKind.OUT_OF_PROVINCE
        )
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
            terminal_response=boundary.scope_redirect(()),
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
                tool_calls=(_static_call(planning_question, static_query),),
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
                    boundary.scope_redirect(topics)
                    if topics
                    else boundary.unbound_live_redirect()
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
                (_static_call(planning_question, static_query),)
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
            terminal_response=boundary.location_prompt(request, unresolved=False),
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
        calls.append(_static_call(planning_question, static_query))
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
        terminal_response=boundary.location_prompt(request, unresolved=True),
    )
