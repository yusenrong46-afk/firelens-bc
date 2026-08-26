"""Compatibility projection of the typed deterministic intent automaton.

Historically this module contained a second, regex-heavy routing grammar. The
public dataclasses remain stable, but all consumers now receive the same parsed
clause ownership from :mod:`firelens.answering.intent_automaton`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from firelens.answering.intent_automaton import clear_intent_cache, parse_request_intent


@dataclass(frozen=True, slots=True)
class RequestClause:
    """One top-level request clause and its structural live-fire facets."""

    text: str
    current_live_fire: bool
    non_current_fire: bool
    live_location_candidate: str | None = None


@dataclass(frozen=True, slots=True)
class RequestFacets:
    """Backward-compatible request projection backed by one typed parse."""

    original_question: str
    clauses: tuple[RequestClause, ...]

    @property
    def clause_texts(self) -> tuple[str, ...]:
        return tuple(clause.text for clause in self.clauses)

    @property
    def live_clauses(self) -> tuple[RequestClause, ...]:
        return tuple(clause for clause in self.clauses if clause.current_live_fire)

    @property
    def non_live_clauses(self) -> tuple[RequestClause, ...]:
        return tuple(clause for clause in self.clauses if not clause.current_live_fire)

    @property
    def has_current_live_fire(self) -> bool:
        return bool(self.live_clauses)

    @property
    def only_non_current_fire(self) -> bool:
        return not self.has_current_live_fire and any(
            clause.non_current_fire for clause in self.clauses
        )

    @property
    def live_location_candidates(self) -> tuple[str, ...]:
        return tuple(
            candidate
            for clause in self.live_clauses
            if (candidate := clause.live_location_candidate) is not None
        )


@lru_cache(maxsize=2_048)
def parse_request_facets(question: str) -> RequestFacets:
    """Return the stable request-facet projection from one typed parse."""

    parsed = parse_request_intent(question)
    return RequestFacets(
        original_question=question,
        clauses=tuple(
            RequestClause(
                text=clause.text,
                current_live_fire=clause.is_live,
                non_current_fire=clause.is_noncurrent_fire,
                live_location_candidate=clause.live_location_candidate,
            )
            for clause in parsed.clauses
        ),
    )


def requests_non_bc_national_scope(question: str) -> bool:
    """Return whether a current-record request explicitly owns national scope."""

    return parse_request_intent(question).requests_non_bc_scope


def clear_request_grammar_cache() -> None:
    """Clear the compatibility and parser caches after an intentional reload."""

    parse_request_facets.cache_clear()
    clear_intent_cache()
