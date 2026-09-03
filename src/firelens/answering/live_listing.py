"""PRESENT: the official records near a place, or across B.C., in plain words.

The list a person reads is the list they see on the map and in the record
cards, in the same order (`display_order`): nearest first when measured from a
place, most significant first otherwise. Every number is an official field
exactly as published (distances and sizes with `:g`), the publisher is named,
and the age of the records is stated. A cached copy is always called cached.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from firelens.answering.live_sample import (
    display_order,
    official_display_label,
    official_fire_of_note,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.plain_time import time_ago
from firelens.contracts import LiveResult, LiveResultKind, QueryRequest
from firelens.freshness_language import aggregate_freshness_from_records

# How many records the prose names before pointing at the list and the map.
NAMED_IN_PROSE = 3


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _name(record: LiveResult) -> str:
    label = official_display_label(record)
    number = (record.incident_number or "").strip()
    if number and number.casefold() not in label.casefold():
        return f"{label} ({number})"
    return label


def _status(record: LiveResult) -> str:
    text = f"listed as {record.status}" if record.status else "with no status reported"
    if official_fire_of_note(record) and "fire of note" not in (record.status or "").casefold():
        text += ", a Fire of Note"
    if record.size_hectares is not None:
        text += f", {record.size_hectares:g} hectares"
    return text


def listing_place(request: QueryRequest) -> str | None:
    """The place a lookup was measured from, as the person named it."""

    if request.location is not None and request.location.label:
        return request.location.label
    mention = coarse_location_from_question(request.question)
    if mention is not None and mention.label:
        return mention.label
    if request.location is not None:
        return "your approximate location"
    return None


def _counted(fires: Sequence[LiveResult]) -> str:
    """ "2 fires", "3 fires and 3 perimeters", "1 perimeter": counted by kind."""

    incidents = sum(item.kind == LiveResultKind.INCIDENT for item in fires)
    perimeters = len(fires) - incidents
    parts = []
    if incidents:
        parts.append(_plural(incidents, "fire"))
    if perimeters:
        parts.append(_plural(perimeters, "perimeter"))
    return " and ".join(parts)


def _status_breakdown(fires: Sequence[LiveResult]) -> str:
    """ "Of these, 3 are Out of Control and 7 are Being Held.\""""

    counts: dict[str, int] = {}
    for record in fires:
        status = record.status or "without a reported status"
        counts[status] = counts.get(status, 0) + 1
    parts = [
        f"{count} {'is' if count == 1 else 'are'} {status}"
        for status, count in sorted(counts.items(), key=lambda item: -item[1])
    ]
    if len(parts) == 1:
        return f"All of them are {next(iter(counts))}."
    return f"Of these, {', '.join(parts[:-1])} and {parts[-1]}."


def _fire_sentences(fires: Sequence[LiveResult], *, measured: bool) -> list[str]:
    sentences: list[str] = []
    for index, record in enumerate(fires[:NAMED_IN_PROSE]):
        name = _name(record)
        if measured and record.distance_km is not None:
            opener = f"The closest is {name}," if index == 0 else f"{name} is"
            sentences.append(f"{opener} {record.distance_km:g} km away, {_status(record)}.")
        elif measured:
            sentences.append(
                f"{name} has no mappable position in the official record, {_status(record)}."
            )
        else:
            sentences.append(f"{name} is {_status(record)}.")
    return sentences


def _evacuation_sentence(evacuations: Sequence[LiveResult], place: str | None) -> str:
    publisher = evacuations[0].authority
    where = f" near {place}" if place else ""
    described = "; ".join(
        f"{official_display_label(record)}"
        + (f" ({record.status}" + (f", issued by {record.issuer})" if record.issuer else ")"))
        for record in evacuations[:NAMED_IN_PROSE]
    )
    more = (
        f" and {len(evacuations) - NAMED_IN_PROSE} more"
        if len(evacuations) > NAMED_IN_PROSE
        else ""
    )
    return f"{publisher} lists {_plural(len(evacuations), 'evacuation record')}{where}: {described}{more}."


def _freshness_sentence(records: Sequence[LiveResult], now: datetime | None) -> str:
    freshness = aggregate_freshness_from_records(list(records))
    if freshness == "stale":
        return (
            "FireLens is showing a cached copy of these records because the live refresh "
            "failed; they may be outdated."
        )
    if freshness == "mixed":
        return (
            "Some of these records are cached copies from a failed refresh and may be outdated."
        )
    publishers = list(dict.fromkeys(record.authority for record in records))
    latest = max(record.source_updated_at for record in records)
    who = publishers[0] if len(publishers) == 1 else "The publishers"
    return f"{who} last updated these records {time_ago(latest, now=now)}."


def listing_answer(
    request: QueryRequest,
    records: Sequence[LiveResult],
    *,
    roster_total: int | None = None,
    now: datetime | None = None,
) -> str:
    """Plain-language listing of the fetched official records, in display order."""

    ordered = display_order(records)
    fires = [item for item in ordered if item.kind != LiveResultKind.EVACUATION]
    evacuations = [item for item in ordered if item.kind == LiveResultKind.EVACUATION]
    measured = any(item.distance_km is not None for item in ordered)
    place = listing_place(request) if measured else None
    sentences: list[str] = []
    if fires:
        where = f" near {place}" if place else " in British Columbia"
        sentences.append(f"{fires[0].authority} lists {_counted(fires)}{where}.")
        sentences.extend(_fire_sentences(fires, measured=measured))
        if len(fires) > NAMED_IN_PROSE:
            sentences.append(
                f"The other {len(fires) - NAMED_IN_PROSE} are in the list below and on the map."
            )
            if not measured:
                sentences.append(_status_breakdown(fires))
    if evacuations:
        sentences.append(_evacuation_sentence(evacuations, place))
    if roster_total is not None and roster_total > len(records):
        sentences.append(
            f"This shows {len(records)} of the {roster_total} records currently published; "
            "the official map has the rest."
        )
    sentences.append(_freshness_sentence(ordered, now))
    if measured and place:
        sentences.append(
            f"Distances are straight-line from {place}, not driving distance, and not a "
            "safety assessment."
        )
    return " ".join(sentences)
