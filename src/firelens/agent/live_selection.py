"""Deterministic selected-record identity and official handoff binding."""

from __future__ import annotations

import re
from collections.abc import Sequence

from firelens.answering.live_analysis import (
    closest_locatable_result,
    is_closest_live_question,
)
from firelens.contracts import LiveResult, QueryRequest, RelatedLink


def selected_live_result_id(
    request: QueryRequest,
    live: Sequence[LiveResult],
) -> str | None:
    """Bind focused answers to the typed record selected by deterministic code."""

    if request.context.selected_live_result_id:
        return request.context.selected_live_result_id
    if not is_closest_live_question(request.question):
        return None
    closest = closest_locatable_result(request.question, live)
    return closest.result_id if closest is not None else None


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
