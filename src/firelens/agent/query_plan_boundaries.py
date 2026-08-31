"""Application-owned terminal responses used by internal query planning."""

from __future__ import annotations

from uuid import uuid4

from firelens.answering.live_handoffs import official_safety_links, related_live_links
from firelens.contracts import (
    AskResponse,
    QueryRequest,
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)


def location_prompt(request: QueryRequest, *, unresolved: bool) -> AskResponse:
    if unresolved:
        answer = (
            "FireLens could not match that place to a British Columbia community. "
            "Enter a BC community name (for example Kelowna or Prince George) or "
            "share an approximate location to continue."
        )
        limitation = "The place label did not resolve to a BC community, so no official records were fetched."
    else:
        answer = "A BC community or approximate location is needed before FireLens can look up current official records for this request."
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


def empty_map_location_prompt(request: QueryRequest) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer="No. No evacuation orders shown on a map does not mean you are safe, and it is not an all-clear. Enter a BC community so FireLens can check bounded official evacuation records.",
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Enter a BC community FireLens can check for official evacuation records.",
            continuation_question="Show current evacuation alerts and orders near my place.",
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        related_links=official_safety_links(),
        limitations=[
            "An empty or filtered map view is not an all-clear and cannot establish safety."
        ],
    )


def scope_redirect(topics: tuple[str, ...]) -> AskResponse:
    if topics:
        answer = f"FireLens is not connected to an official live source for {', '.join(topics)}. Open the related official service for the current value."
        limitations = ["FireLens did not substitute unrelated wildfire records."]
    else:
        answer = "FireLens reads official British Columbia wildfire sources only. Use the relevant jurisdiction's official wildfire or emergency service for current records."
        limitations = ["FireLens covers official British Columbia layers only."]
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=answer,
        reason_code=ReasonCode.SCOPE_REDIRECT,
        related_links=related_live_links(topics),
        limitations=limitations,
    )


def unbound_live_redirect() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer="Select a mapped official record or name a British Columbia community before asking about that current fire. FireLens did not substitute a record.",
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No current record was fetched for an unbound reference."],
    )


def selection_prompt() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer="Select a mapped official record before asking for one record's size or status. FireLens will not choose a nearby record for you.",
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No official record was fetched because no exact record was selected."],
    )


def multi_place_comparison_limit(request: QueryRequest) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer="FireLens cannot yet compare distances from two communities in one lookup. Ask for the closest current fire to one BC community, then ask the same question for the other; FireLens will keep the two distance origins separate.",
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Choose the first BC community to check.",
            continuation_question=request.question,
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[
            "No official records were fetched because one request cannot bind two distance origins."
        ],
    )


def absence_all_clear_boundary() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer="No. An apparent absence of fires within a radius does not establish that there is nothing to worry about or that an area is all-clear. Check official alerts and follow instructions from the issuing authority.",
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        related_links=official_safety_links(),
        limitations=[
            "No official location-bound lookup was run, and absence is not a safety determination."
        ],
    )


def travel_or_fuel_boundary() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer="FireLens cannot decide whether you should drive for fuel during a wildfire. Follow any evacuation alert or order from its issuing authority, and check DriveBC for current road conditions before travel.",
        reason_code=ReasonCode.PERSONALIZED_SAFETY_DECISION,
        related_links=official_safety_links(include_road_conditions=True),
        limitations=["FireLens did not make a personal travel or safety decision."],
    )


def evacuation_alert_distance_boundary() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer="No. Do not ignore an evacuation alert because a fire appears far away. Follow the direction from the authority that issued the alert and check EmergencyInfoBC for the official notice.",
        reason_code=ReasonCode.PERSONALIZED_SAFETY_DECISION,
        related_links=official_safety_links(),
        limitations=["FireLens did not make a personal evacuation decision."],
    )
