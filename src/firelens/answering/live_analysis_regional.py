"""Deterministic regional summaries for admitted official incident records."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from firelens.answering.location_intent import directional_bc_region_label
from firelens.contracts import LiveResult, LiveResultKind

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


def geography_answer(question: str, records: Sequence[LiveResult]) -> str:
    """Summarize only official fire-centre and status fields present in ``records``."""

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
    status_text = _counted_labels(
        sorted(statuses.items(), key=lambda row: row[0].casefold()), label_first=True
    )
    if centres:
        ordered = sorted(centres.items(), key=lambda row: (-row[1], row[0].casefold()))
        highest = ordered[0][1]
        leaders = [name for name, count in ordered if count == highest]
        missing_centre_count = len(incidents) - sum(centres.values())
        missing_note = (
            f" {missing_centre_count} fetched incident records were omitted from the "
            "fire-centre breakdown because the official centre label was unavailable."
            if missing_centre_count
            else ""
        )
        centre_summary = _regional_count_summary(ordered, leaders, highest)
        breakdown = (
            "These fetched incident records use the official fire-centre label for "
            f"regional grouping. {centre_summary} Statuses in the same records: "
            f"{status_text}. This is a record count, not a safety determination."
            f"{missing_note}"
        )
        return f"{limitation} {breakdown}" if limitation else breakdown
    unavailable = (
        "The official layer did not provide a fire-centre field. "
        f"Statuses in the fetched incident records: {status_text}. "
        "This is a record count, not a safety determination."
    )
    return f"{limitation} {unavailable}" if limitation else unavailable


def _regional_count_summary(
    ordered: Sequence[tuple[str, int]], leaders: Sequence[str], highest: int
) -> str:
    """Render the admitted fire-centre distribution without machine-style ``name=count``."""

    noun = "incident" if highest == 1 else "incidents"
    if len(leaders) == 1:
        leader_summary = (
            f"{leaders[0]} has {highest} {noun}, the highest count in this bounded result."
        )
    else:
        leader_summary = (
            f"{_join_words(list(leaders))} are tied for the highest count in this bounded "
            f"result, with {highest} {noun} each."
        )
    remaining = [(name, count) for name, count in ordered if name not in leaders]
    if not remaining:
        return leader_summary
    return f"{leader_summary} Other fire-centre counts: {_counted_labels(remaining)}."


def _counted_labels(items: Sequence[tuple[str, int]], *, label_first: bool = False) -> str:
    phrases = []
    for name, count in items:
        noun = "incident" if count == 1 else "incidents"
        phrases.append(f"{count} {name}" if label_first else f"{name} has {count} {noun}")
    return _join_words(phrases)


def _join_words(parts: Sequence[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


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
