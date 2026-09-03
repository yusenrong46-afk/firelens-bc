"""BOUND: the clauses of a turn that are answered by saying what FireLens will not do.

A mixed question is answered clause by clause. Records and guidance clauses run
tools. Two other kinds run nothing and are still answered, each as its own
section, so no clause is silently dropped:

- a personal safety decision ("...and should I evacuate?") is a boundary
  FireLens keeps, with the official next step;
- a time FireLens holds no data for ("what changed since yesterday") is
  unavailable, said plainly.

A live topic FireLens has no official feed for ("where to check road
closures") is the third kind; it is answered by the typed official handoff
(`live_handoffs.related_live_links`) and only needs to be kept away from the
model, which `is_boundary_clause` does for the planner.
"""

from __future__ import annotations

import re

from firelens.answering.intent import plan_query
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_automaton_types import ClauseIntentKind, TemporalScope
from firelens.answering.unsupported_live import unsupported_live_topics
from firelens.contracts import AnswerSection, AnswerSectionKind, QueryRequest, QueryRoute

_EVACUATION_DECISION = re.compile(r"\bevacuat\w*|\bleave\b|\bget\s+out\b", re.IGNORECASE)
_COMPARISON_WITH_THE_PAST = re.compile(
    r"\b(?:changed?|changes|since|yesterday|earlier|before|previous(?:ly)?|compared?|"
    r"history|historical|last\s+(?:night|week|month|year)|ago|trend|grown|grew)\b",
    re.IGNORECASE,
)

EVACUATION_DECISION_TEXT = (
    "Whether to evacuate is a decision FireLens cannot make for you. Follow instructions "
    "from the issuing local authority, and check EmergencyInfoBC for current evacuation "
    "orders and alerts."
)
PERSONAL_SAFETY_TEXT = (
    "That is a personal safety decision FireLens cannot make for you. Follow instructions "
    "from the issuing local authority and emergency services."
)
SAFETY_BOUNDARY_LIMITATION = "FireLens did not make a personal safety decision."
UNAVAILABLE_LIMITATION = "FireLens keeps no earlier copies of official records to compare with."


def _is_personal_safety(clause: str) -> bool:
    return plan_query(QueryRequest(question=clause)).route == QueryRoute.PROHIBITED


def _asks_about_the_past(
    clause_kind: ClauseIntentKind, scope: TemporalScope, text: str
) -> bool:
    return (
        scope == TemporalScope.NONCURRENT
        and clause_kind in {ClauseIntentKind.OTHER, ClauseIntentKind.LIVE_RECORDS}
        and _COMPARISON_WITH_THE_PAST.search(text) is not None
    )


def is_boundary_clause(text: str) -> bool:
    """Whether a non-live clause must not be sent to the model or reviewed search."""

    parsed = parse_request_intent(text)
    if not parsed.clauses:
        return False
    clause = parsed.clauses[0]
    return bool(
        unsupported_live_topics(text)
        or _is_personal_safety(text)
        or _asks_about_the_past(clause.kind, clause.temporal_scope, text)
    )


def clause_boundaries(question: str) -> tuple[AnswerSection, ...]:
    """The boundary sections for a question's declined or unavailable clauses.

    Only a question with more than one clause has boundaries; a lone personal
    safety question keeps its dedicated whole-turn response.
    """

    parsed = parse_request_intent(question)
    if len(parsed.clauses) < 2:
        return ()
    sections: list[AnswerSection] = []
    kinds: set[AnswerSectionKind] = set()
    for clause in parsed.clauses:
        # "Am I safe in Kelowna" names a place, so the parser files it with the
        # live clauses; the decision it asks for is still not FireLens's to make.
        if _is_personal_safety(clause.text):
            kind = AnswerSectionKind.SAFETY_BOUNDARY
            text = (
                EVACUATION_DECISION_TEXT
                if _EVACUATION_DECISION.search(clause.text)
                else PERSONAL_SAFETY_TEXT
            )
            heading = "What FireLens cannot decide"
        elif clause.is_live:
            continue
        elif _asks_about_the_past(clause.kind, clause.temporal_scope, clause.text):
            kind = AnswerSectionKind.UNAVAILABLE
            text = (
                f"FireLens cannot say \u201c{clause.text}\u201d. It shows the current "
                "official publication only and keeps no earlier copies to compare with."
            )
            heading = "What FireLens cannot show"
        else:
            continue
        if kind in kinds:
            continue
        kinds.add(kind)
        sections.append(AnswerSection(kind=kind, heading=heading, text=text))
    return tuple(sections)


def wants_evacuation_records(boundaries: tuple[AnswerSection, ...]) -> bool:
    """A declined evacuation decision still deserves the official evacuation records."""

    return any(
        section.kind == AnswerSectionKind.SAFETY_BOUNDARY
        and section.text == EVACUATION_DECISION_TEXT
        for section in boundaries
    )
