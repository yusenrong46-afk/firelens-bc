"""Post-fetch official analysis. Luna narrates these facts; it does not invent them."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from firelens import freshness_language
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_evacuation import (
    evacuation_answer,
    is_evacuation_record_question,
)
from firelens.answering.live_record_intent import is_fire_geography_analysis
from firelens.answering.location_intent import directional_bc_region_label
from firelens.contracts import (
    CoarseResolvedLocation,
    LiveResult,
    LiveResultKind,
    QueryRequest,
)
from firelens.live_support import (
    annotated_distance_fields,
    geometry_relation,
)

_NEARBY_RADIUS_KM = 50.0

_PLACEHOLDER_NAME = "unnamed official record"
_EXISTENCE = re.compile(
    r"\b(?:is there|are there|does there exist)\b.{0,80}\b(?:called|named)\s+"
    r"[\"']?(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,6})[\"']?",
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
_NORTH_SOUTH_COMPARISON = re.compile(
    r"\bnorthern?\b.{0,120}\bsouthern?\b|\bsouthern?\b.{0,120}\bnorthern?\b",
    re.IGNORECASE,
)
_LATITUDE_DENSITY = re.compile(
    r"\blatitude\b.{0,80}\b(?:bands?|density)\b|"
    r"\b(?:bands?|density)\b.{0,80}\blatitude\b",
    re.IGNORECASE,
)
_GENERIC_DENSITY = re.compile(r"\bdensity\b", re.IGNORECASE)
_OKANAGAN_KOOTENAYS_COMPARISON = re.compile(
    r"\bokanagan\b.{0,120}\bkootenays?\b|"
    r"\bkootenays?\b.{0,120}\bokanagan\b",
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
_PREFIXED_NAMED_FIRE = re.compile(
    r"\bwhere(?:\s+is|['’]s)\s+(?:the\s+)?(?:fire|wildfire|incident)\s+"
    r"(?P<name>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,5}?)"
    r"(?=\s+(?:right\s+now|today|tonight|currently|now)\b|[?!.]|$)",
    re.IGNORECASE,
)
_BCWS_INCIDENT_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?P<number>[A-Za-z]\d{4,6})(?![A-Za-z0-9])"
)
_FIRE_FOLLOW_UP = re.compile(
    r"\b(?:it|its|that\s+(?:fire|wildfire|incident)|this\s+(?:fire|wildfire|incident)|"
    r"the\s+(?:fire|wildfire|incident)|same\s+(?:fire|wildfire|incident))\b",
    re.IGNORECASE,
)
_GENERIC_LOCATED_NAMES = frozenset(
    {"a", "active", "any", "closest", "current", "local", "nearest", "the"}
)


def official_information_prefix(records: Sequence[LiveResult]) -> str:
    """Honest lead-in: cached-stale records are never called current."""

    return freshness_language.official_information_prefix(
        freshness_language.aggregate_freshness_from_records(list(records))
    )


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
        updates.update(
            annotated_distance_fields(
                result_id=item.result_id,
                kind=item.kind,
                geometry=item.geometry,
                latitude=resolved.latitude,
                longitude=resolved.longitude,
                freshness=item.freshness,
            )
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

    incident_number = _BCWS_INCIDENT_NUMBER.search(question)
    if incident_number is not None and re.search(
        r"\b(?:fire|wildfire|incident)\b", question, re.IGNORECASE
    ):
        return incident_number.group("number").upper()
    prefixed = _PREFIXED_NAMED_FIRE.search(question)
    if prefixed is not None:
        name = " ".join(prefixed.group("name").split()).strip(" ?.!'\"")
        return name or None
    match = _LOCATED_NAMED_FIRE.search(question)
    if match is None:
        return None
    base = " ".join(match.group("name").split()).strip(" ?.!'\"")
    if not base or base.casefold().split()[0] in _GENERIC_LOCATED_NAMES:
        return None
    return f"{base} Fire"


def _requested_fire_identity(request: QueryRequest) -> str | None:
    direct = extracted_located_fire_name(request.question)
    if direct is not None:
        return direct
    if not _FIRE_FOLLOW_UP.search(request.question):
        return None
    for turn in reversed(request.history):
        incident_number = _BCWS_INCIDENT_NUMBER.search(turn.content)
        if incident_number is not None:
            return incident_number.group("number").upper()
        prior = extracted_located_fire_name(turn.content)
        if prior is not None:
            return prior
    return None


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

    queried = _requested_fire_identity(request)
    if queried is None:
        return list(records)
    normalized_query = _normalized_record_name(queried)
    query_variants = {
        normalized_query,
        normalized_query.removesuffix(" fire").removesuffix(" wildfire"),
    }

    def normalized_identities(item: LiveResult) -> set[str]:
        values = (official_display_name(item), item.name or "", item.incident_number or "")
        return {_normalized_record_name(value) for value in values if value}

    exact = [item for item in records if normalized_identities(item) & query_variants]
    if exact:
        if "perimeter" not in request.question.casefold():
            incidents = [item for item in exact if item.kind == LiveResultKind.INCIDENT]
            if incidents:
                return incidents
        return exact
    typo_matches = [
        item
        for item in records
        if any(
            _is_single_typo(identity, variant)
            for identity in normalized_identities(item)
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
    if is_empty_map_safety_inference(request.question):
        incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in records)
        perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in records)
        evacuation_count = sum(item.kind == LiveResultKind.EVACUATION for item in records)
        record_label = "record" if len(records) == 1 else "records"
        return (
            "An empty map view is not an all-clear and does not establish that the "
            "area is safe. The current bounded official lookup returned "
            f"{len(records)} layer {record_label}: {incident_count} incidents, "
            f"{perimeter_count} perimeters, and {evacuation_count} evacuation "
            "records. These are layer-record counts, not distinct-fire counts or "
            "a safety determination."
        )
    located_name = extracted_located_fire_name(request.question)
    if located_name is not None:
        if not records:
            return f"No fetched official record matched the named fire {located_name}."
        matched = records[0]
        identity = official_display_name(matched)
        if (
            matched.incident_number
            and matched.incident_number.casefold() not in identity.casefold()
        ):
            identity = f"{identity} ({matched.incident_number})"
        geometry_type = str(matched.geometry.get("type") or "").strip()
        mapped_geometry = (
            f" Its official mapped geometry is a {geometry_type}."
            if geometry_type in {"Point", "Polygon", "MultiPolygon"}
            else ""
        )
        distance = (
            f" It is {matched.distance_km:g} km geodesic from the stated community "
            f"to the official {matched.distance_basis.replace('_', ' ')}."
            if matched.distance_km is not None and matched.distance_basis is not None
            else ""
        )
        return (
            f"The fetched official {matched.kind.value} record matches {identity}, "
            f"status {matched.status}.{mapped_geometry}{distance}"
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
    if is_evacuation_record_question(request.question):
        return evacuation_answer(
            request,
            records,
            display_name=official_display_name,
            nearby_radius_km=_NEARBY_RADIUS_KM,
        )
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
        return _geography(request.question, records)
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


def _geography(question: str, records: Sequence[LiveResult]) -> str:
    limitation = _geography_limitation(question)
    if not records:
        unavailable = (
            "The official records available for this request do not include "
            "fire-centre labels to summarize."
        )
        return f"{limitation} {unavailable}" if limitation else unavailable
    incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT]
    if not incidents:
        unavailable = "The fetched official records do not include wildfire incidents."
        return f"{limitation} {unavailable}" if limitation else unavailable
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
        breakdown = (
            "The only validated regional grouping in these records is the official "
            "fire-centre label. Incident counts by fire-centre label among fetched records: "
            f"{centre_text}. Highest count in this bounded result: {leaders}={highest}. "
            f"Status counts across the same incident records: {status_text}."
            f"{missing_note}"
        )
        return f"{limitation} {breakdown}" if limitation else breakdown
    unavailable = (
        "The official layer did not provide a fire-centre field. "
        f"Status counts from fetched records: {status_text}."
    )
    return f"{limitation} {unavailable}" if limitation else unavailable


def _geography_limitation(question: str) -> str:
    if _NORTH_SOUTH_COMPARISON.search(question) or directional_bc_region_label(question):
        return (
            "The official records do not provide a validated north/south classification "
            "for the requested directional B.C. region, so FireLens cannot determine "
            "which fetched incidents belong there or make a north-versus-south comparison."
        )
    if _LATITUDE_DENSITY.search(question):
        return (
            "FireLens has no validated latitude-band or density aggregation for "
            "these records: latitude bands and area denominators are not defined, "
            "so no latitude-band density is calculated."
        )
    if _GENERIC_DENSITY.search(question):
        return (
            "FireLens has no validated wildfire-density measure or area denominator "
            "for these records, so it does not calculate a density."
        )
    if _OKANAGAN_KOOTENAYS_COMPARISON.search(question):
        return (
            "The official records do not provide a validated Okanagan-versus-"
            "Kootenays classification or mapping, so FireLens does not make that "
            "regional comparison."
        )
    return ""


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
