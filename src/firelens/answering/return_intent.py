"""Deterministic recognition of reviewed generic return conditions."""

from __future__ import annotations

import re

from firelens.answering.intent_patterns import (
    _RETURN_DECISION_CUE_PATTERNS,
    _REVIEWED_RETURN_CONDITION_PATTERNS,
)


def reviewed_return_condition_intent(question: str) -> bool:
    """Recognize only reviewed generic return timing, never a current all-clear."""

    lowered = question.casefold()
    if any(re.search(pattern, lowered) for pattern in _RETURN_DECISION_CUE_PATTERNS):
        return False
    return any(re.search(pattern, lowered) for pattern in _REVIEWED_RETURN_CONDITION_PATTERNS)
