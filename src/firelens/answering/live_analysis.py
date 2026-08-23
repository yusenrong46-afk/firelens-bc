"""Post-fetch official analysis. Luna narrates these facts; it does not invent them."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from firelens.answering.live_record_intent import is_fire_geography_analysis
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
_LOCATED_NAMED_FIRE = re.compile(
    r"\bwhere(?:\s+is|['’]s)\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,5}?)\s+"
    r"(?:fire|wildfire)\s+(?:near|around|by|in|within)\b",
    re.IGNORECASE,
)
_GENERIC_LOCATED_NAMES = frozenset(
    {"a", "active", "any", "closest", "current", "local", "nearest", "the"}
)


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


def extracted_located_fire_name(question: str) -> str | None:
    """Extract a specifically named fire from a where-in-place question."""

    match = _LOCATED_NAMED_FIRE.search(question)
    if match is None:
        return None
    base = " ".join(match.group("name").split()).strip(" ?.!'\"")
    if not base or base.casefold().split()[0] in _GENERIC_LOCATED_NAMES:
        return None
    return f"{base} Fire"


def _normalized_record_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _is_single_typo(first: str, second: str) -> bool:
    """Accept one edit or adjacent transposition, never general fuzzy similarity."""

    if first == second or abs(len(first) - len(second)) > 1 or min(len(first), len(second)) < 6:
        return False
    if len(first) == len(second):
        different = [
            index
            for index, pair in enumerate(zip(first, second, strict=True))
            if pair[0] != pair[1]
        ]
        if len(different) == 1:
            return True
        return bool(
            len(different) == 2
            and different[1] == different[0] + 1
            and first[different[0]] == second[different[1]]
            and first[different[1]] == second[different[0]]
        )
    shorter, longer = (first, second) if len(first) < len(second) else (second, first)
    for index in range(len(longer)):
        if longer[:index] + longer[index + 1 :] == shorter:
            return True
    return False


def filter_requested_named_fire_results(
    request: QueryRequest, records: Sequence[LiveResult]
) -> list[LiveResult]:
    """Keep unrelated nearby records out of a specifically named-fire response."""

    queried = extracted_located_fire_name(request.question)
    if queried is None:
        return list(records)
    normalized_query = _normalized_record_name(queried)
    query_variants = {
        normalized_query,
        normalized_query.removesuffix(" fire").removesuffix(" wildfire"),
    }
    exact = [
        item
        for item in records
        if _normalized_record_name(official_display_name(item)) in query_variants
    ]
    if exact:
        return exact
    typo_matches = [
        item
        for item in records
        if any(
            _is_single_typo(_normalized_record_name(official_display_name(item)), variant)
            for variant in query_variants
            if variant
        )
    ]
    matched_names = {
        _normalized_record_name(official_display_name(item)) for item in typo_matches
    }
    return typo_matches if len(matched_names) == 1 else []


def official_analysis_answer(
    request: QueryRequest,
    records: Sequence[LiveResult],
    *,
    roster_total: int | None = None,
    static_answer: str | None = None,
) -> str | None:
    """Return a thin post-fetch composer, or None when Luna may narrate the list."""

    lowered = request.question.casefold()
    located_name = extracted_located_fire_name(request.question)
    if located_name is not None:
        if not records:
            return f"No fetched official record matched the named fire {located_name}."
        matched = records[0]
        distance = (
            f" It is {matched.distance_km:g} km geodesic from the stated community "
            f"to the official {matched.distance_basis.replace('_', ' ')}."
            if matched.distance_km is not None and matched.distance_basis is not None
            else ""
        )
        return (
            f"The fetched official records match {official_display_name(matched)}, "
            f"status {matched.status}.{distance}"
        )
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
    if is_fire_geography_analysis(request.question):
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
    counts = Counter(centres)
    count = max(counts.values())
    leaders = sorted(
        (name for name, candidate_count in counts.items() if candidate_count == count),
        key=str.casefold,
    )
    if len(leaders) > 1:
        return (
            f"{', '.join(leaders)} are tied for the most listed incidents among "
            f"fetched records, with {count} each. This is a record count, not a "
            "safety determination."
        )
    name = leaders[0]
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
    incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT]
    if not incidents:
        return "The fetched official records do not include incident geography."
    centres = Counter(
        item.fire_centre.strip()
        for item in incidents
        if item.fire_centre and item.fire_centre.strip()
    )
    statuses = Counter(item.status for item in incidents)
    status_text = ", ".join(
        f"{name}={count}" for name, count in sorted(statuses.items(), key=lambda row: row[0])
    )
    if centres:
        ordered = sorted(centres.items(), key=lambda row: (-row[1], row[0].casefold()))
        centre_text = ", ".join(f"{name}={count}" for name, count in ordered)
        highest = ordered[0][1]
        leaders = ", ".join(name for name, count in ordered if count == highest)
        missing_centre_count = len(incidents) - sum(centres.values())
        missing_note = (
            f" {missing_centre_count} fetched incident records were omitted from the "
            "fire-centre breakdown because the official centre label was unavailable."
            if missing_centre_count
            else ""
        )
        return (
            "Official incident counts by fire-centre label among fetched records: "
            f"{centre_text}. Highest count in this bounded result: {leaders}={highest}. "
            f"Status counts across the same incident records: {status_text}."
            f"{missing_note}"
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
