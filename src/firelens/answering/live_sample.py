"""Deterministic high-information ranking for official live samples."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from firelens.live_contracts import LiveResult, LiveResultKind

INLINE_SAMPLE_LIMIT = 8
_PLACEHOLDER_NAME = "unnamed official record"
_FIRE_OF_NOTE_STATUS = "fire of note"
_OUT_OF_CONTROL = "out of control"


def official_fire_of_note(result: LiveResult) -> bool:
    """Return whether the official record is currently a Fire of Note."""

    if getattr(result, "fire_of_note", False):
        return True
    return (result.status or "").strip().casefold() == _FIRE_OF_NOTE_STATUS


def official_display_label(result: LiveResult) -> str:
    """Prefer an official name, then an honest unnamed label."""

    name = (result.name or "").strip()
    if name and name.casefold() != _PLACEHOLDER_NAME:
        return name
    number = (result.incident_number or "").strip() or result.result_id
    if result.kind == LiveResultKind.EVACUATION:
        return f"Unnamed evacuation record {number}"
    if result.kind == LiveResultKind.PERIMETER:
        return f"Unnamed perimeter {number}"
    return f"Unnamed incident {number}"


def _named(result: LiveResult) -> bool:
    name = (result.name or "").strip()
    return bool(name) and name.casefold() != _PLACEHOLDER_NAME


def _evacuation_associated_ids(records: Sequence[LiveResult]) -> frozenset[str]:
    """Associate an incident with a returned evacuation only on a shared identity."""

    evacuations = [item for item in records if item.kind == LiveResultKind.EVACUATION]
    if not evacuations:
        return frozenset()
    evac_numbers = {
        (item.incident_number or "").strip().casefold()
        for item in evacuations
        if (item.incident_number or "").strip()
    }
    evac_names = {
        (item.name or "").strip().casefold()
        for item in evacuations
        if (item.name or "").strip()
        and (item.name or "").strip().casefold() != _PLACEHOLDER_NAME
    }
    associated: set[str] = set()
    for item in records:
        if item.kind != LiveResultKind.INCIDENT:
            continue
        number = (item.incident_number or "").strip().casefold()
        name = (item.name or "").strip().casefold()
        if number and number in evac_numbers:
            associated.add(item.result_id)
        elif name and name in evac_names:
            associated.add(item.result_id)
    return frozenset(associated)


def information_value_key(
    result: LiveResult,
    *,
    evacuation_associated_ids: frozenset[str] = frozenset(),
) -> tuple[object, ...]:
    """Lower tuples sort first. The comparator is deterministic under shuffle."""

    status = (result.status or "").strip().casefold()
    size = result.size_hectares if result.size_hectares is not None else -1.0
    updated = result.source_updated_at
    updated_stamp = updated.timestamp() if isinstance(updated, datetime) else 0.0
    return (
        0 if official_fire_of_note(result) else 1,
        0 if status == _OUT_OF_CONTROL else 1,
        0 if result.result_id in evacuation_associated_ids else 1,
        0 if result.kind == LiveResultKind.INCIDENT else 1,
        -float(size),
        -updated_stamp,
        0 if _named(result) else 1,
        result.result_id,
    )


def rank_live_results(records: Sequence[LiveResult]) -> list[LiveResult]:
    """Return records in stable information-value order."""

    associated = _evacuation_associated_ids(records)
    return sorted(
        records,
        key=lambda item: information_value_key(item, evacuation_associated_ids=associated),
    )


def sample_live_results(
    records: Sequence[LiveResult], *, limit: int = INLINE_SAMPLE_LIMIT
) -> list[LiveResult]:
    """Return the priority sample used for inline answer cards and prose."""

    if limit <= 0:
        return []
    return rank_live_results(records)[:limit]


def sample_record_ids(
    records: Sequence[LiveResult], *, limit: int = INLINE_SAMPLE_LIMIT
) -> list[str]:
    return [item.result_id for item in sample_live_results(records, limit=limit)]
