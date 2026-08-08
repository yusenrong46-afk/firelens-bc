"""Conservative corpus-reference and mixed-scope detection."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_CORPUS_IDENTIFIER = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
_REFERENCE_TOKEN = re.compile(r"[a-z0-9]+")
_MIXED_SCOPE_SPLIT = re.compile(r"\b(?:then|after that|before that)\b|[;+]", re.I)
_MIXED_SCOPE_STOPWORDS = {
    "a",
    "about",
    "and",
    "explain",
    "for",
    "how",
    "i",
    "in",
    "is",
    "me",
    "of",
    "please",
    "the",
    "to",
    "what",
}
_GENERIC_SOURCE_WORDS = {
    "bc",
    "british",
    "columbia",
    "document",
    "emergency",
    "guide",
    "guidance",
    "household",
    "information",
    "kit",
    "preparedness",
    "service",
    "wildfire",
}


def _scope_token(token: str) -> str:
    """Normalize only a simple English plural for conservative overlap checks."""

    return token[:-1] if len(token) >= 4 and token.endswith("s") else token


def corpus_identifiers(question: str) -> frozenset[str]:
    """Return normalized corpus-style identifiers mentioned in a question."""

    return frozenset(
        match.group(0).casefold() for match in _CORPUS_IDENTIFIER.finditer(question)
    )


def candidate_contains_identifier(
    question: str, candidates: Sequence[Mapping[str, str]]
) -> bool:
    """Keep an exact corpus identifier from being dismissed as out of scope."""

    identifiers = corpus_identifiers(question)
    if not identifiers:
        return False
    candidate_text = " ".join(
        value for candidate in candidates for value in candidate.values()
    ).casefold()
    return any(identifier in candidate_text for identifier in identifiers)


def candidate_source_reference_present(
    question: str, candidates: Sequence[Mapping[str, str]]
) -> bool:
    """Recognize explicit source names without treating snippets as evidence."""

    question_tokens = set(_REFERENCE_TOKEN.findall(question.casefold()))
    for candidate in candidates:
        for candidate_field in ("title", "publisher", "source_id"):
            tokens = [
                token
                for token in _REFERENCE_TOKEN.findall(
                    candidate.get(candidate_field, "").casefold()
                )
                if token not in _GENERIC_SOURCE_WORDS
            ]
            distinctive = list(dict.fromkeys(tokens))
            if len(distinctive) >= 2 and set(distinctive).issubset(question_tokens):
                return True
    return False


def mixed_scope_request(question: str, candidates: Sequence[Mapping[str, str]]) -> bool:
    """Detect a sequenced corpus-supported clause plus an unrelated clause.

    Candidate snippets are vocabulary only. This conservative boundary requires
    a clear clause separator, one clause with at least two candidate terms, and
    another substantive clause with at most one candidate term.
    """

    clauses = [
        clause.strip() for clause in _MIXED_SCOPE_SPLIT.split(question) if clause.strip()
    ]
    if len(clauses) < 2:
        return False
    candidate_tokens = {
        _scope_token(token)
        for candidate in candidates
        for token in _REFERENCE_TOKEN.findall(" ".join(candidate.values()).casefold())
        if len(token) >= 3 and token not in _MIXED_SCOPE_STOPWORDS
    }
    overlap_counts: list[int] = []
    substantive_counts: list[int] = []
    for clause in clauses:
        tokens = {
            _scope_token(token)
            for token in _REFERENCE_TOKEN.findall(clause.casefold())
            if len(token) >= 3 and token not in _MIXED_SCOPE_STOPWORDS
        }
        overlap_counts.append(len(tokens & candidate_tokens))
        substantive_counts.append(len(tokens))
    return any(count >= 2 for count in overlap_counts) and any(
        overlap <= 1 and substantive >= 2
        for overlap, substantive in zip(overlap_counts, substantive_counts, strict=True)
    )
