"""Application-owned terminal responses used by internal query planning."""

from __future__ import annotations

import re
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

# This recognizes an individual travel/fuel decision in a wildfire context.
# It deliberately leaves non-personal preparedness questions (for example,
# "what should a go-bag contain?") to the guidance/background lane. Indirect
# first-person asks such as "tell me whether I personally should drive" remain
# personal decisions, rather than general road-status questions.
_PERSONAL_TRAVEL_OR_FUEL_DECISION = re.compile(
    r"\b(?:can|could|should|may)\s+(?:i|we)\s+(?:drive|travel|go)\b.{0,120}"
    r"\b(?:wildfire|fire|evacuat(?:ion|e))\b|"
    r"\b(?:wildfire|fire|evacuat(?:ion|e))\b.{0,120}"
    r"\b(?:can|could|should|may)\s+(?:i|we)\s+(?:drive|travel|go)\b|"
    r"\b(?:whether|if)\b.{0,40}\b(?:i|we|me|us|personally)\b.{0,60}"
    r"\b(?:should|can|could|may|safe)\b.{0,60}\b(?:drive|travel|go)\b.{0,120}"
    r"\b(?:wildfire|fire|evacuat(?:ion|e))\b|"
    r"\b(?:safe)\s+for\s+(?:me|us)\b.{0,60}\b(?:drive|travel|go)\b.{0,120}"
    r"\b(?:wildfire|fire|evacuat(?:ion|e))\b",
    re.IGNORECASE,
)


def is_personal_travel_or_fuel_decision(question: str) -> bool:
    """Return whether a request asks FireLens to make a personal travel decision."""

    return _PERSONAL_TRAVEL_OR_FUEL_DECISION.search(question) is not None


def location_prompt(request: QueryRequest, *, unresolved: bool) -> AskResponse:
    if unresolved:
        answer = (
            "FireLens could not match that place to a British Columbia community. "
            "Enter a BC community name (for example Kelowna or Prince George) or "
            "share an approximate location to continue."
        )
        limitation = (
            "That place did not match a BC community, so no official records were looked up."
        )
    else:
        answer = "FireLens needs a BC community or an approximate location before it can look up the current official records for this."
        limitation = "No official records were looked up because a location is needed first."
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
        answer="No. An empty map does not mean you are safe, and it is not an all-clear. Enter a BC community so FireLens can check the official evacuation orders and alerts for it.",
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


def smoke_observation_location_prompt() -> AskResponse:
    """Request a bounded official lookup without attributing visible smoke."""

    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=(
            "FireLens cannot identify the cause of visible smoke. Enter a BC community "
            "or approximate location and it can check current official wildfire incidents nearby."
        ),
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Enter a BC community or approximate location to check official wildfire incidents.",
            continuation_question="Show current wildfires near my place.",
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[
            "No official incident lookup was run because the visible-smoke location was not provided."
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
        answer="FireLens is not sure which fire you mean. Select it on the map, name it, or name a BC community to look near.",
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No record was looked up because the reference was unclear."],
    )


def selection_prompt() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer="Select a fire on the map or in the list first, or name it, and FireLens will give its size and status. It will not pick one for you.",
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No record was looked up because none was selected."],
    )


def ordinal_out_of_list_prompt(position: str, shown: int) -> AskResponse:
    """The list last shown has no record at the requested position."""

    count = f"{shown} official record{'s' if shown != 1 else ''}"
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            f"The list currently shown has {count}, so there is no {position} one. "
            "Select the record you mean on the map or in the list, or ask for a wider "
            "area. FireLens did not substitute a different record."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[
            "No record was looked up because the list has no record at that position."
        ],
    )


def ordinal_without_list_prompt(position: str) -> AskResponse:
    """An ordinal arrived with a selection but no list to count through."""

    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            f"FireLens does not have the list you are counting through, so it cannot tell "
            f"which record is the {position} one. Ask for current records near a BC "
            "community first, or select the record on the map."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No record was looked up because there is no list to count through."],
    )


def record_reference_prompt() -> AskResponse:
    """Keep an ambiguous roster reference from selecting a record implicitly."""

    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            "FireLens is not sure which record you mean. Select it on the map or in the "
            "list, or name the fire, and it will answer about that one."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=["No record was looked up because the reference was unclear."],
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
            "No official records were looked up because one question named two places to measure from."
        ],
    )


def multiple_fire_centre_clarification(
    request: QueryRequest, centres: tuple[str, ...]
) -> AskResponse:
    labels = [label.removesuffix(" Fire Centre") for label in centres]
    if len(labels) == 2:
        choice = f"{labels[0]} or {labels[1]}"
    else:
        choice = ", ".join(labels[:-1]) + f", or {labels[-1]}"
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=f"Which Fire Centre should I use: {choice}?",
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt=f"Choose one Fire Centre: {choice}.",
            continuation_question=request.question,
        ),
        reason_code=ReasonCode.UNCLEAR_INPUT,
        limitations=[
            "No official records were looked up because the question named more than one Fire Centre."
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
