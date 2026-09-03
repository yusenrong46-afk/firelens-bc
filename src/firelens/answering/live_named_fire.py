"""Extract a named official fire from this turn or the previous user turn."""

from __future__ import annotations

import re

from firelens.contracts import QueryRequest
from firelens.understanding.place_vocabulary import DOMAIN_NOUNS, FUNCTION_WORDS

_LOCATED_NAMED_FIRE = re.compile(
    r"\bwhere(?:\s+is|['’]s)\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,5}?)\s+"
    r"(?:fire|wildfire)\s+(?:near|around|by|in|within)\b",
    re.IGNORECASE,
)
_PREFIXED_NAMED_FIRE = re.compile(
    r"\bwhere(?:\s+is|['’]s)\s+(?:the\s+)?(?:fire|wildfire|incident)\s+"
    r"(?P<name>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,5}?)"
    r"(?=\s+(?:right\s+now|today|tonight|currently|now)\b|[?!.]|$)",
    re.IGNORECASE,
)
_WHERE_IS_NAMED_FIRE = re.compile(
    r"(?i:\bwhere(?:\s+is|['’]s)\s+(?:the\s+)?)"
    r"(?P<name>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,4})\s+"
    r"(?i:(?:fire|wildfire)\s*(?:right\s+now|today|currently|now)?\s*[?!.]*\s*$)"
)
_BCWS_INCIDENT_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?P<number>[A-Za-z]\d{4,6})(?![A-Za-z0-9])"
)
_FIRE_FOLLOW_UP = re.compile(
    r"\b(?:it|its|that\s+(?:fire|wildfire|incident)|this\s+(?:fire|wildfire|incident)|"
    r"the\s+(?:fire|wildfire|incident)|same\s+(?:fire|wildfire|incident))\b",
    re.IGNORECASE,
)
# A fire name has a name head. Function words (near, the, that ...) and
# ordinal / proximity adjectives are not names; "near Kelowna" is a place.
_GENERIC_LOCATED_NAMES = (
    FUNCTION_WORDS
    | DOMAIN_NOUNS
    | frozenset(
        {
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "local",
            "biggest",
            "largest",
            "smallest",
        }
    )
)
_GUIDANCE_NAMED_SUBJECTS = frozenset(
    {
        "air quality",
        "alert",
        "emergency kit",
        "evacuation",
        "evacuation alert",
        "evacuation order",
        "fire",
        "firesmart",
        "go bag",
        "grab and go",
        "kit",
        "order",
        "precaution",
        "preparedness",
        "smoke",
        "the fire",
        "this fire",
        "that fire",
        "wildfire",
        "wildfire smoke",
    }
)
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
_TELL_ABOUT_FIRE = re.compile(
    r"\btell\s+me\s+about\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,4}?)"
    r"\s+(?:fire|wildfire|incident)\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_STILL_BURNING_FIRE = re.compile(
    r"\bis\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,4}?)"
    r"\s+(?:fire|wildfire|incident)\s+still\s+burning\b",
    re.IGNORECASE,
)
_STATUS_NAMED_FIRE = re.compile(
    r"\b(?:what(?:'s|\s+is)|give|show)\s+(?:me\s+)?(?:the\s+)?"
    r"(?:current\s+|latest\s+|official\s+)?status\s+(?:of|for)\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,4}?)\s+"
    r"(?:fire|wildfire|incident)\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_STATUS_NAMED_FIRE_TYPO = re.compile(
    r"\bwhts\s+(?:the\s+)?(?:current\s+|latest\s+|official\s+)?status\s+"
    r"(?:of\s+|for\s+)?(?:the\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]*){0,4}?)\s+"
    r"(?:fire|wildfire|incident)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _normalized_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def extracted_located_fire_name(question: str) -> str | None:
    """Extract a specifically named fire from a locate or about question."""

    incident_number = _BCWS_INCIDENT_NUMBER.search(question)
    if incident_number is not None:
        return incident_number.group("number").upper()
    prefixed = _PREFIXED_NAMED_FIRE.search(question)
    if prefixed is not None:
        usable = _usable_named_fire(prefixed.group("name"))
        if usable is not None:
            return usable
    match = _LOCATED_NAMED_FIRE.search(question)
    if match is not None:
        base = " ".join(match.group("name").split()).strip(" ?.!'\"")
        if base and base.casefold().split()[0] not in _GENERIC_LOCATED_NAMES:
            return f"{base} Fire"
    for pattern in (
        _WHERE_IS_NAMED_FIRE,
        _TELL_ABOUT_FIRE,
        _STILL_BURNING_FIRE,
        _STATUS_NAMED_FIRE,
        _STATUS_NAMED_FIRE_TYPO,
    ):
        mentioned = pattern.search(question)
        if mentioned is None:
            continue
        usable = _usable_named_fire(mentioned.group("name"))
        if usable is not None:
            return usable
    return None


def _usable_named_fire(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split()).strip(" ?.!'\"")
    if not cleaned:
        return None
    key = _normalized_name(cleaned)
    if not key or key in _GUIDANCE_NAMED_SUBJECTS:
        return None
    tokens = key.split()
    if tokens[0] in _GENERIC_LOCATED_NAMES:
        return None
    if any(token in _GUIDANCE_NAME_TOKENS for token in tokens):
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
        incident_number = _BCWS_INCIDENT_NUMBER.search(turn.content)
        if incident_number is not None:
            return incident_number.group("number").upper()
        prior = extracted_located_fire_name(turn.content)
        if prior is not None:
            return prior
    return None
