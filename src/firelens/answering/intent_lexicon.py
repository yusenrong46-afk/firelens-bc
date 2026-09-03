"""Immutable lexical data for the typed request-intent automaton."""

from __future__ import annotations

import re
import unicodedata

TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

CURRENT_PHRASES = (
    ("right", "now"),
    ("at", "present"),
    ("at", "the", "moment"),
    ("up", "to", "date"),
    ("this", "morning"),
    ("this", "afternoon"),
    ("this", "evening"),
    ("this", "week"),
)
CURRENT_WORDS = frozenset(
    {
        "active",
        "current",
        "currently",
        "latest",
        "listed",
        "reported",
        "today",
        "tonight",
        "now",
    }
)
NONCURRENT_PHRASES = (
    ("last", "season"),
    ("last", "summer"),
    ("last", "year"),
    ("last", "week"),
    ("next", "week"),
    ("next", "month"),
    ("in", "the", "past"),
)
NONCURRENT_WORDS = frozenset(
    {
        "forecast",
        "forecasted",
        "forecasting",
        "future",
        "historic",
        "historical",
        "historically",
        "history",
        "past",
        "previous",
        "previously",
        "tomorrow",
        "will",
        "yesterday",
    }
)

FIRE_WORDS = frozenset(
    {"fire", "fires", "wildfire", "wildfires", "incident", "incidents", "burning"}
)
PERIMETER_WORDS = frozenset({"perimeter", "perimeters"})
EVACUATION_WORDS = frozenset(
    {"evacuation", "evacuations", "evac", "alert", "alerts", "order", "orders"}
)
RECORD_COMMANDS = frozenset(
    {
        "check",
        "compare",
        "display",
        "fetch",
        "find",
        "give",
        "get",
        "list",
        "map",
        "pull",
        "show",
        "tell",
    }
)
RECORD_NOUNS = frozenset(
    {
        "activity",
        "briefing",
        "count",
        "counts",
        "details",
        "information",
        "map",
        "overview",
        "picture",
        "record",
        "records",
        "report",
        "reports",
        "roster",
        "situation",
        "snapshot",
        "status",
        "update",
        "updates",
    }
)
SCOPE_WORDS = frozenset({"across", "around", "in", "near", "nearby", "throughout", "within"})
EXPOSITORY_WORDS = frozenset(
    {
        "affect",
        "awareness",
        "behave",
        "behavior",
        "behaviour",
        "causes",
        "change",
        "define",
        "definition",
        "describe",
        "ecology",
        "ecosystem",
        "ecosystems",
        "events",
        "explain",
        "influence",
        "legislation",
        "meaning",
        "mistake",
        "mistakes",
        "policy",
        "prevention",
        "research",
        "risk",
        "safety",
        "science",
        "shape",
        "story",
        "stories",
        "poem",
        "poems",
        "fiction",
        "training",
    }
)
CONTEXT_ONLY_WORDS = frozenset(
    {"air", "aqhi", "highway", "highways", "road", "roads", "smoke", "weather", "wind"}
)
UI_OBJECTS = frozenset({"marker", "markers", "pin", "pins"})
UI_ACTIONS = frozenset({"add", "create", "delete", "drop", "move", "place", "remove"})

GUIDANCE_PHRASES = (
    ("emergency", "kit"),
    ("grab", "and", "go"),
    ("go", "bag"),
    ("packing", "checklist"),
    ("packing", "list"),
    ("smoke", "preparedness"),
    ("smoke", "preparation"),
    ("smoke", "readiness"),
    ("emergency", "plan"),
    ("emergency", "planning"),
    ("family", "plan"),
    ("household", "plan"),
    ("home", "ignition", "zone"),
    ("return", "after", "evacuation"),
)
DEFINITION_WORDS = frozenset(
    {
        "basics",
        "comparison",
        "definition",
        "definitions",
        "differ",
        "difference",
        "different",
        "distinction",
        "mean",
        "means",
        "meaning",
        "versus",
        "vs",
    }
)
FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "are",
        "be",
        "by",
        "for",
        "from",
        "is",
        "of",
        "on",
        "the",
        "to",
        "was",
        "were",
    }
)
NATIONAL_SCOPE_PHRASES = (
    ("across", "the", "nation"),
    ("throughout", "the", "nation"),
    ("atlantic", "to", "the", "pacific"),
    ("atlantic", "to", "pacific"),
    ("coast", "to", "coast"),
    ("across", "canada"),
    ("throughout", "canada"),
    ("in", "canada"),
    ("all", "of", "canada"),
    ("rest", "of", "canada"),
    ("across", "the", "country"),
    ("throughout", "the", "country"),
    ("every", "province"),
    ("all", "provinces"),
    ("all", "ten", "provinces"),
    ("all", "10", "provinces"),
    ("canada", "wide"),
    ("nation", "wide"),
)
NATIONAL_PARK_PHRASES = (("national", "park"), ("national", "forest"))
PREDICTION_VERBS = frozenset({"affect", "reach", "spread", "threaten"})
PREDICTION_TARGETS = frozenset(
    {
        "community",
        "home",
        "house",
        "me",
        "my",
        "neighbourhood",
        "neighborhood",
        "our",
        "property",
        "us",
    }
)
GUIDANCE_WORDS = frozenset(
    {
        "advice",
        "basics",
        "checklist",
        "contents",
        "definition",
        "definitions",
        "firesmart",
        "guidance",
        "kit",
        "packing",
        "precaution",
        "precautions",
        "preparedness",
        "readiness",
        "sprinkler",
        "sprinklers",
        "tips",
    }
)
STRONG_GUIDANCE_TOPICS = frozenset(
    {"firesmart", "kit", "precaution", "precautions", "sprinkler", "sprinklers"}
)
GOVERNED_GUIDANCE_TOPICS = frozenset(
    {
        "alert",
        "alerts",
        "emergency",
        "evac",
        "evacuation",
        "family",
        "fire",
        "home",
        "house",
        "household",
        "order",
        "orders",
        "property",
        "smoke",
        "wildfire",
    }
)
GUIDANCE_ACTIONS = frozenset({"pack", "prepare", "protect", "reduce"})
# Live-record commands inside mixed guidance; excludes noun-like list/find.
LIVE_RECORD_ASK_COMMANDS = frozenset(
    {"check", "display", "fetch", "get", "map", "pull", "show"}
)
# Household-prep tokens for static prefetch; not a second request grammar.
PREFETCH_GUIDANCE_TOKENS = (
    GUIDANCE_ACTIONS
    | STRONG_GUIDANCE_TOPICS
    | frozenset({"belongs", "grab", "packing", "preparing", "preparedness"})
)
REQUEST_STARTERS = frozenset(
    {
        "am",
        "are",
        "can",
        "should",
        "must",
        "who",
        "will",
        "would",
        "check",
        "compare",
        "could",
        "define",
        "describe",
        "display",
        "do",
        "does",
        "explain",
        "fetch",
        "find",
        "give",
        "how",
        "is",
        "list",
        "map",
        "outline",
        "pull",
        "say",
        "show",
        "summarize",
        "tell",
        "what",
        "when",
        "where",
        "which",
        "why",
        "write",
    }
)

FRONTED_SCOPE = re.compile(
    r"^\s*(?P<place>[a-z][a-z .'-]{1,80}?)\s*"
    r"(?P<separator>[:,\-\u2013\u2014]|\s+plus\s+)\s*(?P<request>.+)$",
    re.IGNORECASE,
)
COMPACT_RADIUS_SCOPE = re.compile(
    r"^\s*(?:show|list|find|check)?\s*(?:current\s+|active\s+)?"
    r"(?:wildfires?|fires?|incidents?)\s+"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)\s+"
    r"(?P<radius>\d+(?:\.\d+)?)\s*"
    r"(?:km|kilomet(?:er|re)s?)[?!.,]*\s*$",
    re.IGNORECASE,
)
LIVE_RECORDS_CLOSEST_SCOPE = re.compile(
    r"\b(?:list|show|display|find|get|check)\s+(?:the\s+)?"
    r"(?:(?:two|three|2|3)\s+)?"
    r"(?:live|official|current)\s+records?\s+(?:closest|nearest)\s+"
    r"(?:to|from|near)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)"
    r"(?=[,;:.?!]|$)",
    re.IGNORECASE,
)
FIRST_PERSON_PLACE = re.compile(
    r"\b(?:i(?:['’]m|\s+am)|we(?:['’]re|\s+are))\s+"
    r"(?:currently\s+)?in\s+(?P<place>[a-z][a-z .'-]{1,80}?)"
    r"(?=[,;:.?!]|$)",
    re.IGNORECASE,
)
THIRD_PARTY_PLACE = re.compile(
    r"\b(?:my|our)\s+(?:parents?|family|friends?|children|kids|relatives?)\s+"
    r"(?:are|is|live|lives|stay|stays)\s+(?:currently\s+)?in\s+"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)"
    r"(?=[,;:.?!]|$)",
    re.IGNORECASE,
)
NEARBY_INFORMATION_REQUEST = re.compile(
    r"\b(?:anything|something|what(?:['’]s|\s+is))\s+"
    r"(?:happening\s+)?nearby\b",
    re.IGNORECASE,
)
NEAR_PLACE_INFORMATION_REQUEST = re.compile(
    r"\b(?:"
    r"(?:is\s+there\s+)?(?:anything|something)\s+"
    r"(?:(?:i|we)\s+should\s+)?(?:know\s+about|happening|going\s+on)|"
    r"what(?:['’]s|\s+is)\s+(?:happening|going\s+on)"
    r")\s+(?:near|around)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)"
    r"(?=[,;:.?!]|$)",
    re.IGNORECASE,
)
# A bare comma also separates clauses when what follows reads as a new request
# ("how many fires, what changed since yesterday"); `_looks_like_clause` decides.
# A period ends a request only when it does not close an abbreviation such as
# "B.C.", "U.S.", "St.", "Mt.", "e.g." ("What records does B.C. list?").
TOP_LEVEL_SEPARATOR = re.compile(
    r"\s*(?:\+|[?;](?=\s|$)|(?<!\b[A-Za-z])(?<!\b[A-Za-z]\.[A-Za-z])"
    r"(?<!\b[SsMmFf]t)(?<!\be\.g)(?<!\bi\.e)\.(?=\s|$))\s*|"
    r"\s*(?:,\s*)?(?:and|also|plus|but|then|with)\s+|"
    r"\s*,\s*(?=\S)",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize Unicode without changing reader-visible clause punctuation."""

    normalized = unicodedata.normalize("NFKC", text).replace("’", "'")
    # Expand only narrow, unambiguous compressed-chat forms; this is not fuzzy correction.
    normalized = re.sub(r"\barnd\b", "around", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\brn\b", "right now", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmoutain\b", "mountain", normalized, flags=re.IGNORECASE)
    return normalized


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize the bounded grammar and normalize common contractions."""

    normalized = normalize_text(text).casefold()
    normalized = re.sub(r"\bb\s*\.\s*c\.?\b", "bc", normalized)
    normalized = re.sub(r"\bwhere(?:'s|s)\b", "where is", normalized)
    normalized = re.sub(r"\bwhat's\b", "what is", normalized)
    tokens: list[str] = []
    for token in TOKEN.findall(normalized):
        if token.endswith("'s") and len(token) > 2:
            tokens.append(token[:-2])
        else:
            tokens.append(token)
    return tuple(tokens)


def is_fire_token(token: str) -> bool:
    """Recognize governed fire nouns, including named compound-fire typos."""

    if token in FIRE_WORDS:
        return True
    return bool(
        len(token) >= 6
        and (token.endswith("fire") or token.endswith("fires"))
        and token not in {"bonfire", "bonfires", "campfire", "campfires"}
    )


def has_fire(tokens: tuple[str, ...]) -> bool:
    return any(is_fire_token(token) for token in tokens)


def has_phrase(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(
        tokens[index : index + width] == phrase for index in range(len(tokens) - width + 1)
    )


def has_any_phrase(tokens: tuple[str, ...], phrases: tuple[tuple[str, ...], ...]) -> bool:
    return any(has_phrase(tokens, phrase) for phrase in phrases)
