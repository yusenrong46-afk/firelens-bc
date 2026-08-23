"""Narrow deterministic safety and trust-intent predicates."""

from __future__ import annotations

import re

TRUST_EXPLANATION_PATTERN = (
    r"\bhow can i tell whether information in your answer is "
    r"current or just preparedness guidance\b"
)

_EMPTY_MAP_SAFETY_INFERENCE = re.compile(
    r"\bmap\b.{0,100}\b(?:no|zero)\s+(?:matching\s+)?(?:fires?|wildfires?|records?)\b"
    r".{0,120}\b(?:safe|all-clear)\b",
    re.IGNORECASE,
)
_TRUST_EXPLANATION = re.compile(TRUST_EXPLANATION_PATTERN, re.IGNORECASE)
_TRUST_EXPLANATION_LIMITATIONS = (
    "Official live records show two clocks: when the official source updated the "
    "record and when FireLens retrieved it.",
    "Stable preparedness guidance labels reviewed structured claims separately from "
    "exact source wording that has not been approved as a structured FireLens claim.",
    "General background is labelled as not checked against the reviewed collection.",
    "Automated evidence and critical-field checks do not replace human semantic review.",
)


def is_empty_map_safety_inference(question: str) -> bool:
    return bool(_EMPTY_MAP_SAFETY_INFERENCE.search(question))


def trust_explanation_limitations(question: str) -> list[str] | None:
    if not _TRUST_EXPLANATION.search(question):
        return None
    return list(_TRUST_EXPLANATION_LIMITATIONS)
