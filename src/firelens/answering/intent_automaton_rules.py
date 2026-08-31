"""Small predicate rules shared by the deterministic intent automaton."""

from __future__ import annotations

from firelens.answering import intent_lexicon as lex


def is_selected_prediction(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set & {"can", "could", "might", "will"}
        and lex.has_fire(tokens)
        and token_set & lex.PREDICTION_VERBS
        and token_set & lex.PREDICTION_TARGETS
    )
