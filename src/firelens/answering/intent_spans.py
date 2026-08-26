"""Location and national-span helpers owned by the typed intent automaton.

Downstream routing must not call this module.  It exists only so the parser can
stay under the production size bound while remaining the sole owner of those
fields.
"""

from __future__ import annotations

import re

from firelens.answering import intent_lexicon as lex


def clean_fronted_scope(candidate: str) -> str:
    candidate = candidate.strip()
    candidate = re.sub(r"^(?:for|near|around|in)\s+", "", candidate, flags=re.IGNORECASE)
    return candidate.strip()


def plausible_fronted_scope(candidate: str) -> bool:
    cleaned = clean_fronted_scope(candidate)
    tokens = lex.tokenize(cleaned)
    token_set = frozenset(tokens)
    return bool(
        tokens
        and len(tokens) <= 5
        and tokens[0] not in lex.REQUEST_STARTERS
        and not token_set
        & (
            lex.FIRE_WORDS
            | lex.RECORD_NOUNS
            | lex.AUDIENCE_WORDS
            | lex.PLACE_STOPWORDS
            | lex.DISCOURSE_PREFIX_WORDS
            | {"blank", "empty", "map"}
        )
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
    if lex.has_any_phrase(tokens, lex.NATIONAL_PARK_PHRASES):
        national_park = True
    else:
        national_park = False
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


def _rejected_place(candidate: str) -> bool:
    tokens = lex.tokenize(candidate)
    token_set = frozenset(tokens)
    if not tokens:
        return True
    if token_set & (lex.AUDIENCE_WORDS | lex.PLACE_STOPWORDS | lex.DISCOURSE_PREFIX_WORDS):
        return True
    if re.search(r"\b(?:and|or|versus|vs)\b", candidate, flags=re.IGNORECASE):
        return True
    return False


def _noisy_place(candidate: str) -> bool:
    token_set = frozenset(lex.tokenize(candidate))
    return bool(
        token_set
        & (lex.FIRE_WORDS | lex.PERIMETER_WORDS | lex.RECORD_NOUNS | {"mapped", "official"})
    )


def _finalize_place(candidate: str) -> str | None:
    candidate = lex.TIME_TAIL.sub("", candidate).strip(" ,.?;+'")
    candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.IGNORECASE)
    if not candidate:
        return None
    if _noisy_place(candidate):
        salvaged = re.search(
            r"\b(?:to|from|near)\s+(?P<place>[a-z][a-z .'-]{1,80})$",
            candidate,
            flags=re.IGNORECASE,
        )
        if salvaged is None:
            return None
        candidate = salvaged.group("place").strip(" ,.?;+'")
        candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.IGNORECASE)
    if not candidate or _noisy_place(candidate) or _rejected_place(candidate):
        return None
    return candidate


def _named_place_from_text(text: str) -> str | None:
    alerted = lex.UNDER_ALERT_SCOPE.search(text)
    if alerted is not None:
        candidate = _finalize_place(alerted.group("place"))
        if candidate:
            return candidate
    mapped_focus = lex.MAP_FOCUS_SCOPE.search(text)
    if mapped_focus is not None:
        candidate = _finalize_place(mapped_focus.group("place"))
        if candidate:
            return candidate
    existential = lex.EXISTENTIAL_EVACUATION_SCOPE.search(text)
    if existential is not None:
        raw = existential.group("place_after") or existential.group("place_before")
        candidate = _finalize_place(raw or "")
        if candidate:
            return candidate
    matches = tuple(
        (
            *lex.TRAILING_SCOPE.finditer(text),
            *lex.REPORT_FOR_SCOPE.finditer(text),
            *lex.NEAREST_BARE_SCOPE.finditer(text),
        )
    )
    if matches:
        candidate = _finalize_place(matches[-1].group("place"))
        if candidate:
            return candidate
    mapped = lex.MAP_SCOPE.search(text)
    if mapped is not None:
        candidate = _finalize_place(mapped.group("place"))
        if candidate:
            return candidate
    owned = lex.COMMAND_OWNED_SCOPE.search(text)
    if owned is not None:
        candidate = owned.group("place").strip()
        candidate = re.sub(
            r"^(?:bring\s+up\s+|catch\s+(?:me|us)\s+up\s+on\s+|"
            r"show\s+(?:me\s+)?(?:the\s+)?|give\s+(?:me\s+)?(?:the\s+)?|"
            r"display\s+(?:the\s+)?)",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        finalized = _finalize_place(candidate)
        if finalized:
            return finalized
    return None


def location_candidate(text: str, *, is_live: bool) -> str | None:
    if not is_live:
        return None
    named = _named_place_from_text(text)
    if named:
        return named
    fronted = lex.FRONTED_SCOPE.search(text)
    if fronted is None:
        return None
    candidate = clean_fronted_scope(fronted.group("place"))
    if not plausible_fronted_scope(candidate):
        return None
    return _finalize_place(candidate)


def fronted_scope_for_question(question: str) -> str | None:
    match = lex.FRONTED_SCOPE.search(question)
    if match is None:
        return None
    candidate = clean_fronted_scope(match.group("place"))
    if not plausible_fronted_scope(candidate) or _rejected_place(candidate):
        return None
    return candidate
