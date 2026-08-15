"""Deterministic recognition and rendering for live-record follow-up requests."""

from __future__ import annotations

import re
from collections.abc import Sequence

from firelens.contracts import AggregateFreshness, LiveResult, LiveResultKind, QueryRequest

_DISTANCE_PATTERN = re.compile(
    r"\b(?:how far|how close|distance|kilomet(?:er|re)s?|miles?)\b", re.IGNORECASE
)
_SELECTED_ENTITY_PATTERN = re.compile(
    r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|perimeter|record)\b",
    re.IGNORECASE,
)
_SELECTED_ATTRIBUTE_PATTERN = re.compile(
    r"\b(?:status|happening|details?|size|large|big|hectares?|source|publisher|dataset|"
    r"updated|updates?|update time|update timestamp)\b",
    re.IGNORECASE,
)
_SELECTED_UNSUPPORTED_PATTERN = re.compile(
    r"\b(?:why|cause|caused|start(?:ed)?|ignition|will|predict(?:ed|ion)?|forecast|"
    r"reach|arrive|spread to|contained?|controlled?|go out)\b",
    re.IGNORECASE,
)
_SELECTED_PRONOUN_UNSUPPORTED_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:when|why)\s+did\s+it\s+start|"
    r"what\s+caused\s+it|"
    r"when\s+will\s+it\s+(?:reach|arrive|spread|be\s+contained|"
    r"be\s+controlled|go\s+out)\b.*|"
    r"will\s+it\s+(?:reach|arrive|spread|be\s+contained|be\s+controlled|"
    r"go\s+out)\b.*|"
    r"is\s+it\s+going\s+to\s+(?:reach|arrive|spread)\b.*"
    r")[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_LIVE_ELLIPTICAL = re.compile(
    r"^\s*(?:"
    r"(?:what|which)\s+(?:source|publisher|dataset)\s+(?:reported|published)\s+it|"
    r"who\s+(?:reported|published)\s+it|"
    r"what(?:'s|\s+is)\s+its\s+(?:status|size|source)|"
    r"how\s+(?:large|big)\s+is\s+it|"
    r"when\s+was\s+it\s+updated|"
    r"(?:what|any)\s+updates?(?:\s+on\s+it)?"
    r")[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_DISTANCE_ELLIPTICAL = re.compile(
    r"^\s*(?:how\s+(?:far|close)(?:\s+away)?\s+is\s+it"
    r"(?:\s+(?:from|to)\s+[a-z][a-z .'-]{1,80})?|"
    r"(?:what(?:'s|\s+is)\s+(?:the\s+)?)?distance\s+from\s+"
    r"[a-z][a-z .'-]{1,80}?\s+to\s+it)[?!.]*\s*$",
    re.IGNORECASE,
)
_SOURCE_PATTERN = re.compile(
    r"\b(?:what|which|who|where).{0,30}\b(?:source|reported|published|dataset)\b|"
    r"\b(?:source|publisher|dataset)\b",
    re.IGNORECASE,
)
_UPDATED_PATTERN = re.compile(
    r"\b(?:when\s+(?:was|is)\b.{0,100}\bupdated|"
    r"last updated|source updated|record updated|update time|update timestamp)\b",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(r"\b(?:how (?:large|big)|size|hectares?|ha)\b", re.I)
_COUNT_PATTERN = re.compile(
    r"\bhow many\b.{0,60}\b(?:fires?|wildfires?)(?:\s+records?)?\b",
    re.IGNORECASE,
)


def is_distance_request(request: QueryRequest) -> bool:
    """Recognize distance requests with an explicit or selected wildfire target."""

    if not _DISTANCE_PATTERN.search(request.question):
        return False
    explicit_fire = re.search(
        r"\b(?:fire|wildfire|incident|perimeter)\b",
        request.question,
        re.IGNORECASE,
    )
    return bool(
        explicit_fire
        or (
            request.context.selected_live_result_id
            and _SELECTED_DISTANCE_ELLIPTICAL.match(request.question)
        )
    )


def is_selected_live_request(request: QueryRequest) -> bool:
    """Recognize supported attribute questions about the selected live record."""

    return bool(
        request.context.selected_live_result_id
        and (
            (
                _SELECTED_ENTITY_PATTERN.search(request.question)
                and _SELECTED_ATTRIBUTE_PATTERN.search(request.question)
                and not _SELECTED_UNSUPPORTED_PATTERN.search(request.question)
            )
            or _SELECTED_LIVE_ELLIPTICAL.match(request.question)
        )
    )


def is_unsupported_selected_request(request: QueryRequest) -> bool:
    """Recognize selected-record asks unavailable official fields cannot answer."""

    return bool(
        request.context.selected_live_result_id
        and (
            (
                _SELECTED_ENTITY_PATTERN.search(request.question)
                and _SELECTED_UNSUPPORTED_PATTERN.search(request.question)
            )
            or _SELECTED_PRONOUN_UNSUPPORTED_PATTERN.match(request.question)
        )
    )


def render_live_record_answer(
    request: QueryRequest,
    shown: Sequence[LiveResult],
    aggregate_freshness: AggregateFreshness,
) -> str:
    """Render the same bounded summary or selected-record attribute deterministically."""

    selected_request = is_selected_live_request(request)
    summary = "; ".join(
        f"{item.name or item.incident_number or item.result_id}: {item.status}"
        for item in shown[:5]
    )
    if selected_request and _UPDATED_PATTERN.search(request.question):
        selected = shown[0]
        display_name = selected.name or selected.incident_number or "The selected record"
        return (
            f"The official source record for {display_name} was updated at "
            f"{selected.source_updated_at.isoformat()}."
            if selected.source_updated_at is not None
            else f"The official source record for {display_name} does not provide an update timestamp."
        )
    if selected_request and _SOURCE_PATTERN.search(request.question):
        selected = shown[0]
        display_name = selected.name or selected.incident_number or "The selected record"
        return (
            f"Official source for {display_name}: {selected.authority}. "
            "Open the linked official record for its source data and latest timestamp."
        )
    if selected_request and _SIZE_PATTERN.search(request.question):
        selected = shown[0]
        display_name = selected.name or selected.incident_number or "The selected record"
        return (
            f"The official record reports {display_name} at "
            f"{selected.size_hectares:g} hectares."
            if selected.size_hectares is not None
            else f"The official record for {display_name} does not provide a size value."
        )
    if _COUNT_PATTERN.search(request.question):
        incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in shown)
        perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in shown)
        return (
            f"This bounded official response contains {incident_count} incident records"
            f" and {perimeter_count} perimeter records. This is a record count, not a "
            "distinct-fire count or a safety determination."
        )
    if aggregate_freshness == AggregateFreshness.STALE:
        return "Cached official information (refresh failed): " + summary
    if aggregate_freshness == AggregateFreshness.MIXED:
        return "Official information (includes stale cached records): " + summary
    return "Current official information: " + summary
