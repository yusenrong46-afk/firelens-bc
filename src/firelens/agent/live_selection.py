"""Deterministic selected-record identity and official handoff binding."""

from __future__ import annotations

import re
from collections.abc import Sequence

from firelens.answering.intent_conversation import (
    is_selected_record_followup,
    prior_anchor_user_question,
)
from firelens.answering.live_analysis import (
    closest_locatable_result,
    is_closest_live_question,
    official_display_name,
    ordinal_record,
)
from firelens.contracts import LiveResult, QueryRequest, RelatedLink
from firelens.understanding.reference import ordinal_reference


def _normalized_record_identity(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _prior_closest_question(request: QueryRequest) -> str | None:
    for turn in reversed(request.history):
        if turn.role == "user" and is_closest_live_question(turn.content):
            return turn.content
    return None


def _assistant_named_record_id(
    request: QueryRequest,
    live: Sequence[LiveResult],
) -> str | None:
    latest = next(
        (turn for turn in reversed(request.history) if turn.role == "assistant"), None
    )
    if latest is None:
        return None
    content = _normalized_record_identity(latest.content)
    matches: list[LiveResult] = []
    for item in live:
        name = official_display_name(item)
        identity = _normalized_record_identity(name)
        if identity and identity in content:
            matches.append(item)
    if len(matches) == 1:
        return matches[0].result_id
    locatable = [item for item in matches if item.distance_km is not None]
    if locatable:
        chosen = min(locatable, key=lambda item: (item.distance_km or 0.0, item.result_id))
        return chosen.result_id
    return None


def selected_live_result_id(
    request: QueryRequest,
    live: Sequence[LiveResult],
) -> str | None:
    """Bind focused answers to the typed record selected by deterministic code."""

    if request.context.selected_live_result_id:
        return request.context.selected_live_result_id
    if is_closest_live_question(request.question):
        closest = closest_locatable_result(request.question, live)
        return closest.result_id if closest is not None else None
    ordinal = ordinal_reference(request.question)
    if ordinal is not None:
        chosen = ordinal_record(live, ordinal)
        return chosen.result_id if chosen is not None else None
    if is_selected_record_followup(request.question):
        closest_question = _prior_closest_question(request)
        if closest_question is not None:
            closest = closest_locatable_result(closest_question, live)
            if closest is not None:
                return closest.result_id
        named = _assistant_named_record_id(request, live)
        if named is not None:
            return named
        prior = prior_anchor_user_question(request)
        if prior is not None:
            closest = closest_locatable_result(prior, live)
            if closest is not None:
                return closest.result_id
    return None


def selected_official_handoff(
    request: QueryRequest,
    live: Sequence[LiveResult],
) -> RelatedLink | None:
    """Expose only the deterministic selected record as the requested next check."""

    tokens = set(re.findall(r"[a-z]+", request.question.casefold()))
    if not ({"official", "check"}.issubset(tokens) and "next" in tokens):
        return None
    selected_id = selected_live_result_id(request, live)
    selected = next((item for item in live if item.result_id == selected_id), None)
    if selected is None:
        return None
    return RelatedLink(
        title="Selected official record",
        url=selected.source_url,
        description="Official source for the selected wildfire record.",
    )
