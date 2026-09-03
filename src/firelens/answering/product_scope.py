"""Product scope: FireLens is about wildfire in British Columbia.

A question the planner has already judged unrelated to the reviewed corpus
still gets a labelled general-background answer when it is *about wildfire*
("Why do wildfires spread faster uphill?").  A question with no wildfire,
emergency, or B.C. vocabulary at all ("Write me a chocolate cake recipe") is
outside the product and gets a short scope note instead of a generated answer.

This is deliberately a small, readable vocabulary check rather than a model
judgement, so the boundary is the same on every run.  Follow-up turns are not
checked: "Why does that matter?" inherits the scope of the conversation.
"""

from __future__ import annotations

import re

from firelens.contracts import QueryRequest

_WILDFIRE_VOCABULARY = re.compile(
    r"\b(?:"
    r"\w*fires?|firefight\w*|firesmart|fire\s?smart|burn\w*|blaze\w*|"
    r"flames?|embers?|smoke\w*|smoky|ash|haze|hazy|"
    r"evacuat\w*|alerts?|orders?|emergenc\w*|preparedness|prepared|"
    r"grab[\s-]and[\s-]go|go[\s-]bag|kit|kits|shelter\w*|"
    r"forests?|trees?|brush|grass|fuels?|slopes?|uphill|downhill|"
    r"lightning|drought|heat\s?wave|wind\w*|weather|"
    r"perimeters?|hectares?|containment|contained|held|"
    r"air\s?quality|aqhi|respirator|n95|"
    r"bcws|bc\s?wildfire|british\s+columbia|b\.?c\.?|"
    r"kelowna|kamloops|vernon|penticton|prince\s+george|vancouver|victoria|"
    r"nelson|cranbrook|nanaimo|fort\s+st\.?\s+john|williams\s+lake|quesnel|"
    r"okanagan|kootenay|cariboo|interior|coast\w*|"
    r"firelens"
    r")\b",
    re.IGNORECASE,
)


def is_outside_wildfire_scope(request: QueryRequest) -> bool:
    """True when nothing in a first-turn question relates to wildfire or B.C."""

    if request.history:
        return False
    if request.location is not None or request.context.selected_live_result_id:
        return False
    return _WILDFIRE_VOCABULARY.search(request.question) is None


SCOPE_NOTE = (
    "FireLens answers questions about wildfires in British Columbia: current official "
    "fire, perimeter, and evacuation records near a place, reviewed preparedness "
    "guidance, and general wildfire background. That question is outside what it covers."
)
