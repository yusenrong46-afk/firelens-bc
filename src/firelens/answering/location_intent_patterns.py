"""Bounded regexes supporting coarse current-fire location extraction."""

from __future__ import annotations

import re

CLOSEST_FIRE_TRAILING_PLACE = re.compile(
    r"\b(?:how\s+(?:big|large)|size)\s+(?:is\s+)?(?:the\s+)?"
    r"(?:closest|nearest)\s+(?:fire|wildfire|incident)\s+"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)\s*[?.!]*$",
    re.IGNORECASE,
)

MULTI_PLACE_DISTANCE_COMPARISONS = (
    re.compile(
        r"\b(?:compare|which)\b.{0,100}\b(?:closest|closer|nearest)\b"
        r".{0,80}(?:\bto\b|,)\s+[a-z][a-z.'-]*(?:\s+[a-z][a-z.'-]*){0,2}?"
        r"\s+(?:and|or)\s+[a-z][a-z.'-]*(?:\s+[a-z][a-z.'-]*){0,2}",
        re.IGNORECASE,
    ),
)

MULTI_PLACE_FIRE_COMPARISONS = MULTI_PLACE_DISTANCE_COMPARISONS + (
    re.compile(
        r"\b(?:fires?|wildfires?|(?:fire|wildfire)\s+counts?|"
        r"evacuation\s+(?:alerts?|orders?)|perimeters?|official\s+records?)\b"
        r".{0,100}\b(?:in|near|around|within|for)\s+"
        r"(?:the\s+)?[a-z][a-z .'-]{1,60}?\s+"
        r"(?:versus|vs\.?)\s+(?:the\s+)?[a-z][a-z .'-]{1,60}?"
        r"(?=[?.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?i:\b(?:fires?|wildfires?|(?:fire|wildfire)\s+counts?|"
        r"evacuation\s+(?:alerts?|orders?)|perimeters?|official\s+records?)\b"
        r".{0,100}\b(?:in|near|around|within|for)\s+(?:the\s+)?"
        r"[a-z][a-z .'-]{1,60}?\s+(?:and|or)\s+(?:the\s+)?)"
        r"[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}"
        r"(?=[?.,;]|$)",
    ),
)
