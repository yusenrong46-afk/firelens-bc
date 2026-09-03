"""Place understanding for live-record questions.

Thin adapter over :mod:`firelens.understanding.place`, which is the only place
extractor in FireLens. The public names here are kept because many modules and
tests consume them; none of them re-parses the question with its own grammar.
"""

from __future__ import annotations

import re
from functools import lru_cache

from firelens.answering import intent_lexicon as lex
from firelens.answering.intent_automaton import ClauseIntentKind, parse_request_intent
from firelens.live_contracts import LocationInput
from firelens.understanding.place import (
    PlaceKind,
    PlaceMention,
    extract_place,
    is_out_of_province_label,
    is_personal_location,
    is_province_label,
    is_province_scope,
)

__all__ = [
    "asks_for_personal_location",
    "coarse_location_from_question",
    "directional_bc_region_label",
    "is_multi_place_fire_comparison",
    "is_national_scope_question",
    "is_out_of_province_label",
    "is_province_wide_label",
    "is_province_wide_question",
    "place_mention_for_question",
]


_NON_TOPICAL_KINDS = frozenset(
    {ClauseIntentKind.REVIEWED_GUIDANCE, ClauseIntentKind.PRODUCT_HELP}
)
_DISTANCE_SEMANTICS = re.compile(
    r"\b(?:closest|closer|nearest|nearer|farthest|furthest|how\s+far|distance|km|kilomet)",
    re.IGNORECASE,
)


def _is_expository(text: str) -> bool:
    tokens = lex.tokenize(text)
    return bool(frozenset(tokens) & lex.EXPOSITORY_WORDS) or lex.has_phrase(
        tokens, ("tell", "me", "about")
    )


@lru_cache(maxsize=2_048)
def place_mention_for_question(question: str) -> PlaceMention | None:
    """Return the one geography the question refers to.

    Current-record clauses are searched first (a lowercase "fires in kelowna"
    counts there); a guidance clause never lends its noun phrase to the live
    lookup ("what belongs in a grab-and-go bag" has no place).
    """

    parsed = parse_request_intent(question)
    live_clauses = [clause for clause in parsed.clauses if clause.is_live]
    if not live_clauses:
        if any(clause.is_noncurrent_fire for clause in parsed.clauses):
            return None  # "the 2003 Okanagan Mountain fire" is history, not a lookup
        # "Can I leave Kelowna now?", "What will the wind do near the Kelowna
        # fires?": not a records request, but the stated place keeps the boundary
        # or handoff specific. Guidance and expository clauses lend nothing
        # ("Kamloops: explain wildfire ecology" has no live scope).
        for clause in parsed.clauses:
            if clause.kind in _NON_TOPICAL_KINDS or _is_expository(clause.text):
                continue
            mention = extract_place(clause.text, live=False)
            if mention is not None:
                return mention
        return None
    for clause in live_clauses:
        mention = extract_place(clause.text, live=True)
        if mention is not None:
            return mention
    # "I'm in Kelowna. Are there any fires nearby?": a place stated in a context
    # clause applies to the live request. A guidance clause's place does not.
    for clause in parsed.clauses:
        if clause.is_live or clause.kind == ClauseIntentKind.REVIEWED_GUIDANCE:
            continue
        mention = extract_place(clause.text, live=False)
        if mention is not None:
            return mention
    if len(parsed.clauses) == 1:
        return extract_place(question, live=False)
    return None


def coarse_location_from_question(question: str) -> LocationInput | None:
    """Return only a user-stated community label; never infer personal coordinates."""

    mention = place_mention_for_question(question)
    if mention is None or not mention.is_community:
        return None
    try:
        return LocationInput(
            label=mention.label, radius_km=mention.radius_km if mention.radius_km else 50.0
        )
    except ValueError:
        return None


def is_multi_place_fire_comparison(question: str) -> bool:
    """True when one request names two independent distance origins.

    "Which city has the closer fire, Kelowna or Vernon?" needs two distance
    calculations FireLens does not run in one turn. "Wildfires in the Okanagan
    vs Kootenays" names two regions without distance semantics; the live
    analysis path explains that regional classification is not validated.
    """

    mention = place_mention_for_question(question)
    return (
        mention is not None
        and mention.kind == PlaceKind.MULTIPLE
        and bool(_DISTANCE_SEMANTICS.search(question))
    )


def directional_bc_region_label(question: str) -> str | None:
    """Return a broad directional BC label that must never be geocoded."""

    mention = extract_place(question)
    if mention is not None and mention.kind == PlaceKind.DIRECTIONAL_REGION:
        return mention.label
    return None


def is_national_scope_question(question: str) -> bool:
    """True when a current-record request explicitly owns non-BC national scope."""

    return parse_request_intent(question).requests_non_bc_scope


def is_province_wide_label(label: str | None) -> bool:
    return is_province_label(label)


def is_province_wide_question(question: str) -> bool:
    """Return whether a current question explicitly asks for BC-wide scope."""

    return is_province_scope(question)


def asks_for_personal_location(question: str) -> bool:
    """Return whether answering needs a location the user has not stated."""

    return is_personal_location(question)
