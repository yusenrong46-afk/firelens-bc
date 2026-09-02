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
from firelens.answering.live_named_fire import (
    extracted_located_fire_name,
    requested_fire_identity,
)
from firelens.answering.live_record_intent import is_fire_geography_analysis
from firelens.answering.live_sample import (
    official_fire_of_note,
    rank_live_results,
    sample_live_results,
)
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

_EXPLICIT_FIRE_LOOKUP = re.compile(
    r"\b(?:current\s+)?(?:fires?|wildfires?)\s+(?:near|around|in)\b",
    re.IGNORECASE,
)

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
_ORDINAL_FIRE = re.compile(
    r"\b(?:the\s+)?(?P<rank>first|second|third|1st|2nd|3rd)\s+"
    r"(?:one|fire|wildfire|incident|record)\b",
    re.IGNORECASE,
)
_ORDINAL_RANK = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}


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
    selected_binding = bool(request.context.selected_live_result_id)
    if located_name is not None:
        if selected_binding:
            # The visible map selection is an explicit user binding. Do not
            # claim that it matches a separately named record; the selected
            # record composer below will identify the exact fetched result.
            return None
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
    ordinal = _ORDINAL_FIRE.search(request.question)
    if ordinal is not None:
        if selected_binding:
            return None
        return _ordinal_record(records, ordinal.group("rank"))
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
        return (
            "The official records available for this request do not report a "
            "start or ignition date."
        )
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
        if _CLOSEST_RATIONALE_ASK.search(request.question):
            if selected.distance_km is None or selected.distance_basis is None:
                return (
                    "The selected official record does not include a bound distance, so "
                    "FireLens cannot re-establish why it ranked closest."
                )
            basis = selected.distance_basis.replace("_", " ")
            return (
                f"FireLens kept {official_display_name(selected)} selected because the "
                f"preceding deterministic lookup ranked its {selected.distance_km:g} km "
                f"geodesic distance to the official {basis}. The model did not choose "
                "the record."
            )
        if _UNKNOWN_SELECTED_ASK.search(request.question):
            return (
                f"The fetched official record establishes {official_display_name(selected)}'s "
                f"reported status ({selected.status}) and source timestamp. It does not "
                "establish the fire's cause, future spread, local safety, or a personal "
                "evacuation decision."
            )
        if is_freshness_question(request.question):
            return (
                f"Freshness: the official source updated {official_display_name(selected)} at "
                f"{selected.source_updated_at.isoformat()}. FireLens retrieved that record "
                f"at {selected.retrieved_at.isoformat()}. These are separate clocks."
            )
        if (
            "source" in lowered
            or "reported" in lowered
            or "published" in lowered
            or "updated" in lowered
        ):
            timestamp = selected.source_updated_at.isoformat()
            freshness = freshness_language.freshness_value(selected.freshness)
            freshness_clause = (
                f" Record freshness: {freshness}." if freshness is not None else ""
            )
            return (
                f"Official source for {official_display_name(selected)}: "
                f"{selected.authority}. The official record timestamp is "
                f"{timestamp}.{freshness_clause}"
            )
        if "size" in lowered or "hectare" in lowered or "how large" in lowered:
            status_clause = (
                f" Its official status is {selected.status}." if "status" in lowered else ""
            )
            if selected.size_hectares is None:
                return (
                    f"The official record for {official_display_name(selected)} "
                    f"does not provide a size value.{status_clause}"
                )
            return (
                f"The official record reports {official_display_name(selected)} at "
                f"{selected.size_hectares:g} hectares.{status_clause}"
            )
        return (
            f"{official_display_name(selected)}: {selected.status}. "
            "Open the selected official record for the fields its publishing "
            "authority provides."
        )
    narrate_incidents = any(
        item.kind == LiveResultKind.INCIDENT for item in records
    ) and not re.search(
        r"\b(?:perimeters?|multi[- ]layer|all (?:official )?layers|both (?:official )?layers)\b",
        lowered,
    )
    if narrate_incidents:
        records = [item for item in records if item.kind != LiveResultKind.PERIMETER]
    ranked = rank_live_results(records)
    sample = sample_live_results(ranked)
    parts: list[str] = []
    for item in sample:
        line = f"{official_display_name(item)}: {item.status}"
        if official_fire_of_note(item) and "fire of note" not in (item.status or "").casefold():
            line += ", Fire of Note"
        if item.size_hectares is not None:
            line += f", {item.size_hectares:g} ha"
        if item.distance_km is not None:
            line += f", {item.distance_km:g} km"
        parts.append(line)
    prefix = official_information_prefix(records)
    if len(records) <= 8:
        return prefix + "; ".join(parts)
    distribution = Counter(item.status or "Status not reported" for item in records)
    distribution_text = "; ".join(
        f"{status}: {count}"
        for status, count in sorted(distribution.items(), key=lambda item: item[0].casefold())
    )
    note_count = sum(1 for item in records if official_fire_of_note(item))
    note_text = f" Fire of Note indicator: {note_count}." if note_count else ""
    return (
        f"{prefix}{len(records)} fetched official records. "
        f"Status distribution in the fetched records: {distribution_text}.{note_text} "
        f"Showing a priority sample of {len(sample)} of {len(records)} fetched records: "
        + "; ".join(parts)
    )


def _ordinal_record(records: Sequence[LiveResult], rank: str) -> str:
    incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT] or list(
        records
    )
    index = _ORDINAL_RANK[rank.casefold()]
    if index >= len(incidents):
        return (
            "Select a mapped official record before asking about that position in the "
            "list. FireLens will not substitute a different nearby record."
        )
    chosen = incidents[index]
    distance = (
        f" It is {chosen.distance_km:g} km geodesic from the stated community."
        if chosen.distance_km is not None
        else ""
    )
    return (
        f"{official_display_name(chosen)} is the {rank.casefold()} official incident "
        f"in this lookup, status {chosen.status}.{distance}"
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
    chosen = closest_locatable_result(request.question, records)
    if chosen is None:
        return (
            "The official records do not include locatable geometry for a closest-fire answer."
        )
    basis = (
        "incident point" if chosen.distance_basis == "incident_point" else "perimeter boundary"
    )
    if _SIZE_ASK.search(request.question):
        size = (
            f"The official area is {chosen.size_hectares:g} hectares."
            if chosen.size_hectares is not None
            else "The official record does not report an area."
        )
        return (
            f"{official_display_name(chosen)} is the closest official record among "
            f"fetched locatable records, {chosen.distance_km:g} km geodesic measured "
            f"to the official {basis}. {size} This is not driving distance or a safety "
            "assessment."
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
