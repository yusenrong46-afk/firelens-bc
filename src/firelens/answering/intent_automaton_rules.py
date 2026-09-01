"""Small predicate rules shared by the deterministic intent automaton."""

from __future__ import annotations

import re

from firelens.answering import intent_lexicon as lex
from firelens.answering.intent_guidance import (
    is_stable_evacuation_action as _is_stable_evacuation_action,
)
from firelens.contracts import LiveResultKind

_ALL_THREE_OFFICIAL_RECORD_TYPES = re.compile(
    r"\b(?:open|show|display|list|check)\b.{0,48}"
    r"\ball\s+three\b.{0,48}\bofficial\s+record\s+types?\b",
    re.IGNORECASE,
)


def is_selected_prediction(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set & {"can", "could", "might", "will"}
        and lex.has_fire(tokens)
        and token_set & lex.PREDICTION_VERBS
        and token_set & lex.PREDICTION_TARGETS
    )


def is_stable_evacuation_action(tokens: tuple[str, ...]) -> bool:
    """Keep the new stable-action rule beside other bounded parser predicates."""

    return _is_stable_evacuation_action(tokens)


def is_universal_distance(tokens: tuple[str, ...]) -> bool:
    """Reject requests for one distance rule applied to everyone or every fire."""

    token_set = frozenset(tokens)
    return bool(
        token_set & {"distance", "radius", "far"}
        and (
            token_set & {"everyone", "everybody", "universal"}
            or lex.has_phrase(tokens, ("every", "resident"))
            or lex.has_phrase(tokens, ("every", "family"))
            or lex.has_phrase(tokens, ("every", "wildfire"))
            or lex.has_phrase(tokens, ("every", "person"))
            or lex.has_phrase(tokens, ("one", "exact"))
        )
    )


def all_three_official_record_layers(text: str) -> tuple[LiveResultKind, ...]:
    """Return the complete bounded official record set only for its explicit request."""

    if not _ALL_THREE_OFFICIAL_RECORD_TYPES.search(text):
        return ()
    return (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
        LiveResultKind.EVACUATION,
    )
