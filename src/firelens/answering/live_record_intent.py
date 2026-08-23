"""Deterministic province-wide analysis intent over official fire records."""

from __future__ import annotations

import re

_FIRE_WORD = re.compile(r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?)\b", re.IGNORECASE)
_GEOGRAPHY_ANALYSIS_WORD = re.compile(
    r"\b(?:distribution|geograph(?:y|ic|ically)|concentrat(?:e|ed|ion))\b",
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
    r"\b(?:each|per|by)\s+(?:fire[- ]?)?centres?\b|"
    r"\b(?:each|per|by)\s+(?:fire[- ]?)?centres?\b.{0,80}"
    r"\b(?:count|number|fires?|wildfires?)\b",
    re.IGNORECASE,
)
_EXPLANATORY_GEOGRAPHY = re.compile(
    r"\b(?:how|why)\s+does\b.{0,60}\bgeograph(?:y|ic)\b.{0,40}"
    r"\b(?:affect|influence|shape)\b",
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

    if not _FIRE_WORD.search(question) or _EXPLANATORY_GEOGRAPHY.search(question):
        return False
    return bool(
        _GEOGRAPHY_ANALYSIS_WORD.search(question)
        or _AREA_RANKING.search(question)
        or _WHERE_FIRE_RANKING.search(question)
        or _PER_AREA_COUNTS.search(question)
    )


def is_fire_record_analysis(question: str) -> bool:
    """Recognize direct ranking questions over fields in official fire records."""

    return bool(_FIRE_RECORD_ANALYSIS.search(question))
