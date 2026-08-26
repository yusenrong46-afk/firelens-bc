"""Deterministically retain the non-live clause of a mixed user request."""

from __future__ import annotations

import re

from firelens.answering.intent import (
    live_layers_for_question,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.request_grammar import parse_request_facets
from firelens.contracts import QueryRequest


def extract_static_request(request: QueryRequest) -> QueryRequest | None:
    """Return only the bounded reviewed-guidance fragment of a mixed request."""

    facets = parse_request_facets(request.question)
    fragment = static_guidance_fragment(request.question)
    if fragment is None:
        live_fragments = [
            clause.text
            for clause in facets.clauses
            if clause.current_live_fire
            or live_layers_for_question(clause.text)
            or unsupported_live_topics(clause.text)
            or (
                coarse_location_from_question(clause.text) is not None
                and re.search(
                    r"\b(?:fire|wildfire|map|evacuation|alert|order|perimeter)\b",
                    clause.text,
                    re.IGNORECASE,
                )
            )
        ]
        non_live_fragments = [
            clause.text for clause in facets.clauses if clause.text not in live_fragments
        ]
        if live_fragments and non_live_fragments:
            fragment = " and ".join(non_live_fragments)[:2_000]
    if fragment is None:
        return None
    return QueryRequest(
        question=fragment,
        history=request.history,
        context=request.context,
    )
