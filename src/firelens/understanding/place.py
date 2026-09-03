"""One structural place extractor for every FireLens question.

Design: a place is a *name-like span* that follows a spatial or declarative
anchor ("near", "in", "I'm in", "my city is", "map ") or heads a fronted
request ("Kelowna — any fires?", "kelowna fires?"). The span ends at
punctuation, at a closed-class function word, or at a wildfire-domain noun.

Validation is structural: a span must consist of name-like tokens only. Weak
anchors ("in", "at", "from", "to", "of") accept a lowercase span only when the
caller knows the clause asks for current records; strong anchors ("near",
"close to", "I'm in", "map X") accept any casing. Small *data* sets cover
places that must never be geocoded as a community (province labels,
out-of-province places, fire centres). There is deliberately no open-ended
list of rejected English words: the closed class of function words is finite;
the set of content words that might appear after "near" is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from firelens.live_support import official_fire_centre_from_question
from firelens.understanding.place_vocabulary import (
    CIVIC_PREFIXES,
    DIRECTION_WORDS,
    DOMAIN_NOUNS,
    FUNCTION_WORDS,
    OUT_OF_PROVINCE_PLACES,
    PERSONAL_PLACE_NOUNS,
    PLACE_ALIASES,
    PROVINCE_LABELS,
    SCOPE_ADJECTIVES,
    SKIPPABLE_LEAD,
    WHOLE_COUNTRY_LABELS,
)


class PlaceKind(StrEnum):
    """What kind of geography the user actually referred to."""

    COMMUNITY = "community"
    PROVINCE = "province"
    FIRE_CENTRE = "fire_centre"
    PERSONAL = "personal"
    OUT_OF_PROVINCE = "out_of_province"
    DIRECTIONAL_REGION = "directional_region"
    MULTIPLE = "multiple"


@dataclass(frozen=True, slots=True)
class PlaceMention:
    kind: PlaceKind
    label: str | None = None
    radius_km: float | None = None
    labels: tuple[str, ...] = ()
    # Character offsets of the community span inside the normalized question.
    span: tuple[int, int] | None = None

    @property
    def is_community(self) -> bool:
        return self.kind == PlaceKind.COMMUNITY and self.label is not None


# --- anchors and patterns -------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*")
_STRONG_ANCHORS = frozenset(
    {"near", "around", "round", "nearby", "outside", "beside", "toward", "towards",
     "across", "throughout", "arnd", "nr"}
)  # fmt: skip
# Locative prepositions: a lowercase span after them counts inside a
# current-records clause ("fires in kelowna", "fire by kelowna"). Analysis
# axes ("by size", "by geography") are domain nouns and end the span at once.
_WEAK_ANCHORS = frozenset({"in", "at", "by", "from", "on", "into", "through", "along", "past"})
# "to", "of" and "for" are mostly infinitives, partitives and purposes
# ("to worry", "list of fires", "for students"); "nearest"/"closest" usually
# modify a noun ("nearest mapped perimeter"). They name a place only when the
# span is capitalized ("nearest Kelowna") or the previous word makes them locative.
_CAPITALIZED_ONLY_ANCHORS = frozenset({"to", "of", "for", "nearest", "closest"})
_FOR_PREVIOUS = frozenset(
    {"records", "record", "report", "reports", "summary", "overview", "picture", "update",
     "updates", "map", "status", "situation", "conditions", "outlook", "roster", "news",
     "information", "info", "forecast", "data", "fire", "fires", "wildfire", "wildfires",
     "incident", "incidents", "perimeter", "perimeters", "evacuation", "evacuations",
     "alert", "alerts", "order", "orders", "issued", "declared", "lifted", "rescinded",
     "effect"}
)  # fmt: skip
# Verbs whose object is a place ("leave Kelowna", "evacuate Vernon", "I meant Vernon").
_VERB_ANCHORS = frozenset(
    {"leave", "leaving", "evacuate", "evacuating", "flee", "fleeing", "exit", "visit",
     "visiting", "reach", "reaching", "enter", "entering", "approach", "approaching",
     "threaten", "threatening", "hit", "hitting", "affect", "affecting", "meant", "mean"}
)  # fmt: skip
# Auxiliaries: a clause with one has a predicate, so a lowercase word after a
# fire noun is that predicate, not a terse place ("when did this fire start",
# but "fires kelowna" and "how big closest fire kamloops").
_SENTENCE_MARKERS = frozenset(
    {"did", "does", "do", "is", "are", "was", "were", "will", "would", "can", "could",
     "should", "has", "have", "had"}
)  # fmt: skip
_CAPITALIZED_FIRE_NOUNS = frozenset({"Fire", "Wildfire", "Complex", "Blaze"})
# A weak anchor becomes strong when the previous word makes it locative.
_STRENGTHENING_PREVIOUS = frozenset(
    {"close", "closest", "nearest", "next", "north", "south", "east", "west", "outside", "out",
     "heading", "going", "driving", "travelling", "traveling", "flying", "moving", "relocating",
     "evacuating", "up", "over", "down", "back", "here", "live", "living", "based", "staying",
     "located", "visiting", "stuck", "camping", "vacationing", "centre", "center", "focus",
     "zoom", "map", "records", "record", "report", "reports", "summary", "overview", "picture",
     "update", "updates", "status", "situation", "conditions", "outlook", "roster", "news",
     "fire", "fires", "wildfire", "wildfires", "incident", "incidents", "perimeter",
     "perimeters", "evacuation", "evacuations", "alert", "alerts", "order", "orders", "distance"}
)  # fmt: skip
_DECLARATION_PREFIX = re.compile(
    r"\b(?:i(?:'|’)?m|i am|we(?:'|’)?re|we are|i(?:'|’)?ll be|we(?:'|’)?ll be|"
    r"i live|we live|my (?:parents?|family|kids|children|partner|wife|husband|friends?|"
    r"relatives?|son|daughter|mom|mum|dad|grandparents?) (?:are|is|live|lives|stay|stays)|"
    r"currently|right now)\s+(?:(?:up|out|over|down|back)\s+)?$",
    re.IGNORECASE,
)
_DECLARATION_IS = re.compile(
    r"\b(?:my|our)\s+(?:city|town|community|home|house|place|location|address)\s+is\s*$",
    re.IGNORECASE,
)
_PERSONAL = re.compile(
    r"\b(?:near|around|close to|closest to|nearest to|next to|by|where)\s+(?:me|us)\b|"
    r"\b(?:my|our)\s+(?:current\s+)?(?:place|home|house|address|location|area|neighbou?rhood|"
    r"position|spot|town|city|community|street|property)\b|"
    r"\b(?:to|from)\s+(?:me|us)\b|\bwhere\s+(?:i|we)\s+(?:am|are|live|stay)\b|"
    r"\b(?:how\s+far|what\s+distance)\s+(?:am\s+i|are\s+we)\b|\bnear\s+here\b|"
    r"\baround\s+here\b|\bthis\s+area\b|\bin\s+town\b|\bthe\s+(?:area|neighbou?rhood)\b|"
    r"\b(?:in|at)\s+(?:a|the)\s+(?:small|big|little|rural|remote|nearby|quiet)?\s*"
    r"(?:town|city|village|community)\b|"
    r"\b(?:threat|threats|danger)\s+to\s+(?:me|us)\b",
    re.IGNORECASE,
)
_PROVINCE_SCOPE = re.compile(
    r"\b(?:across|throughout|in|of|by|around|for|over)\s+(?:the\s+)?"
    r"(?:whole\s+|entire\s+)?(?:province|b\s*\.?\s*c\s*\.?|british\s+columbia)\b"
    r"(?!\s*wildfire\s+service)"  # "by BC Wildfire Service" names the publisher
    r"|\b(?:province|b\s*\.?\s*c\s*\.?)\s*[- ]wide\b|\bprovincial(?:ly)?\b"
    r"|\ball\s+of\s+(?:bc|b\.c\.|british columbia)\b",
    re.IGNORECASE,
)
_DIRECTIONAL_REGION = re.compile(
    r"(?<!\w)(?P<direction>north(?:ern)?|south(?:ern)?)\s+"
    r"(?:b\s*\.?\s*c(?:\.)?|british\s+columbia)(?!\w)",
    re.IGNORECASE,
)
_RADIUS = re.compile(
    r"(?P<radius>\d{1,3}(?:\.\d+)?)\s*(?:km|kilomet(?:er|re)s?)\b", re.IGNORECASE
)
_FIRE_NUMBER = re.compile(r"^[a-z]\d{4,6}$")
# Up to five tokens: "the West Kelowna evacuation alert" before trimming.
_NAME_SPAN = r"[A-Za-z0-9][A-Za-z0-9'’.\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’.\-]*){0,4}"
_FRONTED_SEPARATED = re.compile(
    rf"^\s*(?P<place>{_NAME_SPAN}?)\s*(?:[—–:,]|\s-\s|\.\s|\s+plus\s+)\s*(?P<head>[A-Za-z']+)",
    re.IGNORECASE,
)
# "kelowna fires?", "is there a Kamloops order?", "West Kelowna evac alert rn".
_FRONTED_FIRES = re.compile(
    rf"^\s*(?P<place>{_NAME_SPAN}?)\s+(?:area\s+)?(?:(?:any|current|active|latest|new)\s+)?"
    r"(?:(?:wild)?fires?|evac(?:uation)?\s+(?:orders?|alerts?)|evacuations?|orders?|alerts?)"
    r"(?:\s+(?:right\s+now|rn|today|tonight|currently|now|status|update|map|situation))?"
    r"\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_FIRES_PLACE = re.compile(
    rf"\b(?:(?:wild)?fires?|evac(?:uation)?\s+(?:alerts?|orders?)|evacuations?|alerts?|orders?)"
    rf"\s+(?P<place>{_NAME_SPAN}?)"
    r"(?:\s+(?:right\s+now|rn|today|tonight|currently|now|atm))?\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_MAP_COMMAND = re.compile(
    rf"^\s*(?:map|show|display)\s+(?:me\s+)?(?:the\s+)?(?P<place>{_NAME_SPAN}?)"
    r"\s*(?:right\s+now|rn|today|now|please)?\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_STATE_PREDICATE = (
    r"(?:on\s+fire|(?:under|on)\s+(?:an?\s+)?(?:evac(?:uation)?\s+)?(?:alert|order)|safe|ok|okay|"
    r"burning|affected|threatened|evacuated|evacuating|in\s+danger|at\s+risk|"
    r"(?:being\s+)?evacuated|still\s+(?:under|on|safe|burning)|"
    r"(?:been\s+)?(?:lift(?:ed)?|rescinded|cancell?ed|downgraded|expanded|extended|"
    r"issued|declared|in\s+effect|over))\b"
)
# "Is Kelowna safe?", "Was the Kelowna evacuation order lifted?"
_SUBJECT_STATE = re.compile(
    rf"^\s*(?:is|are|was|were|has|have|did|does)\s+(?P<place>{_NAME_SPAN}?)\s+{_STATE_PREDICATE}",
    re.IGNORECASE,
)
_DISCOURSE_PREFIX = re.compile(r"^\s*(?P<word>[A-Za-z']+)\s*(?:[:—–]|\s-\s)\s*")
# "whether Kelowna is under order now", "Kelowna is on evacuation alert".
_PLACE_IS_STATE = re.compile(
    rf"\b(?P<place>{_NAME_SPAN}?)\s+(?:is|are|was|were)\s+(?:still\s+|currently\s+|now\s+)?"
    rf"{_STATE_PREDICATE}",
    re.IGNORECASE,
)
_PLACE_FIRE_STATUS = re.compile(
    rf"\b(?:the\s+)?(?P<place>{_NAME_SPAN}?)(?:'|’)?s?\s+(?:wild)?fire\s+"
    r"(?:status|update|situation|report|news|conditions|overview|summary|picture|outlook|"
    r"stuff|details?|info|information|things|map)\b",
    re.IGNORECASE,
)
_CONJUNCTION_JOIN = re.compile(r"\s*,?\s*(?:and|or|vs\.?|versus|&|to)\s+", re.IGNORECASE)
# "..., Kelowna or Vernon?": a comparison pair appended after a comma.
_TRAILING_PAIR = re.compile(
    rf",\s*(?P<first>{_NAME_SPAN}?)\s+(?:or|and|vs\.?|versus|&)\s+(?P<second>{_NAME_SPAN}?)"
    r"\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_PROVINCE_TAIL = re.compile(
    r"\s*,?\s*(?:bc|b\.c\.|b\.c|british columbia|canada)\.?\s*$", re.IGNORECASE
)
_POSSESSIVE = re.compile(r"(?:'|’)s$", re.IGNORECASE)


def normalize_question(text: str) -> str:
    """The text form whose offsets `PlaceMention.span` refers to."""

    text = text.replace("’", "'").replace("—", " — ").replace("–", " – ")
    return " ".join(text.split())


_normalize = normalize_question


def _clean_label(raw: str) -> str | None:
    """Validate a raw span structurally and return a display label."""

    label = _normalize(raw).strip(" ,.;:?!'\"")
    label = _PROVINCE_TAIL.sub("", label).strip(" ,.;:?!'\"")
    lowered = label.casefold()
    for prefix in CIVIC_PREFIXES:
        if lowered.startswith(prefix + " "):
            label = label[len(prefix) + 1 :]
            lowered = label.casefold()
    words = label.split()
    while len(words) > 1 and words[0].casefold() in SKIPPABLE_LEAD:
        words = words[1:]
    if not words or (len(words) == 1 and words[0].casefold() in SKIPPABLE_LEAD):
        return None  # "new fires?" names nothing
    words[-1] = _POSSESSIVE.sub("", words[-1])
    lowered_words = [w.casefold().strip(".'") for w in words]
    joined = " ".join(lowered_words)
    if joined in PLACE_ALIASES:
        return PLACE_ALIASES[joined]
    if any(w in FUNCTION_WORDS or w in DOMAIN_NOUNS for w in lowered_words):
        return None
    if all(w in SCOPE_ADJECTIVES or w in DIRECTION_WORDS for w in lowered_words):
        return None
    if any(_FIRE_NUMBER.match(w) for w in lowered_words):
        return None
    if all(w.isdigit() for w in lowered_words):
        return None
    if len(joined) < 3:
        return None
    return " ".join(words)


def _read_span(text: str, start: int) -> tuple[str, int, int, str | None] | None:
    """Read a name-like span at `start`; return (raw, begin, end, terminator)."""

    begin: int | None = None
    end = start
    count = 0
    position = start
    terminator: str | None = None
    capitalized_head = False
    while count < 4:
        match = _TOKEN.match(text, position)
        if match is None:
            break
        token = match.group(0)
        lowered = _stop_key(token)
        if _is_stop(token):
            if begin is None and lowered in SKIPPABLE_LEAD:
                position = match.end()
                while position < len(text) and text[position] == " ":
                    position += 1
                continue
            terminator = lowered
            break
        if begin is not None and capitalized_head and token[:1].islower():
            break  # "near Kelowna growing": a capitalized name does not continue lowercase
        if begin is None:
            begin = match.start()
            capitalized_head = token[:1].isupper()
        sentence_end = token.endswith(".") and len(token) > 4  # "Kelowna." but not "St."
        end = match.end() - (1 if sentence_end else 0)
        count += 1
        position = match.end()
        while position < len(text) and text[position] == " ":
            position += 1
        if sentence_end or position >= len(text) or text[position] in ',;:?!()"—–':
            break
    if begin is None:
        return None
    if capitalized_head and _names_a_fire(text, end):
        return None  # "the Bald Range Fire", "Pine Fire": a fire name, not a place
    return text[begin:end], begin, end, terminator


def _names_a_fire(text: str, end: int) -> bool:
    """True when a capitalized fire noun follows the span ("Pine Fire")."""

    following = _TOKEN.match(text, end + 1) if end < len(text) and text[end] == " " else None
    return following is not None and following.group(0).strip(".?!") in _CAPITALIZED_FIRE_NOUNS


def _anchor_strength(text: str, match: re.Match[str]) -> str | None:
    word = match.group(0).casefold().strip(".'")
    prefix = text[: match.start()]
    if word in _STRONG_ANCHORS or word in _VERB_ANCHORS:
        return "strong"
    previous = _TOKEN.findall(prefix)
    previous_word = previous[-1].casefold().strip(".'") if previous else ""
    if word == "for":
        # "records for Kelowna" may name a place; "for students" is an audience.
        return "capitalized_only" if previous_word in _FOR_PREVIOUS else None
    if word in _WEAK_ANCHORS or word in _CAPITALIZED_ONLY_ANCHORS:
        if previous_word in _STRENGTHENING_PREVIOUS or _DECLARATION_PREFIX.search(prefix):
            return "strong"
        return "weak" if word in _WEAK_ANCHORS else "capitalized_only"
    if word == "is" and _DECLARATION_IS.search(text[: match.end()]):
        return "strong"
    return None


def _anchored_candidates(text: str, *, live: bool) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    for match in _TOKEN.finditer(text):
        strength = _anchor_strength(text, match)
        if strength is None:
            continue
        start = match.end()
        while start < len(text) and text[start] == " ":
            start += 1
        span = _read_span(text, start)
        if span is None:
            continue
        raw, begin, end, terminator = span
        if terminator in PERSONAL_PLACE_NOUNS and raw == raw.lower():
            continue  # "a small town", "the nearest city": a description, not a name
        if strength == "weak" and not live and raw[:1].islower():
            continue
        if strength == "capitalized_only" and raw[:1].islower():
            continue
        found.append((raw, begin, end))
        joiner = _CONJUNCTION_JOIN.match(text, end)
        if joiner is not None:
            second = _read_span(text, joiner.end())
            # "Kelowna and Vernon" is a pair; "Kelowna and the current air
            # quality" is a second topic: the pair must agree in casing.
            if (
                second is not None
                and second[3] not in PERSONAL_PLACE_NOUNS
                and second[0][:1].isupper() == raw[:1].isupper()
            ):
                found.append((second[0], second[1], second[2]))
    trailing = _TRAILING_PAIR.search(text)
    if trailing is not None and (
        trailing.group("first")[:1].isupper() == trailing.group("second")[:1].isupper()
    ):
        found.append((trailing.group("first"), trailing.start("first"), trailing.end("first")))
        found.append(
            (trailing.group("second"), trailing.start("second"), trailing.end("second"))
        )
    return found


def _fronted_candidates(text: str, *, anchored: bool) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    fronted = _FRONTED_SEPARATED.match(text)
    if fronted is not None and not anchored:
        # "Kelowna — any fires?": a request head (function word or domain noun)
        # must follow the separator, otherwise "Kelowna, BC" style tails match.
        # When the request names its own place ("Easier: fires near Kelowna")
        # the fronted word is a discourse prefix, not a second place.
        head = fronted.group("head").casefold().split("'")[0]
        if head in FUNCTION_WORDS or head in DOMAIN_NOUNS:
            # "For Kelowna, any fires?" names a place; "For students, explain..."
            # names an audience: after trimming a function word the tail must be
            # capitalized.
            tail = _name_tail(
                text, fronted.start("place"), fronted.end("place"), trimmed_needs_case=True
            )
            if tail is not None:
                found.append(tail)
    tokens = _TOKEN.findall(text)
    fires_place = _FIRES_PLACE.search(text)
    if fires_place is not None and not fires_place.group("place")[:1].isupper():
        # "fires kelowna", "evac alert kelowna rn": terse forms may be lowercase;
        # a sentence ("when did this fire start", "why are wildfires dangerous")
        # or a longer topic ("... wildfire policies") is not one.
        lowered = {token.casefold() for token in tokens}
        if len(tokens) > 5 or lowered & _SENTENCE_MARKERS:
            fires_place = None
    # "Please: is there a Kamloops order?": the sentence patterns read the
    # request after a fronted discourse word.
    offset = 0
    prefix = _DISCOURSE_PREFIX.match(text)
    if prefix is not None and _is_stop(prefix.group("word")):
        offset = prefix.end()
    body = text[offset:]
    # "What caused Mountain Fire?" is not "<place> fire": once a leading
    # function word is trimmed the rest must read as a capitalized name.
    for match in (_FRONTED_FIRES.match(body), _SUBJECT_STATE.match(body), fires_place):
        if match is None:
            continue
        shift = 0 if match is fires_place else offset
        tail = _name_tail(
            text,
            match.start("place") + shift,
            match.end("place") + shift,
            trimmed_needs_case=True,
        )
        if tail is not None:
            found.append(tail)
    # "whether Kelowna is under order": the name sits right before the verb;
    # "prove that the community is safe" ends in function words and names nothing.
    place_state = _PLACE_IS_STATE.search(text)
    if place_state is not None:
        tail = _name_tail(
            text,
            place_state.start("place"),
            place_state.end("place"),
            trimmed_needs_case=True,
            adjacent=True,
        )
        if tail is not None:
            found.append(tail)
    # "map kelowna": the object of a map command is the whole remaining text.
    map_command = _MAP_COMMAND.match(body)
    if map_command is not None:
        tail = _name_tail(
            text,
            map_command.start("place") + offset,
            map_command.end("place") + offset,
            allow_trim=False,
        )
        if tail is not None:
            found.append(tail)
    # "show me vernon fire stuff": the command verb is trimmed, the name may be
    # lowercase, but the name must sit right before "fire" ("the latest fire
    # overview" names nothing).
    status = _PLACE_FIRE_STATUS.search(text)
    if status is not None:
        tail = _name_tail(text, status.start("place"), status.end("place"), adjacent=True)
        if tail is not None:
            found.append(tail)
    return found


def _name_tail(
    text: str,
    begin: int,
    end: int,
    *,
    trimmed_needs_case: bool = False,
    allow_trim: bool = True,
    adjacent: bool = False,
) -> tuple[str, int, int] | None:
    """Keep only the run of name-like tokens inside a pattern capture.

    Leading and trailing function words or domain nouns are trimmed ("the
    Kelowna area" -> "Kelowna"); an internal one means the capture is not one
    name ("fires and Kelowna").
    """

    tokens = list(_TOKEN.finditer(text, begin, end))
    while tokens and _is_stop(tokens[0].group(0)):
        tokens.pop(0)
    if adjacent and tokens and _is_stop(tokens[-1].group(0)):
        return None
    while tokens and _is_stop(tokens[-1].group(0)):
        tokens.pop()
    if not tokens:
        return None
    if any(_is_stop(match.group(0)) for match in tokens):
        return None  # "in Glacier National Park" is fine; "fires and Kelowna" is not one name
    trimmed = tokens[0].start() > begin
    if trimmed and not allow_trim:
        return None
    if trimmed and trimmed_needs_case and text[tokens[0].start()].islower():
        return None
    if text[tokens[0].start()].isupper() and _names_a_fire(text, tokens[-1].end()):
        return None  # "the Cariboo Fire" names a fire, not the Cariboo
    return text[tokens[0].start() : tokens[-1].end()], tokens[0].start(), tokens[-1].end()


def _stop_key(token: str) -> str:
    # "I'm", "Kelowna's" and "St." compare by their head word.
    return token.casefold().strip(".'").split("'")[0]


def _is_stop(token: str) -> bool:
    lowered = _stop_key(token)
    return lowered in FUNCTION_WORDS or lowered in DOMAIN_NOUNS or lowered in _VERB_ANCHORS


def _merge_overlapping(
    communities: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Two captures of the same text region are one place; keep the longer one."""

    ordered = sorted(communities, key=lambda item: (item[1], -(item[2] - item[1])))
    merged: list[tuple[str, int, int]] = []
    for label, begin, end in ordered:
        if merged and begin < merged[-1][2]:
            if end - begin > merged[-1][2] - merged[-1][1]:
                merged[-1] = (label, begin, end)
            continue
        merged.append((label, begin, end))
    return merged


def _radius(text: str, before: int) -> float | None:
    window = text[max(0, before - 40) : before]
    matches = list(_RADIUS.finditer(window))
    if not matches:
        return None
    value = float(matches[-1].group("radius"))
    return value if 1 <= value <= 500 else None


@lru_cache(maxsize=4_096)
def extract_place(question: str, *, live: bool = False) -> PlaceMention | None:
    """Return the single geography the user referred to, or None.

    `live=True` tells the extractor that the text is a current-records clause,
    which lets lowercase spans after weak anchors ("fires in kelowna") count.
    """

    text = _normalize(question)
    if not text:
        return None
    fire_centre = official_fire_centre_from_question(text)
    if fire_centre is not None:
        return PlaceMention(kind=PlaceKind.FIRE_CENTRE, label=fire_centre)
    directional = _DIRECTIONAL_REGION.search(text)
    anchored = _anchored_candidates(text, live=live)
    raw_candidates = anchored + _fronted_candidates(text, anchored=bool(anchored))
    communities: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    out_of_province: str | None = None
    province_named = False
    for raw, begin, end in raw_candidates:
        if directional is not None and begin < directional.end() and end > directional.start():
            continue
        label = _clean_label(raw)
        if label is None:
            if _normalize(raw).strip(" ,.;:?!'\"").casefold() in PROVINCE_LABELS:
                province_named = True
            continue
        key = label.casefold()
        if key in PROVINCE_LABELS:
            province_named = True
            continue
        if key in WHOLE_COUNTRY_LABELS or key in PERSONAL_PLACE_NOUNS:
            continue
        if key in OUT_OF_PROVINCE_PLACES:
            out_of_province = label
            continue
        if key in seen:
            continue
        seen.add(key)
        communities.append((label, begin, end))
    if out_of_province is not None and not communities:
        return PlaceMention(kind=PlaceKind.OUT_OF_PROVINCE, label=out_of_province)
    communities = _merge_overlapping(communities)
    if len(communities) > 1:
        return PlaceMention(
            kind=PlaceKind.MULTIPLE, labels=tuple(label for label, *_ in communities)
        )
    if communities:
        label, begin, end = communities[0]
        return PlaceMention(
            kind=PlaceKind.COMMUNITY,
            label=label,
            radius_km=_radius(text, begin),
            span=(begin, end),
        )
    if directional is not None:
        direction = directional.group("direction").casefold()
        return PlaceMention(
            kind=PlaceKind.DIRECTIONAL_REGION,
            label="northern B.C." if direction.startswith("north") else "southern B.C.",
        )
    if _PERSONAL.search(text):
        return PlaceMention(kind=PlaceKind.PERSONAL)
    if province_named or _PROVINCE_SCOPE.search(text):
        return PlaceMention(kind=PlaceKind.PROVINCE, label="British Columbia")
    return None


def is_personal_location(question: str) -> bool:
    """True when the user refers to their own unstated location."""

    return bool(_PERSONAL.search(_normalize(question)))


def is_province_scope(question: str) -> bool:
    """True when the question explicitly asks about all of B.C."""

    return bool(_PROVINCE_SCOPE.search(_normalize(question)))


def is_out_of_province_label(label: str | None) -> bool:
    if not isinstance(label, str) or not label.strip():
        return False
    normalized = " ".join(label.split()).casefold().strip(" .,")
    if normalized in WHOLE_COUNTRY_LABELS:
        return True
    segments = [segment.strip(" .,") for segment in normalized.split(",")]
    while segments and segments[-1] in WHOLE_COUNTRY_LABELS:
        segments.pop()
    return any(segment in OUT_OF_PROVINCE_PLACES for segment in segments if segment)


def is_province_label(label: str | None) -> bool:
    if not isinstance(label, str) or not label.strip():
        return False
    normalized = " ".join(label.split()).casefold().strip(" .,")
    for suffix in (", canada", " canada"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip(" .,")
    if re.fullmatch(r"b\s*\.?\s*c\s*\.?", normalized):
        normalized = "bc"
    return normalized in PROVINCE_LABELS
