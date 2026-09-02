"""Execute the fixed official-fetch and RAG tools."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from firelens.agent.budget import tool_fingerprint
from firelens.agent.packet import AgentPacket, live_record_fact
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
)
from firelens.answering.live_analysis import (
    annotate_live_results,
    filter_requested_named_fire_results,
)
from firelens.answering.live_analysis_distance import ranked_live_results_for_request
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.live_record_intent import is_fire_geography_analysis
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_national_scope_question,
    is_out_of_province_label,
    is_province_wide_label,
)
from firelens.answering.static_guidance_subject import static_guidance_retrieval_query
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    CoarseResolvedLocation,
    LiveResultKind,
    LocationInput,
    QueryRequest,
)
from firelens.errors import ToolInputError
from firelens.live import LiveDataErrorKind, LiveDataService, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator
from firelens.live_support import (
    official_fire_centre_label,
    regional_reference_point_limitation,
)

_EXPLICIT_PROVINCE_SCOPE = re.compile(
    r"\b(?:across|throughout|in|of|by|around)\s+"
    r"(?:the\s+)?(?:province|b\s*\.?\s*c\s*\.?|british\s+columbia)\b"
    r"|\b(?:province|b\s*\.?\s*c\s*\.?)\s*[- ]wide\b",
    re.IGNORECASE,
)


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request: QueryRequest,
    live_coordinator: LiveAnswerCoordinator,
    static_service: Any,
    packet: AgentPacket,
) -> str:
    """Run one allowlisted tool and merge facts into the packet."""

    live_service: LiveDataService = live_coordinator.live_service
    plan = packet.query_plan
    if plan is not None and not plan.authorizes(name, arguments):
        packet.policy.refused_tool_calls += 1
        return json.dumps({"error": "tool_call_not_authorized_by_request_plan"})
    fingerprint = tool_fingerprint(name, arguments)
    if not packet.policy.consume_tool_call():
        return json.dumps({"error": "tool_call_budget_exhausted"})
    if fingerprint in packet.tool_fingerprints:
        packet.policy.repeated_tool_dispatch += 1
        return json.dumps({"error": "duplicate_tool_dispatch"})
    packet.tool_fingerprints.append(fingerprint)
    if name == AgentTool.LIST_OFFICIAL_FIRES.value:
        requested_layers = (
            plan.live_layers if plan is not None else live_layers_for_question(request.question)
        )
        fire_layers = tuple(
            layer
            for layer in requested_layers
            if layer in {LiveResultKind.INCIDENT, LiveResultKind.PERIMETER}
        )
        if not fire_layers:
            fire_layers = (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
        results, resolved, roster_total = await _fetch_layers(
            live_service,
            request,
            arguments.get("place_label"),
            fire_layers,
            packet,
        )
        _extend_unique(packet, results)
        if resolved is not None:
            packet.resolved_location = resolved
        if roster_total is not None:
            packet.roster_total = max(packet.roster_total or 0, roster_total)
        packet.tool_names.append(name)
        return json.dumps({"records": [live_record_fact(item) for item in results]})
    if name == AgentTool.GET_OFFICIAL_FIRE.value:
        result_id = str(
            arguments.get("result_id") or request.context.selected_live_result_id or ""
        )
        selected = request.context.selected_live_result_id or result_id
        packet.tool_names.append(name)
        if not selected:
            packet.unknown_topics.append("unbound_selected_record")
            return json.dumps({"records": [], "error": "no_selected_record"})
        existing = [item for item in packet.live_results if item.result_id == selected]
        if existing:
            return json.dumps({"records": [live_record_fact(item) for item in existing]})
        shown, resolved = await _fetch_selected(live_service, request, selected, packet)
        if resolved is not None:
            packet.resolved_location = resolved
        if not shown:
            if not packet.unavailable_layers:
                packet.unknown_topics.append("missing_selected_record")
            return json.dumps({"records": [], "error": "selected_record_not_found"})
        _extend_unique(packet, shown)
        return json.dumps({"records": [live_record_fact(item) for item in shown]})
    if name == AgentTool.LIST_OFFICIAL_EVACUATIONS.value:
        results, resolved, roster_total = await _fetch_layers(
            live_service,
            request,
            arguments.get("place_label"),
            (LiveResultKind.EVACUATION,),
            packet,
        )
        _extend_unique(packet, results)
        if resolved is not None:
            packet.resolved_location = resolved
        if roster_total is not None:
            packet.roster_total = max(packet.roster_total or 0, roster_total)
        packet.tool_names.append(name)
        return json.dumps({"records": [live_record_fact(item) for item in results]})
    if name == AgentTool.SEARCH_REVIEWED_GUIDANCE.value:
        query = str(arguments.get("query") or request.question)
        # Preserve the planner's user-language subrequest for auditability,
        # while giving static RAG its typed subject as the bounded publication
        # question. This lets generic kit guidance and contextual pet follow-
        # ups reach only the material that the reviewed pipeline can admit.
        # The current user turn owns a recognized reviewed-guidance subject.
        # A planner query may narrow an untyped request, but it must not replace
        # a typed current-turn subject with an unrelated concept remembered
        # from conversation history (for example a pet fragment for a general
        # emergency-bag question).
        static_question = (
            static_guidance_retrieval_query(request.question)
            or static_guidance_retrieval_query(query)
            or query
        )
        static_request = QueryRequest(
            question=static_question,
            history=request.history,
            context=request.context,
        )
        response = await static_service.ask(
            static_request,
            allow_live=False,
            prefer_reviewed_quotes=True,
        )
        packet.static_response = response
        packet.tool_names.append(name)
        packet.policy.consume_retrieval_cycle()
        packet.policy.consume_grounded_generation()
        return json.dumps(
            {
                "status": response.status.value,
                "response_mode": response.response_mode.value,
                "answer": response.answer,
                "claim_count": len(response.claims),
            }
        )
    if name == AgentTool.ANSWER_GENERAL_BACKGROUND.value:
        query = str(arguments.get("query") or request.question)
        static_request = QueryRequest(
            question=query,
            history=request.history,
            context=request.context,
        )
        background = getattr(static_service, "_background_answer", None)
        if callable(background):
            response = await background(
                static_request,
                trace_id=uuid4().hex,
                route="related",
                limitations=(BACKGROUND_LIMITATION,),
                observer=None,
            )
        else:
            response = await static_service.ask(
                static_request,
                allow_live=False,
                prefer_reviewed_quotes=False,
            )
        packet.static_response = response
        packet.tool_names.append(name)
        packet.policy.consume_grounded_generation()
        return json.dumps(
            {
                "status": response.status.value,
                "response_mode": response.response_mode.value,
                "answer": response.answer,
                "claim_count": len(response.claims),
            }
        )
    raise ToolInputError()


def _extend_unique(packet: AgentPacket, results: list[Any]) -> None:
    seen = {item.result_id for item in packet.live_results}
    for item in results:
        if item.result_id in seen:
            continue
        packet.live_results.append(item)
        seen.add(item.result_id)


async def _fetch_selected(
    live_service: LiveDataService,
    request: QueryRequest,
    selected: str,
    packet: AgentPacket,
) -> tuple[list[Any], CoarseResolvedLocation | None]:
    kind = selected.partition(":")[0]
    layers = {
        "incident": (LiveResultKind.INCIDENT,),
        "perimeter": (LiveResultKind.PERIMETER,),
        "evacuation": (LiveResultKind.EVACUATION,),
    }.get(kind, (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
    try:
        mapped = await live_service.map_results(layers=layers)
    except LiveDataUnavailable:
        _remember_retrieval(packet, datetime.now(UTC))
        packet.mark_unavailable(layers)
        return [], None
    _record_successful_live_response(packet, mapped)
    shown = [item for item in mapped.results if item.result_id == selected]
    location = request.location or coarse_location_from_question(request.question)
    resolved = await _resolve(live_service, location) if location is not None else None
    return annotate_live_results(shown, resolved), resolved


def _annotation_location(
    request: QueryRequest, location: LocationInput | None
) -> LocationInput | None:
    candidate = location or request.location or coarse_location_from_question(request.question)
    if candidate is not None and is_province_wide_label(candidate.label):
        return None
    return candidate


def _question_explicitly_requests_province_scope(question: str) -> bool:
    """Return whether the user, rather than analysis classification, chose BC scope."""

    return bool(_EXPLICIT_PROVINCE_SCOPE.search(question))


def _first_non_province_location(
    *candidates: LocationInput | None,
) -> LocationInput | None:
    """Return an explicit community or regional label without inventing one."""

    return next(
        (
            candidate
            for candidate in candidates
            if candidate is not None and not is_province_wide_label(candidate.label)
        ),
        None,
    )


async def _fetch_layers(
    live_service: LiveDataService,
    request: QueryRequest,
    place_label: object,
    layers: tuple[LiveResultKind, ...],
    packet: AgentPacket,
) -> tuple[list[Any], CoarseResolvedLocation | None, int | None]:
    if is_national_scope_question(request.question):
        _note_topic(packet, "out_of_province_place")
        return [], None, None
    proposed_label = (
        str(place_label).strip()
        if isinstance(place_label, str) and place_label.strip()
        else None
    )
    question_location = coarse_location_from_question(request.question)
    proposed_location = (
        LocationInput(label=proposed_label)
        if proposed_label is not None and not is_province_wide_label(proposed_label)
        else None
    )
    # An analysis intent (for example, "distribution") is not a geography
    # instruction.  Preserve a concrete question, request, or planned place so
    # regional analytics cannot silently substitute the provincial roster.  An
    # explicit BC/province scope still takes precedence over retained UI state.
    question_requests_province = _question_explicitly_requests_province_scope(
        request.question
    ) or (question_location is not None and is_province_wide_label(question_location.label))
    any_explicit_province = bool(
        question_requests_province
        or (request.location is not None and is_province_wide_label(request.location.label))
        or (proposed_label is not None and is_province_wide_label(proposed_label))
    )
    bound_location = _first_non_province_location(
        question_location,
        request.location,
        proposed_location,
    )
    province_wide = bool(
        question_requests_province
        or (any_explicit_province and bound_location is None)
        or (bound_location is None and is_fire_geography_analysis(request.question))
    )
    if province_wide:
        bound_location = None
    location = None if province_wide else bound_location
    if location is not None and is_out_of_province_label(location.label):
        _note_topic(packet, "out_of_province_place")
        return [], None, None
    fire_centre = official_fire_centre_label(location.label) if location is not None else None
    if location is not None:
        packet.add_live_limitation(regional_reference_point_limitation(location))
    try:
        if location is not None and fire_centre is None:
            page = await live_service.nearby_page(
                location, layers=layers, page=1, page_size=100
            )
            resolved = getattr(page, "resolved_location", None)
            if resolved is None:
                resolved = await _resolve(live_service, location)
            roster_total = getattr(getattr(page, "pagination", None), "total_results", None)
            if roster_total is None:
                roster_total = len(page.results)
            annotated = annotate_live_results(list(page.results), resolved)
            filtered = ranked_live_results_for_request(
                request.question,
                filter_requested_named_fire_results(request, annotated),
            )
            if extracted_located_fire_name(request.question) is not None and not filtered:
                _note_topic(packet, "named_fire_not_found")
            _record_successful_live_response(packet, page)
            return (
                filtered,
                resolved,
                roster_total,
            )
        mapped = await live_service.map_results(layers=layers)
        # A BCWS fire-centre label is an administrative source field, not a
        # geocodable origin.  Do not attach distances from an unrelated place
        # returned by a gazetteer lookup.
        resolved_location = (
            None
            if province_wide or fire_centre is not None
            else _annotation_location(request, None)
        )
        resolved = (
            await _resolve(live_service, resolved_location)
            if resolved_location is not None
            else None
        )
        annotated = annotate_live_results(list(mapped.results), resolved)
        centre_filtered = (
            [
                item
                for item in annotated
                if item.fire_centre is not None
                and item.fire_centre.casefold() == fire_centre.casefold()
            ]
            if fire_centre is not None
            else annotated
        )
        if fire_centre is not None:
            packet.add_live_limitation(
                f"Results are filtered to the official BC Wildfire Service {fire_centre} label."
            )
        filtered = ranked_live_results_for_request(
            request.question,
            filter_requested_named_fire_results(request, centre_filtered),
        )
        if extracted_located_fire_name(request.question) is not None and not filtered:
            _note_topic(packet, "named_fire_not_found")
        _record_successful_live_response(packet, mapped)
        return (
            filtered,
            resolved,
            len(filtered) if fire_centre is not None else len(mapped.results),
        )
    except LiveDataUnavailable as exc:
        _remember_retrieval(packet, datetime.now(UTC))
        if exc.kind == LiveDataErrorKind.NOT_FOUND:
            # The place label did not resolve to a BC community. The layers
            # themselves are healthy, so ask for a usable place instead of
            # reporting an outage.
            _note_topic(packet, "unresolved_place")
            return [], None, None
        packet.mark_unavailable(layers)
        return [], None, None


def _record_successful_live_response(packet: AgentPacket, response: Any) -> None:
    _remember_retrieval(packet, getattr(response, "generated_at", None))
    unavailable = getattr(response, "unavailable_layers", None)
    if unavailable:
        packet.mark_unavailable(unavailable)


def _remember_retrieval(packet: AgentPacket, generated_at: datetime | None) -> None:
    if generated_at is None:
        return
    if packet.retrieved_at is None or generated_at > packet.retrieved_at:
        packet.retrieved_at = generated_at


def _note_topic(packet: AgentPacket, topic: str) -> None:
    if topic not in packet.unknown_topics:
        packet.unknown_topics.append(topic)


async def _resolve(
    live_service: LiveDataService, location: LocationInput
) -> CoarseResolvedLocation | None:
    try:
        latitude, longitude = await live_service.resolve_location(location)
    except LiveDataUnavailable:
        return None
    return CoarseResolvedLocation(latitude=latitude, longitude=longitude)
