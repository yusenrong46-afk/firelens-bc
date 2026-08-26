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
ANALYSIS_WORDS = frozenset(
    {
        "concentrated",
        "concentration",
        "closest",
        "count",
        "counts",
        "density",
        "distributed",
        "distribution",
        "fewest",
        "geographic",
        "geographically",
        "geography",
        "largest",
        "most",
        "nearest",
        "oldest",
        "regions",
    }
)
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
        "policy",
        "prevention",
        "research",
        "risk",
        "safety",
        "science",
        "shape",
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
        "meaning",
        "versus",
        "vs",
    }
)
AUDIENCE_WORDS = frozenset(
    {
        "children",
        "everyone",
        "families",
        "family",
        "homeowners",
        "kids",
        "people",
        "public",
        "residents",
        "students",
        "visitors",
        "workplaces",
    }
)
PLACE_STOPWORDS = frozenset(
    {
        "active",
        "canada",
        "canadian",
        "current",
        "latest",
        "nation",
        "national",
        "nationally",
        "nationwide",
        "now",
        "official",
        "preamble",
        "reported",
        "today",
        "tonight",
        "untrusted",
    }
)
# Colon-fronted prompt labels ("Harder:", "Please:") are discourse, not geography.
DISCOURSE_PREFIX_WORDS = frozenset(
    {
        "actually",
        "also",
        "easier",
        "easiest",
        "example",
        "finally",
        "first",
        "half",
        "harder",
        "hardest",
        "instruction",
        "note",
        "ok",
        "okay",
        "please",
        "prompt",
        "question",
        "second",
        "skip",
        "task",
        "wait",
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
# Commands that can keep a live ask alive inside a mixed guidance clause.
# Excludes noun-like "list"/"find" so packing lists and "where can I find
# guidance" stay reviewed rather than live records.
LIVE_RECORD_ASK_COMMANDS = frozenset(
    {"check", "display", "fetch", "get", "map", "pull", "show"}
)
# Household-prep tokens that authorize static prefetch without claiming a
# reviewed-guidance clause. Downstream must project this set; it is not a
# second request grammar.
PREFETCH_GUIDANCE_TOKENS = (
    GUIDANCE_ACTIONS
    | STRONG_GUIDANCE_TOPICS
    | frozenset({"belongs", "grab", "packing", "preparing", "preparedness"})
)
REQUEST_STARTERS = frozenset(
    {
        "are",
        "can",
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
    }
)

FRONTED_SCOPE = re.compile(
    r"^\s*(?P<place>[a-z][a-z .'-]{1,80}?)\s*"
    r"(?P<separator>[:,\-\u2013\u2014]|\s+plus\s+)\s*(?P<request>.+)$",
    re.IGNORECASE,
)
TRAILING_SCOPE = re.compile(
    r"\b(?:near|around|round|within|in|across|throughout|"
    r"close(?:st)?\s+to|nearest\s+to)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,100})",
    re.IGNORECASE,
)
NEAREST_BARE_SCOPE = re.compile(
    r"\b(?:nearest|closest)\s+(?!to\b|mapped\b|official\b|wildfire\b|fire\b|perimeter\b)"
    r"(?P<place>[a-z][a-z .'-]{1,80})",
    re.IGNORECASE,
)
REPORT_FOR_SCOPE = re.compile(
    r"\b(?:fire|wildfire|incident|perimeter)\s+"
    r"(?:activity|occurrences?|status|update|report|records?|overview|snapshot|"
    r"picture|summary|situation)\s+for\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,100})",
    re.IGNORECASE,
)
COMMAND_OWNED_SCOPE = re.compile(
    r"^\s*(?:please\s+)?(?:bring\s+up\s+|catch\s+(?:me|us)\s+up\s+on\s+|"
    r"show\s+(?:me\s+)?(?:the\s+)?|"
    r"give\s+(?:me\s+)?(?:the\s+)?|display\s+(?:the\s+)?)?"
    r"(?P<place>(?!(?:current|latest|official|national|nationwide|active|"
    r"reported|today|tonight|now)\b)[a-z][a-z .'-]{1,60}?)\s+"
    r"(?:wildfire|fire)\s+"
    r"(?:activity|occurrences?|status|update|report|records?|overview|snapshot|"
    r"picture|summary|situation)\b",
    re.IGNORECASE,
)
MAP_SCOPE = re.compile(
    r"^\s*(?:please\s+)?map\s+(?P<place>[a-z][a-z .'-]{1,80})\s*$",
    re.IGNORECASE,
)
MAP_FOCUS_SCOPE = re.compile(
    r"\b(?:put|move|focus|centre|center|zoom)\s+(?:the\s+)?map\s+"
    r"(?:on|to|at|near|around)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,80})",
    re.IGNORECASE,
)
UNDER_ALERT_SCOPE = re.compile(
    r"\b(?:is|are|whether)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,60}?)\s+"
    r"(?:is\s+|are\s+)?(?:under|on)\s+(?:an?\s+)?"
    r"(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)\b",
    re.IGNORECASE,
)
EXISTENTIAL_EVACUATION_SCOPE = re.compile(
    r"\b(?:is|are)\s+there\s+(?:an?\s+)?"
    r"(?:"
    r"(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)\s+"
    r"(?:for|in|near|around)\s+(?:the\s+)?(?P<place_after>[a-z][a-z .'-]{1,60})"
    r"|"
    r"(?P<place_before>[a-z][a-z .'-]{1,60}?)\s+"
    r"(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)"
    r")\b",
    re.IGNORECASE,
)
TIME_TAIL = re.compile(
    r"\s+(?:right\s+now|currently|current|latest|today|tonight|now|at\s+present|"
    r"at\s+the\s+moment|this\s+(?:morning|afternoon|evening|week)|"
    r"last\s+(?:season|summer|year|week)|yesterday)\b.*$",
    re.IGNORECASE,
)
TOP_LEVEL_SEPARATOR = re.compile(
    r"\s*(?:\+|[?;](?=\s|$)|\.(?=\s|$))\s*|"
    r"\s*(?:,\s*)?(?:and|also|plus|but|then|with)\s+",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize Unicode without changing reader-visible clause punctuation."""

    return unicodedata.normalize("NFKC", text).replace("’", "'")


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
