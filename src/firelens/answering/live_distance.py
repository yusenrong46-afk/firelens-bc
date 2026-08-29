"""Resumable location prompt and app-owned geodesic distance answers."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from firelens.answering.live_analysis import closest_locatable_result, official_display_name
from firelens.contracts import (
    AskResponse,
    LiveResult,
    QueryRequest,
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)


def location_request(request: QueryRequest) -> AskResponse:
    """Return the resumable prompt used when a live ask needs location input."""

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
            "A community label is used only to fetch official records. "
            "This is not driving distance or a safety assessment."
        ],
    )


def distance_answer(request: QueryRequest, records: Sequence[LiveResult]) -> str | None:
    """Compose a geodesic kilometre sentence from packet distances."""

    if not records:
        return (
            "The official records available for this request do not include a "
            "locatable fire or perimeter."
        )
    selected_id = request.context.selected_live_result_id
    chosen: LiveResult | None = None
    if selected_id:
        chosen = next((item for item in records if item.result_id == selected_id), None)
    else:
        chosen = closest_locatable_result(request.question, records)
        if chosen is None:
            return (
                "The official records do not include locatable geometry for a "
                "closest-fire answer."
            )
    if chosen is None or chosen.distance_km is None:
        return "The official record does not include locatable geometry for a distance answer."
    basis = (
        "incident point" if chosen.distance_basis == "incident_point" else "perimeter boundary"
    )
    return (
        f"{official_display_name(chosen)} is {chosen.distance_km:g} km geodesic "
        f"from the requested place, measured to the official {basis}. "
        "This is not driving distance or a safety assessment."
    )
