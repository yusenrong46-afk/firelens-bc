"""Post-fetch official analysis. Luna narrates these facts; it does not invent them."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from firelens import freshness_language
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_analysis_distance import (
    closest_locatable_result as closest_locatable_result,
)
from firelens.answering.live_analysis_distance import (
    closest_three_facts as _closest_three_facts,
)
from firelens.answering.live_analysis_distance import (
    freshness_summary as _freshness_summary,
)
from firelens.answering.live_analysis_distance import (
    is_closest_live_question as is_closest_live_question,
)
from firelens.answering.live_analysis_distance import (
    is_freshness_question as is_freshness_question,
)
from firelens.answering.live_analysis_distance import (
    is_ranked_distance_question as is_ranked_distance_question,
)
from firelens.answering.live_analysis_distance import (
    is_three_fact_closest_question as is_three_fact_closest_question,
)
from firelens.answering.live_analysis_distance import (
    official_display_name as official_display_name,
)
from firelens.answering.live_analysis_distance import (
    ranked_distance_answer as _ranked_by_distance,
)
from firelens.answering.live_analysis_distance import size_roster as _size_roster
from firelens.answering.live_analysis_regional import geography_answer
from firelens.answering.live_evacuation import (
    evacuation_answer,
    is_evacuation_record_question,
)
from firelens.answering.live_focus import focused_record_answer
from firelens.answering.live_listing import listing_answer, listing_place
from firelens.answering.live_named_fire import (
    extracted_located_fire_name,
    requested_fire_identity,
)
from firelens.answering.live_record_intent import is_fire_geography_analysis
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
from firelens.understanding.fire_name import INCIDENT_NUMBER
from firelens.understanding.reference import ordinal_label, ordinal_reference

_NEARBY_RADIUS_KM = 50.0

_EXPLICIT_FIRE_LOOKUP = re.compile(
    r"\b(?:current\s+)?(?:fires?|wildfires?)\s+(?:near|around|in)\b",
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
    r"\bhow many\b.{0,80}\b(?:fires?|wildfires?|incidents?|fire\s+records?|records?)\b",
    re.IGNORECASE,
)


def is_record_count_question(question: str) -> bool:
    """ "How many fires / incidents / records ...": answered with a record count."""

    return _COUNT.search(question) is not None


_FIRE_CENTRE_MOST = re.compile(
    r"\bfire centres?\b.{0,40}\bmost\b|\bmost\b.{0,40}\bfire centres?\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"i(?:'m| am) not sure what you(?:'re| are) referring to",
    re.IGNORECASE,
)
_SIZE_ASK = re.compile(r"\b(?:how (?:large|big)|size|hectares?|ha)\b", re.IGNORECASE)
_CLOSEST_RATIONALE_ASK = re.compile(
    r"\bwhy\b.{0,100}\b(?:closest|nearest)\b",
    re.IGNORECASE,
)
_UNKNOWN_SELECTED_ASK = re.compile(
    r"\b(?:uncertain|not\s+certain|unknown|not\s+known)\b",
    re.IGNORECASE,
)
_PRECISE_COORD = re.compile(r"\b-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b")


def official_information_prefix(records: Sequence[LiveResult]) -> str:
    """Honest lead-in: cached-stale records are never called current."""
    return freshness_language.official_information_prefix(
        freshness_language.aggregate_freshness_from_records(list(records))
    )


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


def named_fire_not_found(name: str) -> str:
    """The requested fire is not in the current official list; say so, without a substitute."""

    if INCIDENT_NUMBER.fullmatch(name):
        return (
            f"No current official record has the fire number {name}. It may have been "
            "removed from the current list; try asking for the fires near a community."
        )
    display = name if name.casefold().split()[-1] in _FIRE_WORDS else f"{name} Fire"
    return (
        f"No current official record is named {display}. It may be listed under another "
        "name or fire number; try asking for the fires near a community."
    )


_FIRE_WORDS = frozenset({"fire", "wildfire", "complex", "blaze"})


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

    queried = requested_fire_identity(request)
    if queried is None:
        return list(records)

    def variants(value: str) -> set[str]:
        # "Creek" and "Creek Fire" name the same record.
        normalized = _normalized_record_name(value)
        return {normalized, normalized.removesuffix(" fire").removesuffix(" wildfire")}

    query_variants = variants(queried)

    def normalized_identities(item: LiveResult) -> set[str]:
        values = (official_display_name(item), item.name or "", item.incident_number or "")
        return set().union(*(variants(value) for value in values if value))

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
    selected_binding = bool(request.context.selected_live_result_id)
    if located_name is not None:
        if selected_binding:
            # The visible map selection is an explicit user binding. Do not
            # claim that it matches a separately named record; the selected
            # record composer below will identify the exact fetched result.
            return None
        if not records:
            return named_fire_not_found(located_name)
        matched = records[0]
        identity = official_display_name(matched)
        if (
            matched.incident_number
            and matched.incident_number.casefold() not in identity.casefold()
        ):
            identity = f"{identity} ({matched.incident_number})"
        geometry_type = str(matched.geometry.get("type") or "").strip()
        mapped_geometry = (
            " It is marked on the map as a point."
            if geometry_type == "Point"
            else " Its outline is drawn on the map."
            if geometry_type in {"Polygon", "MultiPolygon"}
            else ""
        )
        distance = (
            f" It is {matched.distance_km:g} km in a straight line from "
            f"{listing_place(request) or 'the place you asked about'}, measured to "
            f"{_basis_words(matched.distance_basis)}."
            if matched.distance_km is not None and matched.distance_basis is not None
            else ""
        )
        return f"{identity} is listed as {matched.status} by {matched.authority}.{mapped_geometry}{distance}"
    ordinal = ordinal_reference(request.question)
    if ordinal is not None:
        if selected_binding:
            return None
        return _ordinal_record(records, ordinal)
    has_incident_records = any(item.kind == LiveResultKind.INCIDENT for item in records)
    has_evacuation_records = any(item.kind == LiveResultKind.EVACUATION for item in records)
    mixed_fire_lookup = bool(
        has_incident_records
        and not has_evacuation_records
        and _EXPLICIT_FIRE_LOOKUP.search(request.question)
    )
    if is_evacuation_record_question(request.question) and not mixed_fire_lookup:
        return evacuation_answer(
            request,
            records,
            display_name=official_display_name,
            nearby_radius_km=_NEARBY_RADIUS_KM,
        )
    if _OLDEST.search(request.question):
        return "The official records do not give a start or ignition date for these fires."
    if _TWO_LARGEST.search(request.question):
        return _two_largest(records)
    if _FIRE_CENTRE_MOST.search(request.question):
        return _most_fire_centre(records)
    if "most burned" in lowered or ("largest" in lowered and "compare" not in lowered):
        return _max_hectares(records)
    if is_freshness_question(request.question) and not selected_binding:
        return _freshness_summary(records)
    if is_ranked_distance_question(request.question):
        return _ranked_by_distance(records)
    if is_three_fact_closest_question(request.question):
        return _closest_three_facts(request, records)
    if is_closest_live_question(request.question):
        if selected_binding:
            return None
        return _closest(request, records)
    if _SIZE_ASK.search(request.question) and not request.context.selected_live_result_id:
        return _size_roster(records)
    if is_fire_geography_analysis(request.question):
        return geography_answer(request.question, records)
    if _COUNT.search(request.question):
        return _count(records, roster_total, request)
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
                "The record you selected is no longer in the current official list. Select "
                "a fire on the map or in the list, or name it, and FireLens will answer "
                "about that one."
            )
        if _CLOSEST_RATIONALE_ASK.search(request.question):
            if selected.distance_km is None or selected.distance_basis is None:
                return (
                    f"The official record for {official_display_name(selected)} has no "
                    "mappable position, so FireLens cannot say how close it is."
                )
            return (
                f"{official_display_name(selected)} is the closest because its straight-line "
                f"distance, {selected.distance_km:g} km measured to "
                f"{_basis_words(selected.distance_basis)}, is the shortest of the records "
                "listed. That is a measurement, not a judgment of which fire matters most."
            )
        if _UNKNOWN_SELECTED_ASK.search(request.question):
            return (
                f"The official record for {official_display_name(selected)} gives its status "
                f"({selected.status}) and when it was last updated. It does not say what "
                "caused the fire, how it will spread, whether an area is safe, or whether "
                "anyone should evacuate."
            )
        return focused_record_answer(request, selected)
    narrate_incidents = any(
        item.kind == LiveResultKind.INCIDENT for item in records
    ) and not re.search(
        r"\b(?:perimeters?|multi[- ]layer|all (?:official )?layers|both (?:official )?layers)\b",
        lowered,
    )
    if narrate_incidents:
        records = [item for item in records if item.kind != LiveResultKind.PERIMETER]
    return listing_answer(request, records, roster_total=roster_total)


def _basis_words(basis: str | None) -> str:
    return (
        "its reported location"
        if basis == "incident_point"
        else "the edge of its mapped perimeter"
    )


def _ordinal_record(records: Sequence[LiveResult], index: int) -> str:
    """Count through this lookup's incidents when no shown list was sent."""

    incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT] or list(
        records
    )
    if index >= len(incidents):
        return (
            f"There is no {ordinal_label(index)} record in this list. Select a fire on the "
            "map or ask about one of the records shown."
        )
    chosen = incidents[index]
    distance = (
        f" It is {chosen.distance_km:g} km away in a straight line."
        if chosen.distance_km is not None
        else ""
    )
    return (
        f"{official_display_name(chosen)} is the {ordinal_label(index)} fire in this list, "
        f"listed as {chosen.status}.{distance}"
    )


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
        return "The official records do not give a size for any of the fires listed."
    chosen = max(sized, key=lambda item: item.size_hectares or 0.0)
    return (
        f"{official_display_name(chosen)} is the largest of the fires listed, at "
        f"{chosen.size_hectares:g} hectares according to {chosen.authority}."
    )


def _two_largest(records: Sequence[LiveResult]) -> str:
    sized = sorted(
        [item for item in records if item.size_hectares is not None],
        key=lambda item: item.size_hectares or 0.0,
        reverse=True,
    )
    if len(sized) < 2:
        return "The official records do not give sizes for two fires to compare."
    first, second = sized[0], sized[1]
    return (
        f"{official_display_name(first)} is the largest of the fires listed, at "
        f"{first.size_hectares:g} hectares. {official_display_name(second)} is next, at "
        f"{second.size_hectares:g} hectares."
    )


def _closest(request: QueryRequest, records: Sequence[LiveResult]) -> str:
    chosen = closest_locatable_result(request.question, records)
    if chosen is None:
        return "None of the fires listed has a mappable position, so FireLens cannot say which is closest."
    place = listing_place(request) or "the place you asked about"
    size = ""
    if _SIZE_ASK.search(request.question):
        size = (
            f" It is {chosen.size_hectares:g} hectares."
            if chosen.size_hectares is not None
            else " The official record does not give its size."
        )
    return (
        f"{official_display_name(chosen)} is the closest fire listed to {place}: "
        f"{chosen.distance_km:g} km in a straight line, measured to "
        f"{_basis_words(chosen.distance_basis)}.{size} That is not driving distance, "
        "and not a safety assessment."
    )


def _most_fire_centre(records: Sequence[LiveResult]) -> str:
    centres = [
        item.fire_centre.strip()
        for item in records
        if item.kind == LiveResultKind.INCIDENT and item.fire_centre
    ]
    if not centres:
        return "The official records do not say which fire centre the fires listed belong to."
    counts = Counter(centres)
    count = max(counts.values())
    leaders = sorted(
        (name for name, candidate_count in counts.items() if candidate_count == count),
        key=str.casefold,
    )
    if len(leaders) > 1:
        return (
            f"{', '.join(leaders)} are tied for the most fires listed, with {count} each. "
            "That is a count of records, not a safety assessment."
        )
    return (
        f"{leaders[0]} has the most fires listed, with {count}. That is a count of "
        "records, not a safety assessment."
    )


def _count(
    records: Sequence[LiveResult], roster_total: int | None, request: QueryRequest
) -> str:
    """ "How many fires ...": the record counts, said as counts of records."""

    incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in records)
    perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in records)
    evacuation_count = sum(item.kind == LiveResultKind.EVACUATION for item in records)
    shown = len(records)
    question = request.question
    place = (
        listing_place(request)
        if any(item.distance_km is not None for item in records)
        else None
    )
    where = f"near {place}" if place else "in British Columbia"
    publisher = next((item.authority for item in records), "BC Wildfire Service")
    not_safety = "That is a count of records, not a safety assessment."
    if is_evacuation_record_question(question) or re.search(
        r"\bevacuation\s+records?\b", question, re.IGNORECASE
    ):
        evacuation_publisher = next(
            (item.authority for item in records if item.kind == LiveResultKind.EVACUATION),
            "EmergencyInfoBC",
        )
        count = f"{evacuation_count} evacuation record{'' if evacuation_count == 1 else 's'}"
        return f"{evacuation_publisher} lists {count} {where} right now. {not_safety}"
    if roster_total is not None and roster_total > shown:
        return (
            f"{publisher} currently publishes {roster_total} matching records {where}; this "
            f"page shows {shown} of them ({incident_count} incidents and {perimeter_count} "
            f"perimeters). {not_safety}"
        )
    fires = f"{incident_count} fire{'' if incident_count == 1 else 's'}"
    breakdown = (
        f" ({incident_count} incident records and {perimeter_count} perimeter records; a "
        "fire can appear as both)"
        if perimeter_count
        else ""
    )
    return f"{publisher} lists {fires} {where} right now{breakdown}. {not_safety}"


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
