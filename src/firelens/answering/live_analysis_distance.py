"""Deterministic distance rankings and selected-record follow-up facts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

from firelens import freshness_language
from firelens.contracts import LiveResult, LiveResultKind, QueryRequest

_PLACEHOLDER_NAME = "unnamed official record"
_CLOSEST_ASK = re.compile(r"\b(?:closest|nearest|how close)\b", re.IGNORECASE)
_RANKED_DISTANCE_ASK = re.compile(
    r"\b(?:list|rank|sort|show)\b.{0,100}\b(?:closest|nearest)\b|"
    r"\b(?:closest|nearest)\b.{0,100}\b(?:in\s+order|nearest\s+to\s+"
    r"(?:farthest|furthest))\b",
    re.IGNORECASE,
)
_TOP_CLOSEST_COUNT = re.compile(
    r"\b(?:the\s+)?(?P<count>two|three|2|3)\s+(?:"
    r"(?:closest|nearest)\s+(?:active\s+)?(?:fires?|wildfires?|incidents?)\b|"
    r"(?:live|official|current)\s+records?\s+(?:closest|nearest)\b)",
    re.IGNORECASE,
)
_THREE_FACT_CLOSEST = re.compile(
    r"\b(?:three|3)\s+(?:most\s+important\s+)?facts?\b.{0,100}"
    r"\b(?:closest|nearest)\b",
    re.IGNORECASE,
)
_FRESHNESS_ASK = re.compile(
    r"\b(?:when\b.{0,100}\b(?:updated|retrieved)|last\s+updated|"
    r"source\s+update|retrieval\s+time)\b",
    re.IGNORECASE,
)
_EVACUATION_ASK = re.compile(r"\bevacuation\b", re.IGNORECASE)
_FIRE_RECORD_ASK = re.compile(r"\b(?:fire|wildfire|incident)s?\b", re.IGNORECASE)


def official_display_name(result: LiveResult) -> str:
    """Prefer a real official name, then an honest unnamed label."""

    from firelens.answering.live_sample import official_display_label

    return official_display_label(result)


def is_ranked_distance_question(question: str) -> bool:
    return bool(_RANKED_DISTANCE_ASK.search(question))


def is_three_fact_closest_question(question: str) -> bool:
    return bool(_THREE_FACT_CLOSEST.search(question))


def is_freshness_question(question: str) -> bool:
    return bool(_FRESHNESS_ASK.search(question))


def is_closest_live_question(question: str) -> bool:
    """Return whether the question requests one nearest official record."""

    return bool(_CLOSEST_ASK.search(question) and not is_ranked_distance_question(question))


def closest_locatable_result(
    question: str,
    records: Sequence[LiveResult],
) -> LiveResult | None:
    """Choose the nearest typed record without relying on generated prose."""

    question_folded = question.casefold()
    if "perimeter" in question_folded:
        pool = [item for item in records if item.kind == LiveResultKind.PERIMETER]
    elif _EVACUATION_ASK.search(question):
        pool = [item for item in records if item.kind == LiveResultKind.EVACUATION]
    elif _FIRE_RECORD_ASK.search(question):
        pool = [item for item in records if item.kind == LiveResultKind.INCIDENT]
    else:
        incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT]
        pool = incidents or list(records)
    locatable = [item for item in pool if item.distance_km is not None]
    if not locatable:
        return None
    return min(
        locatable,
        key=lambda item: (item.distance_km or 0.0, item.result_id.casefold()),
    )


def _unique_ranked_incidents(records: Sequence[LiveResult]) -> list[LiveResult]:
    unique: dict[str, LiveResult] = {}
    for item in records:
        if item.kind != LiveResultKind.INCIDENT or item.distance_km is None:
            continue
        identity = (item.incident_number or item.name or item.result_id).strip().casefold()
        current = unique.get(identity)
        if current is None or (current.distance_km or 0.0) > item.distance_km:
            unique[identity] = item
    return sorted(
        unique.values(),
        key=lambda item: (item.distance_km or 0.0, official_display_name(item).casefold()),
    )


def ranked_live_results_for_request(
    question: str, records: Sequence[LiveResult]
) -> list[LiveResult]:
    """Return a stable incident ranking only when the user explicitly asks for one."""

    if not is_ranked_distance_question(question):
        return list(records)
    ranked = _unique_ranked_incidents(records)
    requested_count = _TOP_CLOSEST_COUNT.search(question)
    if requested_count is None:
        return ranked[:10]
    count = {"two": 2, "2": 2, "three": 3, "3": 3}[requested_count.group("count").lower()]
    return ranked[:count]


def freshness_summary(records: Sequence[LiveResult]) -> str:
    if not records:
        return "No fetched official record supplied a source or retrieval timestamp."
    source_times = sorted({item.source_updated_at for item in records})
    retrieval_times = sorted({item.retrieved_at for item in records})

    def describe(label: str, values: Sequence[datetime]) -> str:
        rendered = [value.isoformat() for value in values]
        if len(rendered) == 1:
            return f"{label} {rendered[0]}"
        return f"{label} range from {rendered[0]} to {rendered[-1]}"

    return (
        describe("Fetched official source update time:", source_times)
        + ". "
        + describe("FireLens retrieval times", retrieval_times)
        + ". Source update and FireLens retrieval are separate clocks."
    )


def ranked_distance_answer(records: Sequence[LiveResult]) -> str:
    ranked = _unique_ranked_incidents(records)
    if not ranked:
        return "The fetched official records do not include locatable geometry for ranking."
    entries = [
        f"{index}. {official_display_name(item)} — {item.distance_km:g} km"
        for index, item in enumerate(ranked[:10], start=1)
    ]
    return (
        "Nearest to farthest among fetched locatable official records: "
        + "; ".join(entries)
        + ". Distances are geodesic, not driving distances or safety assessments."
    )


def closest_three_facts(request: QueryRequest, records: Sequence[LiveResult]) -> str:
    chosen = closest_locatable_result(request.question, records)
    if chosen is None:
        return "The fetched official records do not include locatable geometry for this answer."
    size = (
        f"{chosen.size_hectares:g} hectares"
        if chosen.size_hectares is not None
        else "size not reported"
    )
    return (
        f"1. Record: {official_display_name(chosen)}. "
        f"2. Official status: {chosen.status}. "
        f"3. Distance and size: {chosen.distance_km:g} km geodesic; {size}."
    )


def size_roster(records: Sequence[LiveResult]) -> str:
    """Render reported areas without choosing one incident for the user."""

    incidents = [item for item in records if item.kind == LiveResultKind.INCIDENT] or list(
        records
    )
    parts: list[str] = []
    for item in incidents[:8]:
        name = official_display_name(item)
        if item.size_hectares is None:
            parts.append(f"{name}: size not reported")
        else:
            parts.append(f"{name}: {item.size_hectares:g} hectares")
    if not parts:
        return "The official records do not report burned hectares for the fetched fires."
    prefix = freshness_language.official_information_prefix(
        freshness_language.aggregate_freshness_from_records(list(records))
    )
    return prefix + "; ".join(parts)
