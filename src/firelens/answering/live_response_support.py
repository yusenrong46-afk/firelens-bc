"""Shared deterministic helpers for official live-response construction."""

from __future__ import annotations

from uuid import uuid4

from firelens.contracts import (
    AggregateFreshness,
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    CoarseResolvedLocation,
    LiveResultKind,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
)
from firelens.live_support import OFFICIAL_FALLBACK_URLS

_NO_MATCH_LIMITATION = "No matching record is not a safety determination."
_EMPTY_LIVE_LIMITATION = (
    "Empty, no-match, partial, or unavailable official records are not an all-clear."
)


def empty_live_response(
    *,
    requested_layers: tuple[LiveResultKind, ...],
    unavailable_layers: list[LiveResultKind],
    resolved_location: CoarseResolvedLocation | None,
) -> AskResponse:
    """Render an empty official lookup without turning absence into an all-clear."""

    unavailable = tuple(dict.fromkeys(unavailable_layers))
    all_unavailable = bool(unavailable and set(requested_layers).issubset(unavailable))
    if all_unavailable:
        current_information = (
            "The requested official live wildfire layers were unavailable, so FireLens "
            "could not establish current conditions."
        )
    elif unavailable:
        current_information = (
            "No matching official wildfire records were returned from the available "
            "layers, and some requested official layers were unavailable."
        )
    else:
        current_information = (
            "No matching official wildfire records were returned for the requested area."
        )
    current_information += " This does not mean the area is safe; it is not an all-clear."

    links = [
        RelatedLink(
            title="BC Wildfire Service map",
            url=OFFICIAL_FALLBACK_URLS[0],
            description=(
                "Official current wildfire incidents, perimeters, notices, and source "
                "updates for British Columbia."
            ),
        )
    ]
    handoff = "Check the BC Wildfire Service map for current incidents and perimeters."
    if LiveResultKind.EVACUATION in requested_layers:
        links.append(
            RelatedLink(
                title="EmergencyInfoBC",
                url=OFFICIAL_FALLBACK_URLS[1],
                description=(
                    "Official provincial emergency information and links to issuing local "
                    "authorities."
                ),
            )
        )
        handoff += (
            " Check EmergencyInfoBC and the issuing local authority for evacuation "
            "orders or alerts."
        )

    mode = ResponseMode.LIVE if resolved_location is not None else ResponseMode.ABSTENTION
    status = (
        ResponseStatus.ANSWER if resolved_location is not None else ResponseStatus.ABSTENTION
    )
    limitations = [_EMPTY_LIVE_LIMITATION]
    if all_unavailable:
        limitations.insert(
            0,
            "Official live sources were unavailable; FireLens did not establish whether "
            "matching records exist.",
        )
    else:
        limitations.insert(0, _NO_MATCH_LIMITATION)
    return AskResponse(
        status=status,
        trace_id=uuid4().hex,
        response_mode=mode,
        answer=current_information + "\n\nRelated official information: " + handoff,
        answer_sections=[
            AnswerSection(
                kind=AnswerSectionKind.UNCERTAINTY,
                heading="What the empty official result means",
                text=current_information,
            ),
            AnswerSection(
                kind=AnswerSectionKind.OFFICIAL_HANDOFF,
                heading="Related official information",
                text=handoff,
            ),
        ],
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=limitations,
        related_links=links,
        unavailable_layers=list(unavailable),
        resolved_location=resolved_location,
    )


def freshness_limitation(state: AggregateFreshness) -> str | None:
    if state == AggregateFreshness.STALE:
        return "Cached official records; refresh failed. These records may be outdated."
    if state == AggregateFreshness.MIXED:
        return (
            "Official records include stale cached data because a refresh failed; "
            "some records may be outdated."
        )
    return None


def unique_limitations(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))
