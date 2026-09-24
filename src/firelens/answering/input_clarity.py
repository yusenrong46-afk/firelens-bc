"""Deterministic unclear-input and missing-antecedent gates."""

from __future__ import annotations

import re
from uuid import uuid4

from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.intent_conversation import explicit_corpus_attribution
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    AskResponse,
    QueryRequest,
    ReasonCode,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)
from firelens.guidance_capabilities import resolve_capability

_SMASH_TOKENS = frozenset(
    {
        "asdf",
        "qwer",
        "qwerty",
        "zxcv",
        "zxcvbn",
        "hjkl",
        "jkl;",
        "lorem",
        "ipsum",
        "foo",
        "bar",
        "baz",
        "quux",
        "asdfgh",
    }
)
_DOMAIN_TERMS = re.compile(
    r"\b(?:wildfire|fire|evacuat|alert|order|bcws|emergency|smoke|air quality|"
    r"road|highway|kelowna|pack|kit|firesmart|911|9-1-1|official|guidance)\b",
    re.IGNORECASE,
)
_DEICTIC_SOURCE = re.compile(
    r"\b(?:this|that|the)\s+(?:source|document|guide|checklist|link|handle)\b",
    re.IGNORECASE,
)
_PREVIOUS_ANSWER_SOURCE = re.compile(
    r"(?:"
    r"(?:explain|describe|show|identify|name)\s+(?:me\s+)?(?:the\s+)?"
    r"(?:source|sources|citation|citations|document|evidence)\s+"
    r"(?:you\s+(?:used|cited)(?:\s+for\s+(?:that|this|the\s+previous)\s+answer)?|"
    r"(?:for|behind)\s+(?:that|this|your\s+(?:last|previous))\s+(?:answer|response))|"
    r"(?:what|which)\s+(?:source|sources|document|citation)\s+"
    r"(?:did\s+you\s+(?:use|cite)(?:\s+for\s+(?:that|this)\s+answer)?|"
    r"(?:supports?|backs?)\s+(?:that|your\s+(?:last|previous))\s+(?:answer|response))|"
    r"where\s+did\s+you\s+get\s+(?:that|this)\s+(?:information|answer)"
    r")[.!?\s]*",
    re.IGNORECASE,
)
_CLARIFICATION_EXAMPLES = (
    "What wildfires are currently listed in B.C.?",
    "What belongs in a grab-and-go bag?",
    "What is the difference between an evacuation alert and order?",
)


def is_low_substance_question(question: str) -> bool:
    """Return True only for confident keyboard-smash / non-question input."""

    tokens = [token for token in re.findall(r"[a-z0-9']+", question.casefold()) if token]
    if not tokens:
        return True
    if _DOMAIN_TERMS.search(question):
        return False
    if parse_request_intent(question).has_live_records:
        return False
    if coarse_location_from_question(question) is not None:
        return False
    if resolve_capability(question) is not None:
        return False
    smash = sum(1 for token in tokens if token in _SMASH_TOKENS)
    return smash >= 2 and smash >= max(2, len(tokens) // 2)


def has_source_antecedent(request: QueryRequest) -> bool:
    """A prior turn or selected record can bind 'this source'."""

    if request.context.selected_live_result_id:
        return True
    for turn in reversed(request.history):
        if turn.role != "assistant":
            continue
        text = turn.content.casefold()
        if "authority:" in text or "source:" in text or "reviewed" in text:
            return True
    return False


def requests_previous_answer_source(question: str) -> bool:
    """Recognize a standalone provenance request, not a new guidance question."""

    return _PREVIOUS_ANSWER_SOURCE.fullmatch(question.strip()) is not None


def missing_source_antecedent(request: QueryRequest) -> bool:
    question = request.question
    # Public history carries answer text, not a trusted citation/revision packet.
    # An authority label or selected live ID cannot identify the prior source span.
    if requests_previous_answer_source(question):
        return True
    if not _DEICTIC_SOURCE.search(question):
        return False
    if has_source_antecedent(request):
        return False
    if explicit_corpus_attribution(question) or "source" in question.casefold():
        return True
    return True


def unclear_input_response() -> AskResponse:
    answer = (
        "I could not tell what you want to ask. Try a current-records question, "
        "a reviewed preparedness question, or a place-scoped wildfire question."
    )
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer=answer,
        reason_code=ReasonCode.UNCLEAR_INPUT,
        suggested_questions=list(_CLARIFICATION_EXAMPLES),
        limitations=["FireLens did not treat that input as a wildfire question."],
    )


def missing_source_antecedent_response(request: QueryRequest | None = None) -> AskResponse:
    answer = (
        "I'm not sure which source you mean. Select a source from the evidence "
        "panel, or ask what BC Wildfire Service says about a specific topic."
    )
    prior_source = request is not None and requests_previous_answer_source(request.question)
    if prior_source:
        answer = (
            "I can't verify which source, document revision, or passage supported the "
            "previous answer from the conversation text available here. Please name the "
            "document or ask a specific question about it. I won't infer a citation "
            "from the topic alone."
        )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=answer,
        reason_code=ReasonCode.MISSING_SOURCE_ANTECEDENT,
        required_input=RequiredInput(
            kind=RequiredInputKind.SOURCE,
            prompt="Select a source or name a specific topic.",
            continuation_question="What does the official BC Wildfire Service say about wildfire preparedness?",
        ),
        limitations=[
            "This request does not include verified source metadata for the preceding answer."
            if prior_source
            else "FireLens did not retrieve a source directory for an unbound reference."
        ],
    )
