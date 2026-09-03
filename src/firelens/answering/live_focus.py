"""PRESENT: plain-language answers about the one official record in focus.

Every sentence states an official field exactly as published, names the
publisher, and says how old the record is. The record's fields are the whole
authority: what they do not contain (cause, forecast, personal safety) is said
plainly, not guessed.
"""

from __future__ import annotations

from datetime import datetime

from firelens.answering.live_analysis_distance import official_display_name
from firelens.answering.plain_time import human_time, time_ago
from firelens.contracts import LiveResult, LiveResultKind, QueryRequest
from firelens.understanding.focus import (
    FocusAttribute,
    FocusReference,
    attributes_asked,
    focus_reference,
)

_NOT_SAFETY = (
    "That is a straight-line distance, not driving distance, and not a safety assessment."
)


def _noun(record: LiveResult) -> str:
    return {
        LiveResultKind.INCIDENT: "fire",
        LiveResultKind.PERIMETER: "perimeter",
        LiveResultKind.EVACUATION: "evacuation",
    }.get(record.kind, "record")


def _size(record: LiveResult) -> str | None:
    if record.size_hectares is None:
        return None
    return f"{record.size_hectares:g} hectares"


def _name(record: LiveResult) -> str:
    """The official name, with the fire number when the name does not carry it."""

    name = official_display_name(record)
    number = record.incident_number
    if number and number.casefold() not in name.casefold():
        return f"{name} ({number})"
    return name


def _on_the_map(record: LiveResult) -> str:
    shape = str(record.geometry.get("type") or "")
    if shape == "Point":
        return "It is marked on the map as a point."
    if shape in {"Polygon", "MultiPolygon"}:
        return "Its outline is drawn on the map."
    return "It is marked on the map."


def _updated(record: LiveResult, now: datetime | None) -> str:
    text = (
        f"{record.authority} last updated this record "
        f"{time_ago(record.source_updated_at, now=now)} "
        f"({human_time(record.source_updated_at, now=now)})"
    )
    if str(getattr(record.freshness, "value", record.freshness)) == "stale":
        text += (
            ". FireLens is showing a cached copy because the live refresh failed, so it "
            "may be outdated"
        )
    return text


def _area(record: LiveResult) -> str | None:
    parts = [part for part in (record.fire_zone, record.fire_centre) if part]
    if not parts:
        return None
    text = ", ".join(dict.fromkeys(parts))
    return text if "cent" in text.casefold() else f"{text} Fire Centre"


def _origin(request: QueryRequest, reference_place: str | None) -> str:
    if reference_place:
        return reference_place
    if request.location is not None and request.location.label:
        return request.location.label
    if request.location is not None:
        return "your approximate location"
    return "the place you asked about"


def _distance_sentence(record: LiveResult, name: str, origin: str) -> str:
    if record.distance_km is None:
        return (
            f"The official record for {name} has no mappable position, so FireLens cannot "
            "measure a distance to it."
        )
    basis = (
        "its reported location"
        if record.distance_basis == "incident_point"
        else "the edge of its mapped perimeter"
    )
    return (
        f"{name} is {record.distance_km:g} km from {origin}, measured to {basis}. {_NOT_SAFETY}"
    )


def _status_sentence(record: LiveResult, name: str) -> str:
    note = " and is a Fire of Note" if record.fire_of_note else ""
    return f"{name} is listed as {record.status}{note} by {record.authority}."


def _location_sentence(record: LiveResult, name: str, origin: str) -> str:
    area = _area(record)
    sentence = (
        f"{name} is in the {area}."
        if area
        else f"The official record does not name an area for {name}."
    )
    if record.distance_km is not None:
        sentence += f" It is {record.distance_km:g} km from {origin}."
    return f"{sentence} {_on_the_map(record)}"


def _details(record: LiveResult, name: str, origin: str, now: datetime | None) -> str:
    facts = [_status_sentence(record, name)]
    clauses: list[str] = []
    if (size := _size(record)) is not None:
        clauses.append(f"is {size}")
    if (area := _area(record)) is not None:
        clauses.append(f"is in the {area}")
    if record.distance_km is not None:
        clauses.append(f"is {record.distance_km:g} km from {origin}")
    if len(clauses) > 1:
        facts.append(f"It {', '.join(clauses[:-1])} and {clauses[-1]}.")
    elif clauses:
        facts.append(f"It {clauses[0]}.")
    facts.append(_on_the_map(record))
    facts.append(f"{_updated(record, now)}.")
    return " ".join(facts)


def focused_record_answer(
    request: QueryRequest,
    record: LiveResult,
    *,
    now: datetime | None = None,
) -> str:
    """Answer the attribute asked about the focused record, in plain words."""

    # A turn that named the record itself ("Where is wildfire K51402?") still
    # asks an attribute; only the subject reading is skipped.
    focus = focus_reference(request.question) or FocusReference(
        attributes_asked(request.question) or (FocusAttribute.DETAILS,)
    )
    name = _name(record)
    origin = _origin(request, focus.reference_place)
    if focus.attribute == FocusAttribute.UNSUPPORTED:
        return (
            f"The official record does not say why {name} started, how it will behave, or "
            f"whether it will reach a place. {_status_sentence(record, name)} "
            f"{_updated(record, now)}. For anything beyond the published fields, use the "
            f"{record.authority} record linked below."
        )
    sentences: list[str] = []
    for attribute in focus.attributes:
        if attribute == FocusAttribute.DISTANCE:
            sentences.append(_distance_sentence(record, name, origin))
        elif attribute == FocusAttribute.SIZE:
            size = _size(record)
            sentences.append(
                f"{name} is {size}, according to {record.authority}."
                if size
                else f"The official record for {name} does not give a size."
            )
        elif attribute == FocusAttribute.UPDATED:
            sentences.append(
                f"{_updated(record, now)}. FireLens fetched it "
                f"{time_ago(record.retrieved_at, now=now)} "
                f"({human_time(record.retrieved_at, now=now)}); those are two different clocks."
            )
        elif attribute == FocusAttribute.SOURCE:
            sentences.append(
                f"The source for {name} is {record.authority}, which publishes this "
                f"{_noun(record)} record. The official record is linked below."
            )
        elif attribute == FocusAttribute.LOCATION:
            sentences.append(_location_sentence(record, name, origin))
        elif attribute == FocusAttribute.STATUS:
            sentences.append(_status_sentence(record, name))
        elif attribute == FocusAttribute.DETAILS:
            sentences.append(_details(record, name, origin, now))
    if not {FocusAttribute.UPDATED, FocusAttribute.DETAILS} & set(focus.attributes):
        sentences.append(f"{_updated(record, now)}.")
    return " ".join(dict.fromkeys(sentences))
