"""Deterministic province-wide analysis intent over official fire records."""

from __future__ import annotations

import re

from firelens.answering.location_intent import directional_bc_region_label

_FIRE_WORD = re.compile(r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?)\b", re.IGNORECASE)
_GEOGRAPHY_ANALYSIS_WORD = re.compile(
    r"\b(?:distribut(?:ion|ed)|geograph(?:y|ic|ically)|concentrat(?:e|ed|ion))\b",
    re.IGNORECASE,
)
_DENSITY = re.compile(r"\bdensity\b", re.IGNORECASE)
_SMOKE_OR_AIR_QUALITY = re.compile(r"\b(?:smoke|air\s+quality|aqhi)\b", re.IGNORECASE)
_DENSITY_AGGREGATION = re.compile(
    r"\bdensity\b.{0,80}\b(?:latitude\s+bands?|regions?|areas?|"
    r"fire[- ]?centres?|distribution)\b|"
    r"\b(?:latitude\s+bands?|regions?|areas?|fire[- ]?centres?|distribution)\b"
    r".{0,80}\bdensity\b",
    re.IGNORECASE,
)
_AREA_RANKING = re.compile(
    r"\b(?:which|what)\s+(?:areas?|regions?|fire\s+centres?)\b.{0,80}"
    r"\b(?:most|fewest|highest|lowest|many|number|count)\b|"
    r"\b(?:most|fewest|highest|lowest)\b.{0,80}"
    r"\b(?:areas?|regions?|fire\s+centres?)\b",
    re.IGNORECASE,
)
_WHERE_FIRE_RANKING = re.compile(
    r"\bwhere\s+are\s+(?:the\s+)?(?:most|fewest)\s+"
    r"(?:fires?|wildfires?|[a-z]{1,12}fires?)\b|"
    r"\bwhere\b.{0,50}\b(?:fires?|wildfires?)\b.{0,30}"
    r"\b(?:most|fewest|concentrated)\b",
    re.IGNORECASE,
)
_PER_AREA_COUNTS = re.compile(
    r"\b(?:how\s+many|count|number\s+of|fires?|wildfires?)\b.{0,80}"
    r"\b(?:each|per|by)\s+(?:(?:fire[- ]?)?centres?|areas?|regions?)\b|"
    r"\b(?:each|per|by)\s+(?:(?:fire[- ]?)?centres?|areas?|regions?)\b.{0,80}"
    r"\b(?:count|number|fires?|wildfires?)\b",
    re.IGNORECASE,
)
_UNVALIDATED_REGION_COMPARISON = re.compile(
    r"\bokanagan\b.{0,100}\bkootenays?\b|"
    r"\bkootenays?\b.{0,100}\bokanagan\b",
    re.IGNORECASE,
)
_EXPLANATORY_GEOGRAPHY = re.compile(
    r"\b(?:how|why)\s+does\b.{0,60}\bgeograph(?:y|ic)\b.{0,40}"
    r"\b(?:affect|change|influence|shape)\b",
    re.IGNORECASE,
)
_CURRENT_RECORD_CUE = re.compile(
    r"\b(?:right\s+now|currently|current|latest|today|tonight|"
    r"now|at\s+the\s+moment|active|updated|up[- ]to[- ]date)\b",
    re.IGNORECASE,
)
_DIRECTIONAL_BC_RECORD_REQUEST = re.compile(
    r"\b(?:where\s+are|are\s+there|show|display|list|map|"
    r"how\s+many|count|number\s+of)\b.{0,80}"
    r"\b(?:fires?|wildfires?)\b|"
    r"\bwhich\s+(?:fires?|wildfires?)\s+(?:are\s+)?"
    r"(?:in|across|throughout)\b|"
    r"\bwhat\s+(?:fires?|wildfires?)\s+(?:are\s+)?burning\b|"
    r"\bare\s+(?:the\s+)?(?:fires?|wildfires?)\s+burning\b",
    re.IGNORECASE,
)
_NON_CURRENT_DIRECTIONAL_SCOPE = re.compile(
    r"\b(?:histor(?:y|ical)|past|previous|former|prior|was|were|will|"
    r"forecast(?:s|ed|ing)?|predict(?:ion|ions|ed|ing)?|"
    r"expect(?:ed|s|ing|ation|ations)?|future|likely|tomorrow|"
    r"next\s+(?:day|week|month|year))\b",
    re.IGNORECASE,
)
_EXPLANATORY_DIRECTIONAL_REGION = re.compile(
    r"\b(?:explain|define|meaning|why)\b",
    re.IGNORECASE,
)
_FIRE_RECORD_ANALYSIS = re.compile(
    r"\b(?:largest|oldest|most\s+burned|hectares?)\b.{0,80}"
    r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?)\b|"
    r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?)\b.{0,80}"
    r"\b(?:largest|oldest|most\s+burned|hectares?)\b",
    re.IGNORECASE,
)


def is_fire_geography_analysis(question: str) -> bool:
    """Recognize bounded distribution analysis over official BC fire records."""

    directional_region = directional_bc_region_label(question)
    if (
        not _FIRE_WORD.search(question)
        or _EXPLANATORY_GEOGRAPHY.search(question)
        # A wildfire adjective does not make smoke density an incident-geography
        # request. Air-quality layers remain outside this official fire-record path.
        or (_DENSITY.search(question) and _SMOKE_OR_AIR_QUALITY.search(question))
    ):
        return False
    # North/south B.C. is not a validated incident geography. Only treat it as
    # a request for the current official-record roster when the question has a
    # present-record cue or directly asks for that roster. Historical, future,
    # predictive, and explanatory regional text remains outside the live-map path.
    if directional_region is not None:
        return bool(
            (
                _CURRENT_RECORD_CUE.search(question)
                or _DIRECTIONAL_BC_RECORD_REQUEST.search(question)
            )
            and not _NON_CURRENT_DIRECTIONAL_SCOPE.search(question)
            and not _EXPLANATORY_DIRECTIONAL_REGION.search(question)
        )
    return bool(
        _GEOGRAPHY_ANALYSIS_WORD.search(question)
        or _DENSITY.search(question)
        or _DENSITY_AGGREGATION.search(question)
        or _AREA_RANKING.search(question)
        or _WHERE_FIRE_RANKING.search(question)
        or _PER_AREA_COUNTS.search(question)
        or _UNVALIDATED_REGION_COMPARISON.search(question)
    )


def is_fire_record_analysis(question: str) -> bool:
    """Recognize direct ranking questions over fields in official fire records."""

    return bool(_FIRE_RECORD_ANALYSIS.search(question))
