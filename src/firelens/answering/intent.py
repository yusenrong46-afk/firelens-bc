"""Conservative deterministic routing for the static-only first system."""

from __future__ import annotations

import re

from firelens.contracts import (
    QueryPlan,
    QueryRequest,
    QueryRoute,
    RetrievalRequest,
)


_PROHIBITED_PATTERNS = (
    r"\b(safest|best)\s+(road|route|way)\b",
    r"\bwhich\s+(road|route)\s+should\s+i\s+take\b",
    r"\b(am i|are we|is it)\s+safe\b",
    r"\bis\s+(?:my|our)\s+.{0,30}\bsafe\b",
    r"\bshould\s+i\s+(stay|leave|evacuate|return)\b",
    r"\btell me\s+whether\s+to\s+evacuate\b",
)

_LIVE_PATTERNS = (
    r"\b(right now|currently|latest|today|tonight|this morning|this afternoon|this evening|this week|at the moment)\b",
    r"\b(active|current)\s+(fire|wildfire|evacuation|alert|order)\b",
    r"\b(is there|are there)\s+(a\s+)?(fire|wildfire)\b",
    r"\bwhere\s+is\s+the\s+(fire|wildfire)\b",
    r"\bnear\s+(me|my home|my house|my address)\b",
    r"\bhas\s+.*\s+(been evacuated|issued an evacuation)\b",
    r"\bwhat(?:'s| is)\s+(?:the\s+)?(?:wildfire|fire)\s+(?:status|situation)\b",
    r"\bhow many\s+(?:active\s+)?(?:fires|wildfires)\b",
    r"\b(?:evacuation|wildfire|fire)\s+(?:map|status|update|updates)\b",
    r"\b(?:fires|wildfires)\b.{0,40}\bburning\b",
    r"\bburning\b.{0,40}\b(?:fires|wildfires)\b",
    r"\b(?:road|highway)\b.{0,40}\b(?:open|closed|closure|blocked)\b",
)


def _required_authority(question: str) -> str | None:
    lowered = question.lower()
    if any(term in lowered for term in ("smoke", "air quality", "health", "asthma")):
        return "provincial_public_health"
    if any(
        term in lowered
        for term in ("evacuation alert", "evacuation order", "grab-and-go", "emergency plan")
    ):
        return "provincial_government"
    if any(term in lowered for term in ("firesmart", "sprinkler", "home ignition")):
        return "recognized_wildfire_preparedness_program"
    return None


def plan_query(request: QueryRequest) -> QueryPlan:
    question = " ".join(request.question.split())
    lowered = question.lower()
    if any(re.search(pattern, lowered) for pattern in _PROHIBITED_PATTERNS):
        return QueryPlan(
            original_question=request.question,
            normalized_question=question,
            route=QueryRoute.PROHIBITED,
            retrieval_requests=[],
            limitations=["FireLens cannot make personalized evacuation or safety decisions."],
        )
    if any(re.search(pattern, lowered) for pattern in _LIVE_PATTERNS):
        return QueryPlan(
            original_question=request.question,
            normalized_question=question,
            route=QueryRoute.LIVE,
            retrieval_requests=[],
            limitations=["The static corpus cannot establish current wildfire conditions."],
        )
    return QueryPlan(
        original_question=request.question,
        normalized_question=question,
        route=QueryRoute.STATIC,
        retrieval_requests=[
            RetrievalRequest(
                query=question,
                required_authority=_required_authority(question),
            )
        ],
        limitations=["This answer uses stable guidance and does not provide current status."],
    )
