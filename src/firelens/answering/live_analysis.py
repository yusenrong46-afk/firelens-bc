"""Post-fetch official analysis. Luna narrates these facts; it does not invent them."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    CoarseResolvedLocation,
    GeometryRelation,
    LiveResult,
    LiveResultKind,
    QueryRequest,
)
from firelens.freshness_language import (
    aggregate_freshness_from_records,
)
from firelens.freshness_language import (
    official_information_prefix as freshness_prefix,
)
from firelens.live_support import distance_to_geometry_km, geometry_relation

_NEARBY_RADIUS_KM = 50.0

_PLACEHOLDER_NAME = "unnamed official record"
_EXISTENCE = re.compile(
    r"\b(?:is there|are there|does there exist)\b.{0,80}\b(?:called|named)\s+"
    r"[\"']?(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,6})[\"']?",
    re.IGNORECASE,
)
_EVAC_YES_NO = re.compile(
    r"\b(?:is|are)\b.+\bunder\b.+\b(?:order|alert|evacuat)",
    re.IGNORECASE,
)
_TWO_LARGEST = re.compile(
    r"\b(?:two|2)\s+largest\b|\bcompare\b.+\blargest\b|\blargest\b.+\bcompare\b",
    re.IGNORECASE,
)
_OLDEST = re.compile(
    r"\b(?:oldest|start date|started first|ignition date)\b",
    re.IGNORECASE,
)
_COUNT = re.compile(
    r"\bhow many\b.{0,80}\b(?:fires?|wildfires?|fire\s+records?|records?)\b",
    re.IGNORECASE,
)
_FIRE_CENTRE_MOST = re.compile(
    r"\bfire centres?\b.{0,40}\bmost\b|\bmost\b.{0,40}\bfire centres?\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"i(?:'m| am) not sure what you(?:'re| are) referring to",
    re.IGNORECASE,
)
_PRECISE_COORD = re.compile(r"\b-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b")


def official_information_prefix(records: Sequence[LiveResult]) -> str:
    """Honest lead-in: cached-stale records are never called current."""

    return freshness_prefix(aggregate_freshness_from_records(list(records)))


def official_display_name(result: LiveResult) -> str:
    """Prefer a real name, then the fire number, then the result id."""

    name = (result.name or "").strip()
    if name and name.casefold() != _PLACEHOLDER_NAME:
        return name
    number = (result.incident_number or "").strip()
    if number:
        return number
    return result.result_id


def annotate_live_results(
    results: Sequence[LiveResult],
    resolved: CoarseResolvedLocation | None,
) -> list[LiveResult]:
    """Attach WGS84 kilometres and geometry_relation from the resolved place."""

    if resolved is None:
        return list(results)
    annotated: list[LiveResult] = []
    for item in results:
        relation = geometry_relation(
            item.geometry,
            latitude=resolved.latitude,
            longitude=resolved.longitude,
            radius_km=_NEARBY_RADIUS_KM,
        )
        updates: dict[str, object] = {}
        if relation != item.geometry_relation:
            updates["geometry_relation"] = relation
        if item.kind in {LiveResultKind.INCIDENT, LiveResultKind.PERIMETER}:
            distance = distance_to_geometry_km(
                item.geometry,
                latitude=resolved.latitude,
                longitude=resolved.longitude,
            )
            if distance is not None:
                updates["distance_km"] = round(float(distance), 1)
                updates["distance_basis"] = (
                    "incident_point"
                    if item.kind == LiveResultKind.INCIDENT
                    else "perimeter_boundary"
                )
        annotated.append(item.model_copy(update=updates) if updates else item)
    return annotated


def extracted_existence_name(question: str) -> str | None:
    match = _EXISTENCE.search(question)
    if match is None:
        return None
    name = " ".join(match.group("name").split()).strip(" ?.!'\"")
    name = re.sub(
        r"\s+(?:in\s+(?:bc|british columbia)|today|right now|currently)$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return name or None


def record_matches_name(result: LiveResult, queried: str) -> bool:
    needle = queried.casefold()
    haystacks = [
        official_display_name(result).casefold(),
        (result.name or "").casefold(),
        (result.incident_number or "").casefold(),
    ]
    for item in haystacks:
        if not item:
            continue
        if item == needle or needle == item:
            return True
        if needle in item:
            return True
    return False


def official_analysis_answer(
    request: QueryRequest,
    records: Sequence[LiveResult],
    *,
    roster_total: int | None = None,
    static_answer: str | None = None,
) -> str | None:
    """Return a thin post-fetch composer, or None when Luna may narrate the list."""

    lowered = request.question.casefold()
    queried = extracted_existence_name(request.question)
    if queried:
        if any(record_matches_name(item, queried) for item in records):
            matched = next(item for item in records if record_matches_name(item, queried))
            return (
                f"Yes. A fetched official record matches {queried}: "
                f"{official_display_name(matched)}, status {matched.status}."
            )
        return f"No fetched official record is named {queried}."
    if _EVAC_YES_NO.search(request.question):
        return _evac_yes_no(request, records)
    if _OLDEST.search(request.question):
        return (
            "The official records available for this request do not report a "
            "start or ignition date."
        )
    if _TWO_LARGEST.search(request.question):
        return _two_largest(records)
    if _FIRE_CENTRE_MOST.search(request.question):
        return _most_fire_centre(records)
    if (
        "hectare" in lowered
        or "most burned" in lowered
        or ("largest" in lowered and "compare" not in lowered)
    ):
        return _max_hectares(records)
    if "closest" in lowered or "nearest" in lowered or "how close" in lowered:
        return _closest(request, records)
    if "distribution" in lowered or "geography" in lowered:
        return _geography(records)
    if _COUNT.search(request.question):
        return _count(records, roster_total)
    if static_answer and (
        ("alert" in lowered and "order" in lowered)
        or "grab-and-go" in lowered
        or "kit" in lowered
        or "precaution" in lowered
    ):
        return _guidance_with_halves(request.question, static_answer)
    return None


def compose_official_answer(
    request: QueryRequest,
    records: Sequence[LiveResult],
    *,
    roster_total: int | None = None,
    static_answer: str | None = None,
) -> str:
    """Deterministic official sentence used offline and after a rail veto."""

    lowered = request.question.casefold()
    analysis = official_analysis_answer(
        request,
        records,
        roster_total=roster_total,
        static_answer=static_answer,
    )
    if analysis is not None:
        return analysis
    if not records:
        if static_answer:
            return static_answer
        return "The official records available for this request do not report that fact."
    if request.context.selected_live_result_id:
        selected = next(
            (
                item
                for item in records
                if item.result_id == request.context.selected_live_result_id
            ),
            None,
        )
        if selected is None:
            return (
                "Select a mapped fire or perimeter before asking about a specific record. "
                "FireLens will not substitute a different nearby record."
            )
        if (
            "source" in lowered
            or "reported" in lowered
            or "published" in lowered
            or "updated" in lowered
        ):
            return (
                f"Official source for {official_display_name(selected)}: "
                f"{selected.authority}. The official record timestamp is "
                f"{selected.source_updated_at.isoformat()}."
            )
        if "size" in lowered or "hectare" in lowered or "how large" in lowered:
            if selected.size_hectares is None:
                return (
                    f"The official record for {official_display_name(selected)} "
                    "does not provide a size value."
                )
            return (
                f"The official record reports {official_display_name(selected)} at "
                f"{selected.size_hectares:g} hectares."
            )
        return (
            f"{official_display_name(selected)}: {selected.status}. "
            "Open the selected official record for the fields its publishing "
            "authority provides."
        )
    summary = "; ".join(f"{official_display_name(item)}: {item.status}" for item in records[:8])
    return official_information_prefix(records) + summary


def replace_ungrounded_live_hedge(answer: str, replacement: str) -> str:
    if _HEDGE.search(answer):
        return replacement
    return answer


def strip_precise_coordinates(answer: str) -> str:
    """Keep precise WGS84 points off the public answer; the map already has them."""

    return _PRECISE_COORD.sub("the official mapped geometry", answer)


def _max_hectares(records: Sequence[LiveResult]) -> str:
    sized = [item for item in records if item.size_hectares is not None]
    if not sized:
        return "The official records do not report burned hectares for the fetched fires."
    chosen = max(sized, key=lambda item: item.size_hectares or 0.0)
    return (
        f"{official_display_name(chosen)} has the largest official size "
        f"among fetched records at {chosen.size_hectares:g} hectares."
    )


def _two_largest(records: Sequence[LiveResult]) -> str:
    sized = sorted(
        [item for item in records if item.size_hectares is not None],
        key=lambda item: item.size_hectares or 0.0,
        reverse=True,
    )
    if len(sized) < 2:
        return "The official records do not report burned hectares for two fires to compare."
    first, second = sized[0], sized[1]
    return (
        f"{official_display_name(first)} is larger at {first.size_hectares:g} "
        f"hectares. {official_display_name(second)} is next at "
        f"{second.size_hectares:g} hectares among fetched records."
    )


def _closest(request: QueryRequest, records: Sequence[LiveResult]) -> str:
    pool = list(records)
    if "perimeter" in request.question.casefold():
        pool = [item for item in records if item.kind == LiveResultKind.PERIMETER] or pool
    locatable = [item for item in pool if item.distance_km is not None]
    if not locatable:
        return (
            "The official records do not include locatable geometry for a closest-fire answer."
        )
    chosen = min(locatable, key=lambda item: item.distance_km or 0.0)
    basis = (
        "incident point" if chosen.distance_basis == "incident_point" else "perimeter boundary"
    )
    return (
        f"{official_display_name(chosen)} is the closest official record among "
        f"fetched locatable records, {chosen.distance_km:g} km geodesic measured "
        f"to the official {basis}. This is not driving distance or a safety "
        "assessment."
    )


def _most_fire_centre(records: Sequence[LiveResult]) -> str:
    centres = [
        item.fire_centre.strip()
        for item in records
        if item.kind == LiveResultKind.INCIDENT and item.fire_centre
    ]
    if not centres:
        return (
            "The official records do not report a fire-centre field for the fetched incidents."
        )
    name, count = Counter(centres).most_common(1)[0]
    return (
        f"{name} has the most listed incidents among fetched records, with {count}. "
        "This is a record count, not a safety determination."
    )


def _geography(records: Sequence[LiveResult]) -> str:
    if not records:
        return (
            "The official records available for this request do not report "
            "fire-centre geography."
        )
    centres = [item.fire_centre for item in records if item.fire_centre]
    statuses: dict[str, int] = {}
    for item in records:
        statuses[item.status] = statuses.get(item.status, 0) + 1
    status_text = ", ".join(f"{name}={count}" for name, count in statuses.items())
    if centres:
        return (
            "Official fire-centre labels in the fetched records: "
            + ", ".join(sorted(set(centres)))
            + f". Status counts: {status_text}."
        )
    return (
        "The official layer did not provide a fire-centre field. "
        f"Status counts from fetched records: {status_text}."
    )


def _count(records: Sequence[LiveResult], roster_total: int | None) -> str:
    incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in records)
    perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in records)
    shown = len(records)
    if roster_total is not None and roster_total > shown:
        return (
            f"This bounded official response shows {shown} of {roster_total} "
            f"matching official records ({incident_count} incidents and "
            f"{perimeter_count} perimeters on this page). This is a record "
            "count, not a distinct-fire count or a safety determination."
        )
    return (
        f"Official layers return {incident_count} incident records "
        f"and {perimeter_count} perimeter records. This is a record count, not "
        "a distinct-fire count or a safety determination."
    )


def _evac_yes_no(request: QueryRequest, records: Sequence[LiveResult]) -> str:
    location = request.location or coarse_location_from_question(request.question)
    place = location.label if location is not None and location.label else "the requested place"
    covering = [
        item
        for item in records
        if item.kind == LiveResultKind.EVACUATION
        and (
            item.geometry_relation in {GeometryRelation.INSIDE, GeometryRelation.NEARBY}
            or (item.distance_km is not None and item.distance_km <= _NEARBY_RADIUS_KM)
        )
    ]
    if covering:
        names = ", ".join(official_display_name(item) for item in covering[:8])
        return (
            f"Yes. Official fire-related evacuation records near {place} include "
            f"{names}. This is not a stay-or-leave instruction."
        )
    return (
        f"No fetched official fire-related evacuation order or alert covers "
        f"{place} in this bounded response. That is not an all-clear."
    )


def _guidance_with_halves(question: str, static_answer: str) -> str:
    lowered_q = question.casefold()
    lowered_a = static_answer.casefold()
    if "alert" in lowered_q and "order" in lowered_q:
        missing = []
        if "alert" not in lowered_a:
            missing.append("alert")
        if "order" not in lowered_a:
            missing.append("order")
        if missing:
            return (
                static_answer + " The reviewed guidance available for this request does not "
                "define both an evacuation alert and an evacuation order."
            )
    return static_answer
