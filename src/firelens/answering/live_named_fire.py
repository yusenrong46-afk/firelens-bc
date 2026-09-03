"""Extract a named official fire from this turn or the previous user turn."""

from __future__ import annotations

import re

from firelens.contracts import QueryRequest
from firelens.understanding.fire_name import extract_fire_name

_FIRE_FOLLOW_UP = re.compile(
    r"\b(?:it|its|that\s+(?:fire|wildfire|incident)|this\s+(?:fire|wildfire|incident)|"
    r"the\s+(?:fire|wildfire|incident)|same\s+(?:fire|wildfire|incident))\b",
    re.IGNORECASE,
)
# Guidance subjects that can precede a fire noun without naming a fire.
_GUIDANCE_NAME_TOKENS = frozenset(
    {
        "checklist",
        "comparison",
        "ecology",
        "ecosystem",
        "ecosystems",
        "education",
        "english",
        "firesmart",
        "guidance",
        "history",
        "homeowner",
        "homeowners",
        "kit",
        "legislation",
        "policies",
        "policy",
        "precaution",
        "preparedness",
        "prevention",
        "program",
        "programs",
        "research",
        "school",
        "schools",
        "smoke",
        "student",
        "students",
        "taught",
        "teaching",
        "tomorrow",
        "geography",
    }
)


def _normalized_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def extracted_located_fire_name(question: str) -> str | None:
    """The specific fire this question names (incident number or name), or None."""

    mention = extract_fire_name(question)
    if mention is None:
        return None
    if mention.incident_number:
        return mention.label
    return _usable_named_fire(mention.label)


def _usable_named_fire(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split()).strip(" ?.!'\"")
    if not cleaned:
        return None
    tokens = _normalized_name(cleaned).split()
    if not tokens or any(token in _GUIDANCE_NAME_TOKENS for token in tokens):
        return None
    return cleaned


def requested_fire_identity(request: QueryRequest) -> str | None:
    """Name or incident number this turn is asking about, including user history."""

    direct = extracted_located_fire_name(request.question)
    if direct is not None:
        return direct
    if not _FIRE_FOLLOW_UP.search(request.question):
        return None
    for turn in reversed(request.history):
        if turn.role != "user":
            continue
        prior = extracted_located_fire_name(turn.content)
        if prior is not None:
            return prior
    return None
