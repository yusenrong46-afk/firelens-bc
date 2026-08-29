"""Official handoffs for current information FireLens does not ingest."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from pydantic import HttpUrl

from firelens.contracts import (
    MAX_RELATED_LINKS,
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

_RELATED_LIVE_LINKS = {
    "wildfire records": RelatedLink(
        title="BC Wildfire Service map",
        url=HttpUrl("https://wildfiresituation.nrs.gov.bc.ca/map"),
        description=(
            "Official current wildfire incidents, perimeters, notices, and source updates."
        ),
    ),
    "evacuation information": RelatedLink(
        title="EmergencyInfoBC",
        url=HttpUrl("https://www.emergencyinfobc.gov.bc.ca/"),
        description=(
            "Official provincial emergency information and links to issuing local authorities."
        ),
    ),
    "air quality": RelatedLink(
        title="Current B.C. AQHI",
        url=HttpUrl("https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"),
        description="Environment and Climate Change Canada current AQHI observations and forecasts.",
    ),
    "road conditions": RelatedLink(
        title="DriveBC road conditions",
        url=HttpUrl("https://www.drivebc.ca/"),
        description="Official B.C. road events, closures, delays, cameras, and conditions.",
    ),
    "weather or smoke forecast": RelatedLink(
        title="Environment Canada weather",
        url=HttpUrl("https://weather.gc.ca/"),
        description="Official current conditions, wind, alerts, and forecasts by place.",
    ),
    "firefighting aircraft": RelatedLink(
        title="BC Wildfire Service",
        url=HttpUrl("https://wildfiresituation.nrs.gov.bc.ca/"),
        description="Official wildfire situation, incidents, notices, and response information.",
    ),
}


def merge_related_links(
    *,
    live_handoff_links: Sequence[RelatedLink],
    static_handoff_links: Sequence[RelatedLink],
) -> list[RelatedLink]:
    """Keep both handoff families actionable within the public link contract.

    The first live and static destinations are reserved before remaining slots
    prefer explicit current-information handoffs. URLs, rather than presentation
    labels, define identity.
    """

    selected: list[RelatedLink] = []
    seen_urls: set[str] = set()

    def append_first_unseen(links: Sequence[RelatedLink]) -> None:
        for link in links:
            key = str(link.url)
            if key in seen_urls:
                continue
            selected.append(link)
            seen_urls.add(key)
            return

    def append_remaining(links: Sequence[RelatedLink]) -> None:
        for link in links:
            if len(selected) == MAX_RELATED_LINKS:
                return
            key = str(link.url)
            if key in seen_urls:
                continue
            selected.append(link)
            seen_urls.add(key)

    append_first_unseen(live_handoff_links)
    if len(selected) < MAX_RELATED_LINKS:
        append_first_unseen(static_handoff_links)
    append_remaining(live_handoff_links)
    append_remaining(static_handoff_links)
    return selected[:MAX_RELATED_LINKS]


def related_live_links(topics: tuple[str, ...]) -> list[RelatedLink]:
    """Return bounded official destinations for recognized unsupported topics."""

    return merge_related_links(
        live_handoff_links=[
            _RELATED_LIVE_LINKS[topic] for topic in topics if topic in _RELATED_LIVE_LINKS
        ],
        static_handoff_links=[],
    )


def official_safety_links(*, include_road_conditions: bool = False) -> list[RelatedLink]:
    """Return deterministic official next steps for a blocked safety decision."""

    topics = (
        ("road conditions", "evacuation information")
        if include_road_conditions
        else ("wildfire records", "evacuation information")
    )
    return related_live_links(topics)


def unsupported_live_no_result_response(
    *,
    current_information: str,
    topics: tuple[str, ...],
    links: list[RelatedLink],
    limitations: list[str],
    unavailable_layers: list[LiveResultKind],
    resolved_location: CoarseResolvedLocation | None,
) -> AskResponse:
    """Keep both the no-result warning and official handoff visible."""

    handoff = (
        "FireLens is not connected to an official live source for "
        + ", ".join(topics)
        + ". Open the linked official service for the current value."
    )
    bounded_links = merge_related_links(
        live_handoff_links=links,
        static_handoff_links=[],
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=current_information + "\n\nRelated official information: " + handoff,
        answer_sections=[
            AnswerSection(
                kind=AnswerSectionKind.UNCERTAINTY,
                heading="Current wildfire information",
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
        related_links=bounded_links,
        unavailable_layers=unavailable_layers,
        resolved_location=resolved_location,
    )
