"""Location and national-span helpers used by the typed intent automaton.

Place spans come from :mod:`firelens.understanding.place`; this module only
adapts them to the parser's clause model and owns the national-scope check.
"""

from __future__ import annotations

import re

from firelens.answering import intent_lexicon as lex
from firelens.answering.intent_automaton_types import RecordOperation
from firelens.understanding.place import (
    PlaceKind,
    PlaceMention,
    extract_place,
    normalize_question,
)

_LIVE_PLACE_KINDS = frozenset({PlaceKind.COMMUNITY, PlaceKind.PERSONAL, PlaceKind.FIRE_CENTRE})
_PLACE_STATE_WORDS = frozenset(
    {
        "safe",
        "ok",
        "okay",
        "threatened",
        "evacuated",
        "evacuating",
        "affected",
        "danger",
        "risk",
    }
)
# Explanatory or figurative sentences ("why is fire near homes dangerous",
# "my workload is a fire near deadline") are not record requests.
_NON_REQUEST_MARKERS = frozenset(
    {"why", "how", "my", "our", "your", "his", "her", "their", "like", "as", "if", "because",
     "metaphor", "means", "meaning"}
)  # fmt: skip
_SINGULAR_FIRE_NOUNS = frozenset({"fire", "wildfire", "blaze"})
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*")
_FRONTED_PLACE = re.compile(
    r"^\s*(?P<place>[A-Za-z][A-Za-z0-9'’.\-]*(?:\s+[A-Za-z][A-Za-z0-9'’.\-]*){0,3})\s*"
    r"(?P<separator>[—–:,]|\s-\s|\.\s|\s+plus\s+)",
    re.IGNORECASE,
)


def _canada_is_country_qualifier(tokens: tuple[str, ...]) -> bool:
    try:
        index = tokens.index("canada")
    except ValueError:
        return False
    if index == 0:
        return False
    previous = tokens[index - 1]
    if previous in lex.SCOPE_WORDS or previous in lex.FUNCTION_WORDS:
        return False
    if previous in lex.REQUEST_STARTERS or previous in lex.RECORD_COMMANDS:
        return False
    return previous not in lex.FIRE_WORDS and previous not in lex.RECORD_NOUNS


def requests_non_bc_scope(tokens: tuple[str, ...]) -> bool:
    """True only for an explicit non-BC national *record* span."""

    token_set = frozenset(tokens)
    national_park = lex.has_any_phrase(tokens, lex.NATIONAL_PARK_PHRASES)
    if lex.has_any_phrase(tokens, lex.NATIONAL_SCOPE_PHRASES):
        return True
    if token_set & {"nationwide", "nationally"}:
        return True
    if (
        not national_park
        and "national" in token_set
        and (lex.has_fire(tokens) or bool(token_set & lex.RECORD_NOUNS))
    ):
        return True
    if "canadian" in token_set and (lex.has_fire(tokens) or bool(token_set & lex.RECORD_NOUNS)):
        return True
    if "canada" in token_set and (lex.has_fire(tokens) or bool(token_set & lex.RECORD_NOUNS)):
        return not _canada_is_country_qualifier(tokens)
    return False


def implied_live_place(text: str, tokens: tuple[str, ...]) -> PlaceMention | None:
    """A stated place that makes a verb-less short clause a current-records request.

    "wildfire near kelowna?", "fires kelowna", "Is Fort St. John safe?" name a
    place; "write a wildfire haiku" only has a compound noun after "wildfire".
    """

    if len(tokens) > 8 or frozenset(tokens) & _NON_REQUEST_MARKERS:
        return None
    mention = extract_place(text, live=True)
    if mention is None or mention.kind not in _LIVE_PLACE_KINDS:
        return None
    if mention.span is not None and len(tokens) > 2:
        before = _WORD.findall(normalize_question(text)[: mention.span[0]])
        if before and before[-1].casefold() in _SINGULAR_FIRE_NOUNS:
            return None
    return mention


def implied_place_operation(
    text: str, tokens: tuple[str, ...]
) -> tuple[RecordOperation | None, bool]:
    """(fire operation, evacuation) implied by a stated place in a verb-less clause.

    "wildfire near kelowna?" lists fires; "Is Fort St. John safe?" checks every
    official layer for that place (the personal-safety boundary is added
    downstream). Anything else implies nothing.
    """

    if implied_live_place(text, tokens) is None:
        return None, False
    token_set = frozenset(tokens)
    if token_set & _PLACE_STATE_WORDS and not token_set & lex.DEFINITION_WORDS:
        return RecordOperation.LIST, True  # "Is Kelowna safe from the fire?" needs every layer
    if lex.has_fire(tokens):
        return RecordOperation.LIST, False
    return None, False


def implicit_nearby_location(question: str) -> str | None:
    """Return a stated place for a bounded FireLens-context nearby request.

    "I'm in Kelowna. Anything nearby I should know about?" names no fire word,
    but inside FireLens a nearby request with a stated place is a live request.
    """

    if (
        lex.NEARBY_INFORMATION_REQUEST.search(question) is None
        and lex.NEAR_PLACE_INFORMATION_REQUEST.search(question) is None
    ):
        return None
    mention = extract_place(question, live=True)
    if mention is None or not mention.is_community:
        return None
    return mention.label


def is_context_location_declaration(text: str) -> bool:
    """Return whether a clause only supplies a place for a nearby follow-up."""

    normalized = text.strip(" ,.?;+")
    return bool(
        lex.FIRST_PERSON_PLACE.fullmatch(normalized)
        or lex.THIRD_PARTY_PLACE.fullmatch(normalized)
    )


def location_candidate(text: str, *, is_live: bool) -> str | None:
    """Community label for one clause, or None."""

    if not is_live:
        return None
    mention = extract_place(text, live=True)
    if mention is None or mention.kind != PlaceKind.COMMUNITY:
        return None
    return mention.label


def fronted_scope_for_question(question: str) -> str | None:
    """Return a leading place label such as "Kelowna — any fires?"."""

    match = _FRONTED_PLACE.match(question)
    if match is None:
        return None
    mention = extract_place(question, live=True)
    if mention is None or not mention.is_community or mention.span is None:
        return None
    if mention.span[0] < match.start("place") or mention.span[1] > match.end("place"):
        return None
    return mention.label


def plausible_fronted_scope(candidate: str) -> bool:
    """True when the whole candidate is one place name ("Nelson", not "Show fires")."""

    cleaned = " ".join(candidate.split()).strip(" ,.;:?!'\"")
    mention = extract_place(f"{cleaned} — any fires?", live=True)
    if mention is None or not mention.is_community or mention.span is None:
        return False
    return mention.span[0] == 0 and mention.span[1] >= len(cleaned) - 1
