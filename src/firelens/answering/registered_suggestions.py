"""Allowlisted post-answer suggestions from the guided-question registry."""

from __future__ import annotations

from typing import Any

from firelens.answering.intent import SUGGESTED_QUESTIONS
from firelens.contracts import ResponseMode
from firelens.guidance_capabilities import advertised_guided_questions, resolve_capability

_LIVE_FOLLOWUPS = (
    "What belongs in an emergency kit?",
    "What is the difference between an evacuation alert and order?",
    "How can I prepare for wildfire smoke?",
)
_GUIDANCE_FOLLOWUPS = (
    "What belongs in an emergency kit?",
    "How should I build and review a household emergency plan?",
    "How can I reduce combustible material around my home?",
)


def registered_suggestions(
    *,
    question: str,
    response: Any,
    place_label: str | None = None,
) -> list[str]:
    """Return 0-3 registry questions. Empty is valid for refusal or unclear input."""

    mode = getattr(response, "response_mode", None)
    reason = getattr(getattr(response, "reason_code", None), "value", None)
    existing = list(getattr(response, "suggested_questions", None) or [])
    if existing:
        return existing[:3]
    if reason in {
        "personalized_safety_decision",
        "personalized_medical_advice",
        "policy_manipulation",
        "unclear_input",
        "missing_source_antecedent",
    }:
        return existing
    if mode == ResponseMode.REQUIRES_INPUT:
        return existing
    current = resolve_capability(question, place_label=place_label)
    advertised = {
        normalize(item.question)
        for item in advertised_guided_questions()
        if "{place}" not in item.question
    }
    advertised.update(normalize(item) for item in SUGGESTED_QUESTIONS)
    if mode in {ResponseMode.LIVE, ResponseMode.MIXED}:
        pool = list(_LIVE_FOLLOWUPS)
    elif mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}:
        pool = list(_GUIDANCE_FOLLOWUPS)
    else:
        pool = list(SUGGESTED_QUESTIONS[:3])
    blocked = {normalize(question)}
    if current is not None:
        blocked.update(normalize(item) for item in current.canonical_questions)
    selected: list[str] = []
    for item in pool:
        if normalize(item) in blocked or item in selected:
            continue
        if advertised and normalize(item) not in advertised:
            continue
        selected.append(item)
        if len(selected) == 3:
            break
    return selected


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()
