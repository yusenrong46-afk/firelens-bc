"""BOUND: live topics FireLens has no official feed for.

Air quality, road status, weather and smoke forecasts, aircraft positions:
people ask about them in the same breath as fires, and FireLens holds no
official source for any of them. Such a clause is never answered from the
wildfire layers or by the model; it is handed to the responsible official
service (`live_handoffs`). Definitional questions about the same topics
("what are road closures?") are ordinary background, not handoffs.
"""

from __future__ import annotations

import re

from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_automaton_types import TemporalScope
from firelens.answering.request_grammar import parse_request_facets

_CURRENT_CUE_TEXT = (
    r"(?:right now|currently|current|latest|today|tonight|tomorrow|now|at the moment)"
)
_CURRENT_CUE = re.compile(rf"\b{_CURRENT_CUE_TEXT}\b", re.IGNORECASE)
_EXPLANATORY_UNSUPPORTED = re.compile(
    r"\b(?:what\s+(?:does|do)\b.{0,80}\bmean|what\s+is\s+an?\b|"
    r"(?:explain|define)\b|how\s+does\b.{0,80}\b(?:affect|work))",
    re.IGNORECASE,
)
_UNSUPPORTED_LIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "air quality",
        re.compile(
            rf"\b(?:what|how)\s+(?:is|are)\s+(?:the\s+)?"
            rf"(?:air quality|aqhi|smoke conditions?)\b|"
            rf"\bis\s+(?:it|.{{1,50}})\s+smoky\b|"
            rf"\b{_CURRENT_CUE_TEXT}\b.{{0,60}}\b"
            rf"(?:air quality|aqhi|smoke conditions?|smoky)\b|"
            rf"\b(?:air quality|aqhi|smoke conditions?|smoky)\b.{{0,60}}"
            rf"\b{_CURRENT_CUE_TEXT}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "road conditions",
        re.compile(
            # Live road handoffs need an operational status request, not a
            # road noun plus an adjacent explanatory word.  Personalized
            # safe-driving questions are handled separately by safety routing.
            rf"\b(?:confirm|verify)(?:\s+(?:that|whether|if))?\s+"
            rf"(?:the\s+)?(?:roads?|highways?|routes?)\b"
            rf"(?:\s+[a-z0-9.'-]+){{0,4}}\s+(?:is|are)\s+"
            rf"(?:open|closed|blocked)\b.{{0,35}}\b{_CURRENT_CUE_TEXT}\b|"
            r"\b(?:is|are)\s+(?:the\s+)?(?:roads?|highways?|routes?)\b"
            r"(?:\s+[a-z0-9.'-]+){0,4}\s+\b(?:open|closed|blocked)\b|"
            r"\bare\s+there\s+(?:any\s+)?(?:road|highway|route)\s+"
            r"(?:closures?|blocks?)\b.{0,30}\b(?:near|around|in|on|at)\b|"
            r"\bwhich\s+(?:roads?|highways?|routes?)\s+(?:are\s+)?"
            r"(?:currently\s+|now\s+)?(?:open|closed|blocked)\b|"
            r"\bwhere\s+(?:are\s+)?(?:roads?|highways?|routes?)\s+"
            r"(?:open|closed|blocked)\b|"
            r"\b(?:list|show|display|find|locate|check)\b.{0,20}"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b|"
            # "highway status", "any road closures near Kamloops", "where do I
            # check the highway status": status-seeking, not definitional.
            r"\b(?:road|highway|route)\s+status\b|"
            r"\b(?:any|current)\s+(?:road|highway|route)\s+(?:closures?|conditions?)\b|"
            r"\bwhere\s+(?:do|can|should)\s+(?:i|we)\s+(?:check|find|see|look)\b.{0,30}"
            r"\b(?:roads?|highways?|routes?)\b|"
            r"\b(?:check|find\s+out)\s+(?:if|whether)\s+(?:the\s+)?"
            r"(?:roads?|highways?|routes?)\b(?:\s+[a-z0-9.'-]+){0,4}\s+"
            r"(?:is|are)\s+(?:open|closed|blocked)\b|"
            # A mixed request can omit the leading action verb: "show fires
            # around Prince George and whether Highway 97 is closed" still
            # asks for an operational road-status lookup, not a definition.
            r"\b(?:if|whether)\s+(?:the\s+)?(?:roads?|highways?|routes?)\b"
            r"(?:\s+[a-z0-9.'-]+){0,4}\s+(?:is|are)\s+"
            r"(?:open|closed|blocked)\b|"
            # A request for a personal driving-safety decision is prohibited,
            # but the live coordinator must still own it so it can link the
            # responsible road-conditions service rather than dropping it as
            # an unrelated topic.
            r"\b(?:is\s+it|tell\s+me\s+(?:if|whether))\s+.{0,30}"
            r"\bsafe\s+to\s+(?:drive|travel|go)\b|"
            r"\b(?:current|latest|today|now|right\s+now)\b.{0,35}"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b|"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b"
            r".{0,35}\b(?:current|latest|today|now|right\s+now)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "weather or smoke forecast",
        re.compile(
            rf"\bwhat\s+will\s+(?:the\s+)?(?:wind|weather|smoke)\b|"
            r"\blive\s+weather\b|"
            rf"\b(?:wind|weather|smoke)\b.{{0,60}}"
            rf"\b(?:forecast|speed|direction|{_CURRENT_CUE_TEXT})\b|"
            rf"\b(?:forecast|{_CURRENT_CUE_TEXT})\b.{{0,60}}"
            rf"\b(?:wind|weather|smoke)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "firefighting aircraft",
        re.compile(
            r"\b(?:where|show|display|track|locate)\b.{0,60}"
            r"\b(?:firefighting\s+)?(?:aircraft|airtankers?|air tankers?|helicopters?)\b|"
            rf"\b(?:aircraft|airtankers?|air tankers?|helicopters?)\b.{{0,60}}"
            rf"\b{_CURRENT_CUE_TEXT}\b|"
            rf"\b{_CURRENT_CUE_TEXT}\b.{{0,60}}"
            r"\b(?:firefighting\s+)?(?:aircraft|airtankers?|air tankers?|helicopters?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reception centre",
        re.compile(r"\breception\s+cent(?:re|er)s?\b", re.IGNORECASE),
    ),
    (
        "utility outage",
        re.compile(
            r"\b(?:power|electricity|hydro)\s+(?:out|outage|outages)\b|"
            r"\bpower\s+out\b|"
            r"\boutage\b.{0,40}\b(?:power|electricity|hydro|utility)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "park closure",
        re.compile(
            r"\b(?:provincial\s+)?parks?\b.{0,48}\b(?:closed|closure|closures)\b|"
            r"\b(?:closed|closure|closures)\b.{0,48}\b(?:provincial\s+)?parks?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "insurance boundary",
        re.compile(
            r"\binsurance\s+claim\b|"
            r"\b(?:make|file)\s+an?\s+insurance\b|"
            r"\binsurance\b.{0,48}\b(?:claim|coverage|covered|policy)\b|"
            r"\b(?:claim|coverage|covered)\b.{0,48}\binsurance\b",
            re.IGNORECASE,
        ),
    ),
)

_ROAD_EXPLANATORY_INTENT = re.compile(
    r"\b(?:what\s+are\s+(?:the\s+)?(?:road|highway|route)\s+"
    r"(?:closures?|conditions?)|caus(?:e|es|ed|ing)|effect(?:s)?|"
    r"polic(?:y|ies)|common(?:ness)?|frequen(?:cy|t|tly)|histor(?:y|ical)|"
    r"explain(?:ed|ing)?)\b",
    re.IGNORECASE,
)


def has_independent_supported_live_clause(question: str) -> bool:
    """Keep live fetch only when a clause asks for owned records, not a handoff domain."""

    return any(
        clause.is_live and not unsupported_live_topics(clause.text)
        for clause in parse_request_intent(question).clauses
    )


def unsupported_live_topics(question: str) -> tuple[str, ...]:
    fragments = parse_request_facets(question).clause_texts
    return tuple(
        label
        for label, pattern in _UNSUPPORTED_LIVE_PATTERNS
        if any(
            pattern.search(fragment)
            and not (
                label == "road conditions"
                and (
                    parse_request_intent(fragment).temporal_scope == TemporalScope.NONCURRENT
                    or _ROAD_EXPLANATORY_INTENT.search(fragment)
                )
            )
            and not (
                _EXPLANATORY_UNSUPPORTED.search(fragment) and not _CURRENT_CUE.search(fragment)
            )
            for fragment in fragments
        )
    )
