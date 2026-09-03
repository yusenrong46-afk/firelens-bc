"""UNDERSTAND: references to a record by its position in the list last shown.

"The second one", "record 3", "#2" refer to the roster the person is looking
at. This module only reads the position; the planner decides which list it
indexes (the client's visible roster) and what to do when it cannot.
"""

from __future__ import annotations

import re

ORDINAL_WORDS = {
    "first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
    "fifth": 4, "5th": 4, "sixth": 5, "6th": 5, "seventh": 6, "7th": 6, "eighth": 7, "8th": 7,
    "ninth": 8, "9th": 8, "tenth": 9, "10th": 9,
}  # fmt: skip

_ORDINAL_REFERENCE = re.compile(
    r"\b(?:the\s+)?(?P<rank>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"\d{1,2}(?:st|nd|rd|th))\s+(?:one|fire|wildfire|incident|record|alert|order|evacuation|"
    r"perimeter|result|listing|item|entry)\b|"
    r"\b(?:record|result|item|entry|number|no\.?)\s*#?\s*(?P<number>\d{1,2})\b|"
    r"(?<![\w#])#\s?(?P<hash>\d{1,2})\b",
    re.IGNORECASE,
)


def ordinal_reference(question: str) -> int | None:
    """Zero-based position the question refers to, or None when it names none."""

    match = _ORDINAL_REFERENCE.search(question)
    if match is None:
        return None
    rank = match.group("rank")
    if rank is not None and rank.isalpha():
        return ORDINAL_WORDS[rank.casefold()]
    digits = rank[:-2] if rank is not None else (match.group("number") or match.group("hash"))
    number = int(digits)
    return number - 1 if 1 <= number <= 20 else None


def ordinal_label(index: int) -> str:
    """Human wording for a zero-based position ("second")."""

    for word, position in ORDINAL_WORDS.items():
        if position == index and word.isalpha():
            return word
    return f"{index + 1}th"
