"""Shared deterministic helpers for official live-response construction."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from firelens.answering.plain_time import human_time, time_ago
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

_NO_MATCH_LIMITATION = "Finding no record is not a safety assessment."
_EMPTY_LIVE_LIMITATION = (
    "An empty, partial, or unavailable official result is not an all-clear."
)

_SOURCE_NAMES = {
    LiveResultKind.INCIDENT: "the BC Wildfire Service fire list",
    LiveResultKind.PERIMETER: "fire perimeters",
    LiveResultKind.EVACUATION: "EmergencyInfoBC evacuation orders and alerts",
}
_NOTHING_LISTED = {
    LiveResultKind.INCIDENT: "fires",
    LiveResultKind.PERIMETER: "fire perimeters",
    LiveResultKind.EVACUATION: "evacuation orders or alerts",
}


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def official_sources_checked(requested_layers: tuple[LiveResultKind, ...]) -> str:
    """ "the BC Wildfire Service fire list and fire perimeters": the sources, by name."""

    names = [_SOURCE_NAMES[kind] for kind in _SOURCE_NAMES if kind in requested_layers]
    return _join(names) or "the official wildfire sources"


def _nothing_listed(requested_layers: tuple[LiveResultKind, ...]) -> str:
    kinds = [kind for kind in _NOTHING_LISTED if kind in requested_layers]
    if LiveResultKind.INCIDENT in kinds and LiveResultKind.PERIMETER in kinds:
        kinds.remove(LiveResultKind.PERIMETER)
    named = [_NOTHING_LISTED[kind] for kind in kinds] or ["records"]
    if len(named) == 1:
        return f"No {named[0]} are listed"
    return f"No {named[0]}, and no {' or '.join(named[1:])}, are listed"


def _checked_when(retrieved_at: datetime | None) -> str:
    if retrieved_at is None:
        return " The time of the check was not recorded."
    return f" FireLens checked {time_ago(retrieved_at)} ({human_time(retrieved_at)})."


def empty_live_response(
    *,
    requested_layers: tuple[LiveResultKind, ...],
    unavailable_layers: list[LiveResultKind],
    resolved_location: CoarseResolvedLocation | None,
    retrieved_at: datetime | None = None,
    place: str | None = None,
) -> AskResponse:
    """Render an empty official lookup without turning absence into an all-clear."""

    unavailable = tuple(dict.fromkeys(unavailable_layers))
    all_unavailable = bool(unavailable and set(requested_layers).issubset(unavailable))
    sources = official_sources_checked(requested_layers)
    where = f" near {place}" if place else ""
    when = _checked_when(retrieved_at)
    if all_unavailable:
        current_information = (
            f"FireLens could not reach {sources} just now, so it cannot say what is "
            f"happening{where}.{when}"
        )
        headline = "Official sources could not be reached"
        availability = "The official sources were unavailable. That is not an all-clear."
    elif unavailable:
        current_information = (
            f"{_nothing_listed(requested_layers)}{where} in the sources FireLens could "
            f"reach, but {official_sources_checked(unavailable)} could not be loaded, so "
            f"this may be incomplete.{when}"
        )
        headline = "No records found; some sources unavailable"
        availability = f"{official_sources_checked(unavailable)} could not be loaded."
    else:
        current_information = (
            f"{_nothing_listed(requested_layers)}{where} right now in {sources}.{when}"
        )
        headline = "No records found"
        availability = f"Checked {sources}."
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
            "The official sources were unavailable, so FireLens does not know whether "
            "records exist.",
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
                heading="What FireLens found",
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
            freshness_label="No records returned",
            availability_label=availability[:160],
            retrieval_completed_at=retrieved_at,
            official_escalation_title="BC Wildfire Service map",
            official_escalation_url=OFFICIAL_FALLBACK_URLS[0],
        ),
    )


def freshness_limitation(state: AggregateFreshness) -> str | None:
    if state == AggregateFreshness.STALE:
        return "These are cached official records; the live refresh failed, so they may be outdated."
    if state == AggregateFreshness.MIXED:
        return "Some of these official records are cached copies from a failed refresh and may be outdated."
    return None


def records_section_heading(freshness: AggregateFreshness | None) -> str:
    """One canonical heading for live/mixed record sections."""

    return official_records_headline(freshness)


def unique_limitations(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))
