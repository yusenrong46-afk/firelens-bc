"""Deterministic composition for current official evacuation records."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence

from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import GeometryRelation, LiveResult, LiveResultKind, QueryRequest

_EVACUATION_RECORD_QUERY = re.compile(
    r"\b(?:is|are)\b.{0,100}\bunder\b.{0,100}\b(?:order|alert|evacuat)|"
    r"\b(?:is|are)\s+there\b.{0,100}\b(?:evacuation\s+)?(?:alerts?|orders?)\b|"
    r"\b(?:show|list|find)\b.{0,100}\b(?:evacuation|evac)\b|"
    r"\b(?:evacuation|evac)\s+(?:alerts?|orders?)\b.{0,120}"
    r"\b(?:active|current|near|nearby|around|within|across|throughout|"
    r"right\s+now|today|tonight|in\s+effect)\b",
    re.IGNORECASE,
)
_PROVINCE_SCOPE = re.compile(
    r"\b(?:across|throughout|all\s+of|in)\s+(?:bc|b\.c\.|british\s+columbia|the\s+province)\b|"
    r"\b(?:bc|b\.c\.|british\s+columbia)[- ]wide\b|\bprovince[- ]wide\b",
    re.IGNORECASE,
)


def is_evacuation_record_question(question: str) -> bool:
    """Return whether deterministic current-record wording owns the question."""

    return bool(_EVACUATION_RECORD_QUERY.search(question))


def evacuation_answer(
    request: QueryRequest,
    records: Sequence[LiveResult],
    *,
    display_name: Callable[[LiveResult], str],
    nearby_radius_km: float,
) -> str:
    """Group answer text without changing the fetched evacuation records."""

    location = request.location or coarse_location_from_question(request.question)
    place = location.label if location is not None and location.label else "the requested place"
    lowered = request.question.casefold()
    statuses = {
        status for status in ("order", "alert") if re.search(rf"\b{status}s?\b", lowered)
    }
    status_label = (
        "order"
        if statuses == {"order"}
        else "alert"
        if statuses == {"alert"}
        else "order or alert"
    )
    candidates = [
        item
        for item in records
        if item.kind == LiveResultKind.EVACUATION
        and (not statuses or item.status.casefold() in statuses)
    ]
    province_wide = bool(_PROVINCE_SCOPE.search(request.question))
    if not province_wide:
        candidates = [
            item
            for item in candidates
            if item.geometry_relation in {GeometryRelation.INSIDE, GeometryRelation.NEARBY}
            or (item.distance_km is not None and item.distance_km <= nearby_radius_km)
        ]
    if not candidates:
        if province_wide:
            return (
                "No fetched official fire-related evacuation records matched the "
                "requested status across BC. That is not an all-clear."
            )
        return (
            f"No fetched official fire-related evacuation {status_label} record covers "
            f"{place} in this bounded response. That is not an all-clear."
        )
    groups = Counter(
        (
            display_name(item),
            item.status.strip(),
            (item.issuer or "Issuing authority not named in the record").strip(),
        )
        for item in candidates
    )
    summary = "; ".join(
        f"{name} ({status}; issuer: {issuer}; {count} area record{'s' if count != 1 else ''})"
        for (name, status, issuer), count in list(groups.items())[:8]
    )
    if province_wide:
        bounded = f" Showing 8 of {len(groups)} unique groups." if len(groups) > 8 else ""
        return (
            "Official fire-related evacuation records across BC contain "
            f"{len(groups)} unique name/status/issuer groups across "
            f"{len(candidates)} official area records: {summary}.{bounded} "
            "This is not a stay-or-leave instruction."
        )
    inside = any(item.geometry_relation == GeometryRelation.INSIDE for item in candidates)
    nearby = any(item.geometry_relation == GeometryRelation.NEARBY for item in candidates)
    relation = "inside or nearby" if inside and nearby else "inside" if inside else "nearby"
    return (
        f"Yes. Official fire-related evacuation {status_label} records near {place} "
        f"include {summary}. Their official mapped geometry is classified as {relation} "
        "to the stated coarse place. This is not a stay-or-leave instruction."
    )
