"""Deterministic extraction of coarse BC place labels from live-map questions."""

from __future__ import annotations

import re

from firelens.live_contracts import LocationInput

_PERSONAL_LOCATION = re.compile(
    r"\b(?:near|around|close to|closest to|where)\s+(?:me|my|our)\b|"
    r"\b(?:my|our)\s+(?:home|house|address|location|area|neighbou?rhood)\b|"
    r"\b(?:my|our)\s+current\s+location\b|"
    r"\b(?:to me|from me|from us|current location|where i am|where we are|"
    r"where i live|where we live)\b|"
    r"\b(?:how far|what distance)\s+(?:am i|are we)\b",
    re.IGNORECASE,
)

_PLACE_PATTERNS = (
    re.compile(
        r"\b(?:put|move|focus|centre|center|zoom)\s+(?:the\s+)?map\s+"
        r"(?:on|to|at|near|around)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:is|are)\s+(?P<place>[a-z][a-z .'-]{1,60})\s+under\s+"
        r"(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:is|are)\s+(?P<place>[a-z][a-z .'-]{1,60})\s+(?:under|on)\s+"
        r"(?:an?\s+)?(?:(?:evacuation|evac)\s+)?(?:alert|order)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:show|display)(?:\s+me)?\s+(?P<place>[a-z][a-z .'-]{1,60})\s+"
        r"(?:fire|wildfire)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:drive|travel|go)\s+to\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:near|around|round|by|within|in|for)\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
)

_TRAILING_CLAUSE = re.compile(
    r"\s+(?:and|but|then)\s+(?:tell|show|explain|what|how|is|are|give|help)\b.*$",
    re.IGNORECASE,
)
_TRAILING_TIME = re.compile(
    r"\s+(?:right\s+now|rn|today|tonight|currently|now|this\s+(?:morning|afternoon|evening|week))\b.*$",
    re.IGNORECASE,
)
_TRAILING_LIVE_NOUNS = re.compile(
    r"\s+(?:wildfires?|fires?|evacuation\s+(?:alerts?|orders?))$",
    re.IGNORECASE,
)
_REJECTED_PLACES = {
    "a wildfire",
    "an emergency",
    "bc",
    "british columbia",
    "effect",
    "the",
    "the province",
    "province",
    "this fire",
    "this incident",
    "this wildfire",
}

_PLACE_ALIASES = {
    "west k": "West Kelowna",
}


def _clean_place(candidate: str) -> str | None:
    place = candidate.split(",", maxsplit=1)[0]
    place = _TRAILING_CLAUSE.sub("", place)
    place = _TRAILING_TIME.sub("", place)
    place = _TRAILING_LIVE_NOUNS.sub("", place)
    place = place.strip(" .?!'\"")
    if place.casefold().startswith("the "):
        place = place[4:].strip()
    lowered = place.casefold()
    if (
        len(place) < 2
        or lowered in _REJECTED_PLACES
        or lowered.startswith(("a ", "an ", "the "))
        or any(token in lowered for token in ("grab-and-go", "go bag", "emergency kit"))
    ):
        return None
    return _PLACE_ALIASES.get(lowered, place)


def coarse_location_from_question(question: str) -> LocationInput | None:
    """Return only a user-stated place label; never infer personal coordinates."""

    if _PERSONAL_LOCATION.search(question):
        return None
    for pattern in _PLACE_PATTERNS:
        match = pattern.search(question)
        if match is None:
            continue
        place = _clean_place(match.group("place"))
        if place is None:
            continue
        try:
            return LocationInput(label=place, radius_km=50)
        except ValueError:
            return None
    return None


def asks_for_personal_location(question: str) -> bool:
    """Return whether answering needs location the user has not stated."""

    return bool(_PERSONAL_LOCATION.search(question))
