"""Execute the fixed official-fetch and RAG tools."""

from __future__ import annotations

import json
from typing import Any

from firelens.agent.packet import AgentPacket, live_record_fact
from firelens.agent.tools import AgentTool
from firelens.answering.intent import (
    live_layers_for_question,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.answering.live_analysis import annotate_live_results
from firelens.answering.location_intent import (
    coarse_location_from_question,
    is_province_wide_label,
)
from firelens.contracts import (
    CoarseResolvedLocation,
    LiveResultKind,
    LocationInput,
    QueryRequest,
)
from firelens.live import LiveDataService, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator


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
    if name == AgentTool.LIST_OFFICIAL_FIRES.value:
        results, resolved, roster_total = await _fetch_layers(
            live_service,
            request,
            arguments.get("place_label"),
            (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
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
        if live_layers_for_question(query) or unsupported_live_topics(query):
            query = static_guidance_fragment(query) or query
        static_request = QueryRequest(
            question=query,
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
        return json.dumps(
            {
                "status": response.status.value,
                "response_mode": response.response_mode.value,
                "answer": response.answer,
                "claim_count": len(response.claims),
            }
        )
    raise ValueError(f"tool is not allowlisted: {name}")


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
        packet.mark_unavailable(layers)
        return [], None
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


async def _fetch_layers(
    live_service: LiveDataService,
    request: QueryRequest,
    place_label: object,
    layers: tuple[LiveResultKind, ...],
    packet: AgentPacket,
) -> tuple[list[Any], CoarseResolvedLocation | None, int | None]:
    label = (
        str(place_label).strip()
        if isinstance(place_label, str) and place_label.strip()
        else None
    )
    province_wide = is_province_wide_label(label)
    if province_wide:
        label = None
    location = None if province_wide else request.location
    if label:
        try:
            location = LocationInput(label=label)
        except ValueError:
            location = coarse_location_from_question(f"near {label}")
    if location is None and not province_wide:
        location = coarse_location_from_question(request.question)
    try:
        if location is not None:
            page = await live_service.nearby_page(
                location, layers=layers, page=1, page_size=100
            )
            resolved = getattr(page, "resolved_location", None)
            if resolved is None:
                resolved = await _resolve(live_service, location)
            roster_total = getattr(getattr(page, "pagination", None), "total_results", None)
            if roster_total is None:
                roster_total = len(page.results)
            return annotate_live_results(list(page.results), resolved), resolved, roster_total
        mapped = await live_service.map_results(layers=layers)
        resolved_location = _annotation_location(request, None)
        resolved = (
            await _resolve(live_service, resolved_location)
            if resolved_location is not None
            else None
        )
        return (
            annotate_live_results(list(mapped.results), resolved),
            resolved,
            len(mapped.results),
        )
    except LiveDataUnavailable:
        packet.mark_unavailable(layers)
        return [], None, None


async def _resolve(
    live_service: LiveDataService, location: LocationInput
) -> CoarseResolvedLocation | None:
    try:
        latitude, longitude = await live_service.resolve_location(location)
    except (LiveDataUnavailable, AttributeError, TypeError, ValueError):
        return None
    return CoarseResolvedLocation(latitude=latitude, longitude=longitude)
