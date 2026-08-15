"""Shared deterministic helpers for official live-response construction."""

from __future__ import annotations

from firelens.contracts import AggregateFreshness


def freshness_limitation(state: AggregateFreshness) -> str | None:
    if state == AggregateFreshness.STALE:
        return "Cached official records; refresh failed. These records may be outdated."
    if state == AggregateFreshness.MIXED:
        return (
            "Official records include stale cached data because a refresh failed; "
            "some records may be outdated."
        )
    return None


def unique_limitations(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))
