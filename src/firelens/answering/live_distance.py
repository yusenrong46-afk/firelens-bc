"""Deterministic distance responses for selected or nearest wildfire records."""

from __future__ import annotations

import re
from uuid import uuid4

from firelens.answering.live_response_support import (
    freshness_limitation,
    unique_limitations,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    AskResponse,
    CoarseResolvedLocation,
    LiveResultKind,
    QueryRequest,
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
)
from firelens.live import LiveDataService, LiveDataUnavailable
from firelens.live_support import distance_to_geometry_km


def location_request(request: QueryRequest) -> AskResponse:
    """Return the resumable prompt used when a distance needs location input."""

    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=(
            "Share an approximate location or enter a BC community to continue. "
            "FireLens uses it only for this request."
        ),
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Use approximate location or enter a BC community.",
            continuation_question=request.question,
        ),
        selected_live_result_id=request.context.selected_live_result_id,
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[
            "Distance is a straight-line geodesic measurement, not driving distance or a safety assessment."
        ],
    )


async def distance_answer(
    live_service: LiveDataService,
    request: QueryRequest,
) -> AskResponse:
    """Calculate distance without substituting an unrelated mapped record."""

    selected_id = request.context.selected_live_result_id
    if selected_id is None and not re.search(
        r"\b(?:nearest|closest)\b", request.question, re.IGNORECASE
    ):
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=(
                "Select a mapped fire or perimeter before asking for its distance. "
                "FireLens will not substitute a different nearby record."
            ),
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=[
                "FireLens did not substitute the nearest fire for an unbound reference.",
                "No matching record is not a safety determination.",
            ],
        )
    effective_location = request.location or coarse_location_from_question(request.question)
    if effective_location is None:
        return location_request(request)
    distance_layers: tuple[LiveResultKind, ...]
    if selected_id is not None and selected_id.startswith("perimeter:"):
        distance_layers = (LiveResultKind.PERIMETER,)
    elif selected_id is not None and selected_id.startswith("incident:"):
        distance_layers = (LiveResultKind.INCIDENT,)
    elif re.search(r"\bperimeters?\b", request.question, re.IGNORECASE):
        distance_layers = (LiveResultKind.PERIMETER,)
    elif re.search(r"\bincidents?\b", request.question, re.IGNORECASE):
        distance_layers = (LiveResultKind.INCIDENT,)
    else:
        distance_layers = (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    try:
        latitude, longitude = await live_service.resolve_location(effective_location)
        live = await live_service.map_results(layers=distance_layers)
    except LiveDataUnavailable:
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=(
                "The official wildfire layers or BC place lookup are unavailable, so "
                "FireLens cannot calculate a current distance right now."
            ),
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=["Unavailable current data is not a safety determination."],
        )

    measured = []
    for item in live.results:
        if item.kind not in distance_layers:
            continue
        distance = distance_to_geometry_km(
            item.geometry, latitude=latitude, longitude=longitude
        )
        if distance is None:
            continue
        measured.append(
            item.model_copy(
                update={
                    "distance_km": round(distance, 1),
                    "distance_basis": (
                        "incident_point"
                        if item.kind == LiveResultKind.INCIDENT
                        else "perimeter_boundary"
                    ),
                }
            )
        )

    chosen = (
        next((item for item in measured if item.result_id == selected_id), None)
        if selected_id
        else None
    )
    if selected_id and chosen is None:
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=(
                "The selected map record is not an available incident point or fire "
                "perimeter, so FireLens cannot calculate a meaningful fire distance "
                "from it. Select a mapped fire or perimeter and try again."
            ),
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            selected_live_result_id=selected_id,
            limitations=[
                "FireLens did not substitute a different nearby fire.",
                "No matching record is not a safety determination.",
            ],
            unavailable_layers=live.unavailable_layers,
        )
    if chosen is None and measured:
        chosen = min(measured, key=lambda item: item.distance_km or 0.0)
    if chosen is None:
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=(
                "No measurable incident point or fire perimeter was available in the "
                "official layers. Open the related official map source for the latest details."
            ),
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=["No matching record is not a safety determination."],
            unavailable_layers=live.unavailable_layers,
        )

    distance = chosen.distance_km
    assert distance is not None
    basis = (
        "the incident point"
        if chosen.distance_basis == "incident_point"
        else "the nearest mapped perimeter boundary"
    )
    freshness = aggregate_live_freshness([chosen])
    assert freshness is not None
    stale_limitation = freshness_limitation(freshness)
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.LIVE,
        answer=(
            f"{chosen.name or chosen.incident_number or 'The selected wildfire'} is "
            f"approximately {distance:.1f} km away in a straight-line geodesic "
            f"measurement to {basis}."
        ),
        live_results=[chosen],
        aggregate_freshness=freshness,
        selected_live_result_id=chosen.result_id,
        resolved_location=CoarseResolvedLocation(
            latitude=latitude,
            longitude=longitude,
        ),
        limitations=unique_limitations(
            live.limitations,
            [
                "This is not driving distance, travel advice, or a safety assessment.",
                *([stale_limitation] if stale_limitation else []),
            ],
        ),
        unavailable_layers=live.unavailable_layers,
    )
