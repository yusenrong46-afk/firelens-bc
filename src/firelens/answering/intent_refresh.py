"""Narrow recognition for requests to reload the official wildfire snapshot."""

from __future__ import annotations

from collections.abc import Collection

from firelens.answering import intent_lexicon as lex


def is_refresh_snapshot_tokens(tokens: Collection[str]) -> bool:
    """Return whether normalized tokens request current wildfire data again."""

    token_set = frozenset(tokens)
    return {"refresh", "data"}.issubset(token_set) and bool(token_set & lex.FIRE_WORDS)


def is_live_refresh_request(question: str) -> bool:
    """Return whether a question requests a fresh wildfire-record snapshot."""

    return is_refresh_snapshot_tokens(lex.tokenize(question))
