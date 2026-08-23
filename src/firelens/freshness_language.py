"""Canonical public freshness wording. Live answers must not say current when stale."""

from __future__ import annotations

import re
from typing import Any

_CURRENT_LANGUAGE = re.compile(
    r"\b(?:current|currently|latest|live|up(?:\s+|-)to(?:\s+|-)date)\b",
    re.IGNORECASE,
)
_ALLOWED_NEGATION = re.compile(
    r"\bnot(?:\s+\w+){0,3}\s+(?:current|currently|latest|live|up(?:\s+|-)to(?:\s+|-)date)\b",
    re.IGNORECASE,
)


def freshness_value(freshness: Any) -> str | None:
    if freshness is None:
        return None
    return freshness.value if hasattr(freshness, "value") else str(freshness)


def allows_current_language(freshness: Any) -> bool:
    value = freshness_value(freshness)
    return value in {None, "fresh"}


def official_records_headline(freshness: Any) -> str:
    value = freshness_value(freshness)
    if value == "stale":
        return "Official cached records"
    if value == "mixed":
        return "Official records with mixed freshness"
    if value == "fresh":
        return "Official current records"
    return "Official records"


def official_information_prefix(freshness: Any) -> str:
    value = freshness_value(freshness)
    if value == "stale":
        return "Cached official information (refresh failed; cached records may be outdated): "
    if value == "mixed":
        return "Official information (includes stale cached records): "
    if value == "fresh":
        return "Current official information: "
    return "Official information: "


def aggregate_freshness_from_records(records: list[Any]) -> str | None:
    values = {freshness_value(getattr(item, "freshness", None)) for item in records}
    values.discard(None)
    if not values:
        return None
    if values == {"fresh"}:
        return "fresh"
    if values == {"stale"}:
        return "stale"
    return "mixed"


def current_language_errors(text: str, freshness: Any) -> list[str]:
    if allows_current_language(freshness):
        return []
    screened = _ALLOWED_NEGATION.sub(" ", text)
    if _CURRENT_LANGUAGE.search(screened):
        return ["stale_described_as_current"]
    return []
