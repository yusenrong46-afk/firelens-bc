"""Deterministic extraction of coarse BC place labels from live-map questions."""

from __future__ import annotations

import re

from firelens.answering import intent_lexicon as lex
from firelens.answering import intent_spans as spans
from firelens.answering.location_intent_patterns import (
    CLOSEST_FIRE_TRAILING_PLACE,
    MULTI_PLACE_DISTANCE_COMPARISONS,
    MULTI_PLACE_FIRE_COMPARISONS,
)
from firelens.answering.request_grammar import (
    parse_request_facets,
    requests_non_bc_national_scope,
)
from firelens.live_contracts import LocationInput

_PERSONAL_LOCATION = re.compile(
    r"\b(?:near|around|close to|closest to|where)\s+(?:me|my|our)\b|"
    r"\b(?:my|our)\s+(?:place|home|house|address|location|area|neighbou?rhood)\b|"
    r"\b(?:my|our)\s+current\s+location\b|"
    r"\b(?:to me|from me|from us|current location|where i am|where we are|"
    r"where i live|where we live)\b|"
    r"\b(?:how far|what distance)\s+(?:am i|are we)\b",
    re.IGNORECASE,
)
_DIRECTIONAL_BC_REGION = re.compile(
    r"(?<!\w)(?P<direction>north(?:ern)?|south(?:ern)?)\s+"
    r"(?:b\s*\.?\s*c(?:\.)?|british\s+columbia)(?!\w)",
    re.IGNORECASE,
)
_PROVINCE_WIDE_SCOPE = re.compile(
    r"\b(?:across|throughout|in|of|by|around)\s+"
    r"(?:the\s+)?(?:province|b\s*\.?\s*c\s*\.?|british\s+columbia)\b"
    r"|\b(?:province|b\s*\.?\s*c\s*\.?)\s*[- ]wide\b",
    re.IGNORECASE,
)


def is_multi_place_fire_comparison(question: str) -> bool:
    """Return true when one request requires two independent distance origins."""

    return any(pattern.search(question) for pattern in MULTI_PLACE_DISTANCE_COMPARISONS)


_PLACE_PATTERNS = (
    re.compile(
        r"\b(?:wildfire|fire|incident|perimeter|evacuation)?\s*"
        r"(?:map|layer|view|search)\b.{0,50}"
        r"\b(?:empty|blank|returned?\s+(?:no|zero)|returned?\s+nothing)\b"
        r".{0,50}\b(?:near|around|in)\s+"
        r"(?P<place>[a-z0-9][a-z0-9 .'-]{1,80}?)"
        r"(?=[,;:.?!]|\s+(?:and|but|so)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:no|zero)\s+(?:map\s+)?(?:pins?|markers?)\s+"
        r"(?:are\s+)?(?:show|showing|visible|displayed|present|appearing)\b"
        r".{0,50}\b(?:near|around|in)\s+"
        r"(?P<place>[a-z0-9][a-z0-9 .'-]{1,80}?)"
        r"(?=[,;:.?!]|\s+(?:and|but|so)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:nothing|no\s+(?:matching\s+)?"
        r"(?:results?|fires?|wildfires?|records?)|zero\s+(?:matching\s+)?"
        r"(?:results?|fires?|wildfires?|records?))\b"
        r".{0,50}\b(?:on|in)\s+(?:the\s+)?(?:fire|wildfire)?\s*map\b"
        r".{0,50}\b(?:near|around|in)\s+"
        r"(?P<place>[a-z0-9][a-z0-9 .'-]{1,80}?)"
        r"(?=[,;:.?!]|\s+(?:and|but|so)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:fire|wildfire)?\s*map\b.{0,80}"
        r"\b(?:empty|blank|nothing|no\s+(?:results?|fires?|wildfires?|records?)|"
        r"zero\s+(?:results?|fires?|wildfires?|records?))\b"
        r".{0,50}\b(?:near|around|in)\s+"
        r"(?P<place>[a-z0-9][a-z0-9 .'-]{1,80}?)"
        r"(?=[,;:.?!]|\s+(?:and|but|so)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*map\s+(?P<place>[a-z][a-z .'-]{1,80}?)(?=\s+(?:right\s+now|rn|today|"
        r"tonight|currently|now)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?!(?:i|we|you|give|show|list|which|what|where|how|is|are|can|could|"
        r"please|tell|there)\b)"
        r"(?P<place>[a-z][a-z.'-]*(?:\s+[a-z][a-z.'-]*){0,3}?)\s+"
        r"(?:any\s+)?(?:wild)?fires?(?:\s+(?:right\s+now|rn|today|tonight|"
        r"currently|now))?[?!.,]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:put|move|focus|centre|center|zoom)\s+(?:the\s+)?map\s+"
        r"(?:on|to|at|near|around)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:is|are)\s+(?P<place>[a-z][a-z .'-]{1,60})\s+under\s+"
        r"(?:an?\s+)?(?:evacuation\s+)?(?:alerts?|orders?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:is|are)\s+(?P<place>[a-z][a-z .'-]{1,60})\s+(?:under|on)\s+"
        r"(?:an?\s+)?(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:show|display)(?:\s+me)?\s+"
        r"(?!(?:the\s+)?(?:fires?|wildfires?)\b)"
        r"(?P<place>[a-z][a-z .'-]{1,60}?)\s+(?:fire|wildfire)\b"
        r"(?=\s+(?:and|but|then)\b|"
        r"\s+(?:stuff|details?|information)(?:\s+on\s+(?:the\s+)?map)?[?!.,]*$|"
        r"[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:drive|travel|go)\s+to\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:can|could|may)\s+(?:i|we)\s+leave\s+"
        r"(?!(?:work|school|home|early|the\s+office|my\s+office)\b)"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)\s+"
        r"(?=right\s+now\b|now\b|today\b|tonight\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:should|must)\s+(?:i|we)\s+(?:evacuate|leave)|"
        r"do\s+(?:i|we)\s+need\s+to\s+(?:evacuate|leave))\s+from\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=\s+(?:right\s+now|today|tonight|currently|now)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how\s+far\s+is\s+(?:(?:this|that)(?:\s+selected)?|the\s+selected)\s+"
        r"(?:fire|wildfire|incident|perimeter)|"
        r"(?:what(?:'s|\s+is)\s+the\s+)?distance)\s+from\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=\s+to\s+(?:(?:(?:this|that)(?:\s+selected)?|the\s+selected)\s+"
        r"(?:fire|wildfire|incident|perimeter)|it)\b|"
        r"\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\s+far\s+from\s+(?P<place>[a-z][a-z .'-]{1,80}?)\s+"
        r"is\s+(?:(?:this|that)(?:\s+selected)?|the\s+selected)\s+"
        r"(?:fire|wildfire|incident|perimeter)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\s+(?:far|close)(?:\s+away)?\s+is\s+"
        r"(?:it|(?:(?:this|that)(?:\s+selected)?|the\s+selected)\s+"
        r"(?:fire|wildfire|incident|perimeter))\s+(?:from|to)\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\s+close\s+is\s+(?:the\s+)?(?:nearest|closest)\s+"
        r"(?:fire|wildfire|incident|perimeter)\s+(?:from|to)\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what|which)\s+is\s+(?:the\s+)?(?:nearest|closest)\s+"
        r"(?:(?:official|mapped)\s+){0,2}(?:wildfire\s+|fire\s+)?perimeter\s+"
        r"(?:to|from|near)\s+(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=,|\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:which|what)\s+(?:official\s+)?"
        r"(?:wildfire\s+|fire\s+)?perimeter\s+is\s+"
        r"(?:the\s+)?(?:nearest|closest)(?:\s+(?:to|from))?\s+"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=,|\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:nearest|closest)\s+(?:wildfire\s+|fire\s+)?perimeter\s+"
        r"(?:to|from|near)\s+(?P<place>[a-z][a-z .'-]{1,80}?)"
        r"(?=\s+(?:and|but|then)\b|[?!.,]*$)",
        re.IGNORECASE,
    ),
)

_CONTEXTUAL_PLACE_PATTERNS = (
    re.compile(
        r"\b(?:fires?|wildfires?|(?:fire|wildfire)\s+situation|"
        r"(?:(?:fire|wildfire)\s+)?perimeters?|[a-z]{1,12}fires?)\s+"
        r"(?:(?:is|are)\s+)?"
        r"(?:near|around|round|by|within|in)\s+(?:the\s+)?"
        r"(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bofficial\s+records?(?:\s+are)?\s+"
        r"(?:near|around|within|in|for)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:current\s+|latest\s+)?(?:air\s+quality|aqhi|smoke\s+forecast)\s+"
        r"(?:near|around|within|in|for)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:evacuation|evac)\s+"
        r"(?:information|alerts?(?:\s+and\s+orders?)?|orders?)(?:\s+are)?\s+"
        r"(?:near|around|within|in|for)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what(?:'s|\s+is)\s+)?happening\s+"
        r"(?:near|around|in)\s+(?P<place>[a-z][a-z .'-]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:near|around|round|by|within)\s+(?:the\s+)?"
        r"(?P<place>[a-z][a-z .'-]{1,80}?)\s+(?:fires?|wildfires?)\b",
        re.IGNORECASE,
    ),
)

_TRAILING_CLAUSE = re.compile(
    r"\s+(?:and|but|then)\b.*$",
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
_TRAILING_SELECTED_REFERENCE = re.compile(
    r"\s+(?:to|from)\s+(?:(?:(?:this|that)(?:\s+selected)?|the\s+selected)\s+"
    r"(?:fire|wildfire|incident|perimeter)|it)\b.*$",
    re.IGNORECASE,
)
_TRAILING_ANALYSIS = re.compile(
    r"\s+by\s+(?:hectares?|size|status|regions?|fire[- ]?centres?|geography|distribution)"
    r"(?:\s*(?:/|and)\s*(?:status|regions?|fire[- ]?centres?))*$",
    re.IGNORECASE,
)
_TRAILING_CLOSEST_COMPARISON = re.compile(
    r"\s+is\s+(?:the\s+)?(?:closest|nearest)"
    r"(?:\s+to\s+(?:the\s+)?(?:city|town|community|place))?$",
    re.IGNORECASE,
)
_NON_PLACE_ANALYSIS_WORDS = frozenset(
    {
        "concentrated",
        "concentration",
        "distribution",
        "geographic",
        "geographically",
        "geography",
        "provincial",
        "status",
        "centre",
        "centres",
    }
)
_REJECTED_PLACES = {
    "a wildfire",
    "an emergency",
    "bc",
    "british columbia",
    "bc wildfire service",
    "bcws",
    "effect",
    "the",
    "the province",
    "province",
    "this fire",
    "this incident",
    "this wildfire",
    "any",
    "some",
    "what",
    "there",
    "current",
    "latest",
    "active",
    "national",
    "nationwide",
    "nation",
    "canadian",
    "students",
    "untrusted",
    "preamble",
    "distance",
    "display",
    "map",
    "show",
    "evacuation",
    "alert",
    "order",
    "fire",
    "wildfire",
    "perimeter",
    "mountain",
    "mountains",
    "moutain",
    "one",
    "it",
    "closest",
    "nearest",
    "first",
    "second",
    "third",
    "mountian",
    "forest",
    "bush",
    "grass",
    "wildland",
    "interface",
    "prescribed",
}

_PLACE_ALIASES = {
    "west k": "West Kelowna",
}

_PROVINCE_WIDE_LABELS = frozenset(
    {
        "bc",
        "british columbia",
        "the province",
        "province",
        "bcws",
        "bc wildfire service",
    }
)

# Places FireLens must never geocode as BC communities. The BC Geocoder
# fuzzy-matches anything, so these are rejected before it is asked.
_OUT_OF_PROVINCE_PLACES = frozenset(
    {
        "alberta",
        "saskatchewan",
        "manitoba",
        "ontario",
        "quebec",
        "new brunswick",
        "nova scotia",
        "prince edward island",
        "newfoundland",
        "newfoundland and labrador",
        "yukon",
        "northwest territories",
        "nunavut",
        "calgary",
        "edmonton",
        "banff",
        "jasper",
        "lethbridge",
        "red deer",
        "grande prairie",
        "fort mcmurray",
        "toronto",
        "ottawa",
        "montreal",
        "winnipeg",
        "regina",
        "saskatoon",
        "whitehorse",
        "yellowknife",
        "alaska",
        "washington",
        "washington state",
        "oregon",
        "idaho",
        "montana",
        "california",
        "seattle",
        "portland",
        "spokane",
        "bellingham",
    }
)

_WHOLE_COUNTRY_LABELS = frozenset(
    {"canada", "the rest of canada", "united states", "usa", "us", "america"}
)


def directional_bc_region_label(question: str) -> str | None:
    """Return a broad directional BC label that must never be geocoded.

    The pattern is intentionally limited to a direction directly attached to BC
    or British Columbia. Named places such as North Vancouver and Northern
    Rockies therefore remain eligible community labels.
    """

    match = _DIRECTIONAL_BC_REGION.search(question)
    if match is None:
        return None
    direction = match.group("direction").casefold()
    return "northern B.C." if direction.startswith("north") else "southern B.C."


def _clean_place(candidate: str) -> str | None:
    place = candidate.split(",", maxsplit=1)[0]
    place = _TRAILING_CLAUSE.sub("", place)
    place = _TRAILING_TIME.sub("", place)
    place = _TRAILING_SELECTED_REFERENCE.sub("", place)
    place = _TRAILING_LIVE_NOUNS.sub("", place)
    place = _TRAILING_ANALYSIS.sub("", place)
    place = _TRAILING_CLOSEST_COMPARISON.sub("", place)
    place = place.strip(" .?!'\"")
    modifier = lex.LOCALITY_MODIFIER_PREFIX.match(place)
    if modifier is not None:
        place = modifier.group("place").strip(" .?!'\"")
    if place.casefold().startswith(("on ", "to ", "at ", "near ", "around ", "by ")):
        place = place.split(maxsplit=1)[1].strip()
    if place.casefold().startswith("the "):
        place = place[4:].strip()
    lowered = place.casefold()
    province_with_modifier = re.fullmatch(
        r"(?P<province>bc|b\s*\.?\s*c\s*\.?|british\s+columbia|the\s+province|province)"
        r"(?:\s+(?:active|current|latest|official|reported))?",
        lowered,
    )
    if province_with_modifier is not None:
        return None
    if re.fullmatch(r"b\s*\.?\s*c\s*\.?", lowered):
        return None
    words = frozenset(re.findall(r"[a-z]+", lowered))
    if (
        len(place) < 2
        # A parser match containing a conjunction names alternatives, not one
        # geocodable community. Reject the captured label itself rather than
        # suppressing an entire compound request that may still name one place.
        or bool(re.search(r"\b(?:and|or|versus|vs\.?)\b", place, re.IGNORECASE))
        or lowered in _REJECTED_PLACES
        or bool(words & _NON_PLACE_ANALYSIS_WORDS)
        or lowered.startswith(
            (
                "a ",
                "an ",
                "the ",
                "what ",
                "why ",
                "where ",
                "is ",
                "are ",
                "can ",
                "could ",
                "do ",
                "does ",
                "did ",
                "will ",
                "how ",
                "when ",
                "which ",
                "who ",
                "should ",
                "would ",
                "tell ",
                "please ",
                "distance ",
                "current ",
                "latest ",
                "active ",
                "fires ",
                "wildfires ",
                "my ",
                "our ",
                "your ",
            )
        )
        or lowered.startswith(
            ("show ", "wheres ", "put ", "move ", "focus ", "centre ", "center ", "zoom ")
        )
        or any(token in lowered for token in ("grab-and-go", "go bag", "emergency kit"))
    ):
        return None
    return _PLACE_ALIASES.get(lowered, place)


def is_out_of_province_label(label: str | None) -> bool:
    """True for labels outside British Columbia that must not be geocoded.

    "Vancouver, Canada" stays in-province; "Calgary, Alberta, Canada" and a
    bare "Canada" (a national ask) do not.
    """

    if not isinstance(label, str) or not label.strip():
        return False
    normalized = " ".join(label.split()).casefold().strip(" .,")
    if normalized in _WHOLE_COUNTRY_LABELS:
        return True
    segments = [segment.strip(" .,") for segment in normalized.split(",")]
    while segments and segments[-1] in _WHOLE_COUNTRY_LABELS:
        segments.pop()
    return any(segment in _OUT_OF_PROVINCE_PLACES for segment in segments if segment)


def is_national_scope_question(question: str) -> bool:
    """True when a current-record request explicitly owns non-BC national scope."""

    return requests_non_bc_national_scope(question)


def is_province_wide_label(label: str | None) -> bool:
    """True for BC / province labels that must not be geocoded as a community."""

    if not isinstance(label, str) or not label.strip():
        return False
    normalized = " ".join(label.split()).casefold().strip(" .,")
    for suffix in (", canada", " canada"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip(" .,")
    if re.fullmatch(r"b\s*\.?\s*c\s*\.?", normalized):
        normalized = "bc"
    return normalized in _PROVINCE_WIDE_LABELS


def is_province_wide_question(question: str) -> bool:
    """Return whether a current question explicitly asks for BC-wide scope."""

    return bool(_PROVINCE_WIDE_SCOPE.search(question))


def coarse_location_from_question(question: str) -> LocationInput | None:
    """Return only a user-stated place label; never infer personal coordinates."""

    if _PERSONAL_LOCATION.search(question):
        return None
    if directional_bc_region_label(question) is not None:
        return None
    if any(pattern.search(question) for pattern in MULTI_PLACE_FIRE_COMPARISONS):
        return None

    normalized = lex.normalize_text(question)
    implicit_place = spans.implicit_nearby_location(normalized)
    if implicit_place is not None:
        place = _clean_place(implicit_place)
        if place is not None:
            try:
                return LocationInput(label=place, radius_km=50)
            except ValueError:
                return None

    live_records_closest = lex.LIVE_RECORDS_CLOSEST_SCOPE.search(normalized)
    if live_records_closest is not None:
        place = _clean_place(live_records_closest.group("place"))
        if place is not None:
            try:
                return LocationInput(label=place, radius_km=50)
            except ValueError:
                return None

    closest_size = CLOSEST_FIRE_TRAILING_PLACE.search(normalized)
    if closest_size is not None:
        place = _clean_place(closest_size.group("place"))
        if place is not None:
            try:
                return LocationInput(label=place, radius_km=50)
            except ValueError:
                return None

    compact_radius = lex.COMPACT_RADIUS_SCOPE.search(normalized)
    if compact_radius is not None:
        place = _clean_place(compact_radius.group("place"))
        if place is not None:
            try:
                return LocationInput(
                    label=place,
                    radius_km=float(compact_radius.group("radius")),
                )
            except ValueError:
                return None

    radius = lex.RADIUS_SCOPE.search(normalized)
    if radius is not None:
        place = _clean_place(radius.group("place"))
        if place is not None:
            try:
                return LocationInput(
                    label=place,
                    radius_km=float(radius.group("radius")),
                )
            except ValueError:
                return None

    facets = parse_request_facets(question)
    if facets.only_non_current_fire:
        return None
    for candidate in facets.live_location_candidates:
        place = _clean_place(candidate)
        if place is None:
            continue
        try:
            return LocationInput(label=place, radius_km=50)
        except ValueError:
            return None

    # When the grammar finds a current fire clause, location extraction is
    # intentionally scoped to that clause. A later guidance clause must not
    # lend its place phrase to the live lookup.
    search_texts = (
        tuple(clause.text for clause in facets.live_clauses)
        if facets.has_current_live_fire
        else (question,)
    )
    for search_text in search_texts:
        for pattern in _PLACE_PATTERNS:
            match = pattern.search(search_text)
            if match is None:
                continue
            place = _clean_place(match.group("place"))
            if place is None:
                continue
            try:
                return LocationInput(label=place, radius_km=50)
            except ValueError:
                return None
        for pattern in _CONTEXTUAL_PLACE_PATTERNS:
            match = pattern.search(search_text)
            if match is not None:
                place = _clean_place(match.group("place"))
                if place is not None:
                    try:
                        return LocationInput(label=place, radius_km=50)
                    except ValueError:
                        return None
    return None


def asks_for_personal_location(question: str) -> bool:
    """Return whether answering needs location the user has not stated."""

    return bool(_PERSONAL_LOCATION.search(question))
