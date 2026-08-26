"""Shared deterministic helpers for official live-response construction."""

from __future__ import annotations

from datetime import UTC, datetime
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
from firelens.freshness_language import official_records_headline
from firelens.live_support import OFFICIAL_FALLBACK_URLS
from firelens.proof_presentation import AnswerStatusBanner

_NO_MATCH_LIMITATION = "No matching record is not a safety determination."
_EMPTY_LIVE_LIMITATION = (
    "Empty, no-match, partial, or unavailable official records are not an all-clear."
)


def checked_official_sources_label(
    requested_layers: tuple[LiveResultKind, ...],
    retrieved_at: datetime | None,
) -> str:
    """Name the official layers that were checked and the fetch time when known."""

    names: list[str] = []
    if LiveResultKind.INCIDENT in requested_layers:
        names.append("BC Wildfire Service incidents")
    if LiveResultKind.PERIMETER in requested_layers:
        names.append("perimeters")
    if LiveResultKind.EVACUATION in requested_layers:
        names.append("EmergencyInfoBC evacuations")
    sources = ", ".join(names) if names else "configured official live layers"
    if retrieved_at is None:
        return f"Checked {sources}; fetch time was not retained."
    stamp = retrieved_at.astimezone(UTC).replace(microsecond=0).isoformat()
    return f"Checked {sources} as of {stamp}."


def empty_live_response(
    *,
    requested_layers: tuple[LiveResultKind, ...],
    unavailable_layers: list[LiveResultKind],
    resolved_location: CoarseResolvedLocation | None,
    retrieved_at: datetime | None = None,
) -> AskResponse:
    """Render an empty official lookup without turning absence into an all-clear."""

    unavailable = tuple(dict.fromkeys(unavailable_layers))
    all_unavailable = bool(unavailable and set(requested_layers).issubset(unavailable))
    checked = checked_official_sources_label(requested_layers, retrieved_at)
    if all_unavailable:
        current_information = (
            "The requested official live wildfire layers were unavailable, so FireLens "
            "could not establish current conditions."
        )
        headline = "Official live layers unavailable"
        availability = "Requested official layers were unavailable. That is not an all-clear."
    elif unavailable:
        current_information = (
            "No matching official wildfire records were returned from the available "
            "layers, and some requested official layers were unavailable."
        )
        headline = "No matching official records"
        availability = checked
    else:
        current_information = (
            "No matching official wildfire records were returned for the requested area."
        )
        headline = "No matching official records"
        availability = checked
    current_information += f" {checked}"
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

    mode = (
        ResponseMode.ABSTENTION
        if all_unavailable or resolved_location is None
        else ResponseMode.LIVE
    )
    status = (
        ResponseStatus.ABSTENTION
        if all_unavailable or resolved_location is None
        else ResponseStatus.ANSWER
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
        status_banner=AnswerStatusBanner(
            headline=headline,
            detail=current_information[:500],
            freshness_label="No matching records to classify as current or stale",
            availability_label=availability[:160],
            retrieval_completed_at=retrieved_at,
            official_escalation_title="BC Wildfire Service map",
            official_escalation_url=OFFICIAL_FALLBACK_URLS[0],
        ),
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


def records_section_heading(freshness: AggregateFreshness | None) -> str:
    """One canonical heading for live/mixed record sections."""

    return official_records_headline(freshness)


def unique_limitations(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))
