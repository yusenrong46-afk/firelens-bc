"""Narrow deterministic safety and trust-intent predicates."""

from __future__ import annotations

import re

from firelens.contracts import QueryPlan, QueryRoute, ReasonCode

TRUST_EXPLANATION_PATTERN = (
    r"(?:\bhow can i tell whether information in your answer is "
    r"current or just preparedness guidance\b|"
    r"\bhow (?:do|can) i know\b.{0,100}\b(?:answer|information)\b"
    r".{0,100}\b(?:trustworthy|reliable|grounded|sourced|reviewed)\b|"
    r"\bwhich parts? of (?:a |the )?firelens answer (?:are|were) reviewed\b|"
    r"\bwhere did (?:this|the|your)(?: firelens)? "
    r"(?:answer|information) come from\b)"
)

# A no-all-clear correction is warranted only when the user describes an
# *operational* FireLens/official-record view as empty.  Do not treat generic
# search help, historical research, or unrelated data quality questions as a
# live safety request merely because they contain the word "search" or "map".
_LIVE_VIEW_REFERENCE = re.compile(
    r"\b(?:"
    r"(?:wildfire|fire|incident|incidents?|perimeter|evacuation)\s+"
    r"(?:map|layer|search(?:\s+results?)?)|"
    r"(?:wildfire|fire)?\s*map|"
    r"(?:incident|incidents?|fire|wildfire|records?|results?)\s+"
    r"(?:appeared|appear|returned|return)\s+(?:in|on)\s+"
    r"(?:the\s+)?(?:map|search|layer)|"
    r"(?:map|layer|search(?:\s+results?)?)\s+"
    r"(?:did\s+not|didn't|does\s+not|has\s+not|have\s+not)\s+return"
    r")\b",
    re.IGNORECASE,
)
_MAP_ABSENCE = re.compile(
    r"\b(?:empty|blank|nothing|no\s+(?:matching\s+)?"
    r"(?:results?|incidents?|fires?|wildfires?|records?)|zero\s+(?:matching\s+)?"
    r"(?:results?|incidents?|fires?|wildfires?|records?)|"
    r"(?:returned|return(?:ed)?)\s+(?:zero|no)\s+"
    r"(?:matching\s+)?(?:results?|incidents?|fires?|wildfires?|records?)|"
    r"(?:returned|return(?:ed)?)\s+nothing|"
    r"(?:did\s+not|didn't|does\s+not|has\s+not|have\s+not)\s+return\s+"
    r"(?:any\s+)?(?:results?|incidents?|fires?|wildfires?|records?))\b",
    re.IGNORECASE,
)
_SAFETY_INFERENCE = re.compile(
    r"\b(?:safe|all[- ]clear|(?:is\s+)?everything\s+(?:is\s+)?(?:okay|ok|fine)|"
    r"(?:no|zero)\s+(?:immediate\s+)?danger|"
    r"(?:no|zero)\s+(?:(?:wild)?fire\s+risk|risk\s+(?:from|of)\s+(?:wild)?fire)|"
    r"(?:no|zero)\s+(?:immediate\s+)?risk(?!\s+of\s+"
    r"(?:data|search|archive|reporting)\b)|"
    r"(?:(?:wild)?fire\s+risk|risk\s+(?:from|of)\s+(?:wild)?fire)\s+"
    r"(?:is\s+)?(?:no|zero))\b",
    re.IGNORECASE,
)
_HISTORICAL_ANALYSIS = re.compile(
    r"\b(?:historical|historic|archive|archival)\b|\b(?:19|20)\d{2}\b",
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
    """Recognize an explicit attempt to turn map absence into an all-clear."""

    return bool(
        not _HISTORICAL_ANALYSIS.search(question)
        and _LIVE_VIEW_REFERENCE.search(question)
        and _MAP_ABSENCE.search(question)
        and _SAFETY_INFERENCE.search(question)
    )


def empty_map_safety_routing(
    question: str,
    normalized_question: str,
    *,
    allow_live: bool,
) -> tuple[tuple[str, ...], QueryPlan | None]:
    """Return sentence-local boundary text and an optional all-clear correction plan."""

    lowered = question.lower()
    if not is_empty_map_safety_inference(normalized_question):
        return (lowered,), None
    fragments = tuple(fragment for fragment in re.split(r"(?<=[.!?])\s+", lowered) if fragment)
    plan = (
        QueryPlan(
            original_question=question,
            normalized_question=normalized_question,
            route=QueryRoute.LIVE,
            boundary_reason=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=["An empty map view is not an all-clear."],
        )
        if allow_live
        else None
    )
    return fragments, plan


def trust_explanation_limitations(question: str) -> list[str] | None:
    if not _TRUST_EXPLANATION.search(question):
        return None
    return list(_TRUST_EXPLANATION_LIMITATIONS)
