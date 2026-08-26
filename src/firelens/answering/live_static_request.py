"""Deterministically retain the non-live clause of a mixed user request."""

from __future__ import annotations

from firelens.answering.intent_automaton import parse_request_intent
from firelens.contracts import QueryRequest


def extract_static_request(request: QueryRequest) -> QueryRequest | None:
    """Return only the bounded non-live fragment of a mixed request."""

    parsed = parse_request_intent(request.question)
    fragment = (
        parsed.static_subrequest_text
        if parsed.has_live_records
        else parsed.reviewed_guidance_text
    )
    if fragment is None:
        return None
    return QueryRequest(
        question=fragment,
        history=request.history,
        context=request.context,
    )
