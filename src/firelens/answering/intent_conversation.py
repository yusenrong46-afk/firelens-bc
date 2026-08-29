"""Conversation-aware routing helpers kept separate from the route compiler."""

from __future__ import annotations

import re

from firelens.answering.capability_intent import is_capability_question
from firelens.answering.intent_automaton import TemporalScope, parse_request_intent
from firelens.answering.intent_patterns import _CORPUS_REFERENCE_PATTERNS
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.return_intent import reviewed_return_condition_intent
from firelens.answering.scope import corpus_identifiers
from firelens.contracts import QueryRequest, ReasonCode

_PACKING_EXCLUSION = re.compile(
    r"\b(?:not|isn['’]t|aren['’]t)\s+(?:really\s+)?"
    r"(?:needed|necessary|essential|required)\b|"
    r"\b(?:do\s+not|don['’]t)\s+need\b|"
    r"\b(?:leave|take|remove|skip)\s+(?:it\s+)?out\b|"
    r"\b(?:should\s+not|shouldn['’]t|avoid)\b.{0,24}\bpack(?:ing)?\b",
    re.IGNORECASE,
)
_PACKING_CONTEXT = re.compile(
    r"\b(?:bag|bags|kit|kits|pack|packing|grab-and-go|go-bag)\b", re.IGNORECASE
)
_GENERAL_MISTAKE_DISCUSSION = re.compile(r"\b(?:mistake|mistakes|error|errors)\b", re.I)
_EXPLICIT_SOURCE_ATTRIBUTION = re.compile(
    r"\baccording\s+to\b|\b(?:what\s+(?:does|do)|does)\b.{0,80}\b(?:say|says|"
    r"recommend|require|follow)\b|\b(?:source|document|guide|checklist)\b.{0,80}\b(?:say|says|"
    r"recommend|require|follow)\b|\b(?:say|says|recommend|require|follow)\b.{0,80}"
    r"\b(?:source|document|guide|checklist)\b",
    re.IGNORECASE,
)
_NAMED_INDIVIDUAL_FIRE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9'’.-]*\s+){1,4}(?:Fire|Wildfire|Incident)"
    r"\b(?!\s+(?:Cent(?:re|er)|Service|Guide|Program))"
)
_DEICTIC_FOLLOWUP = re.compile(
    r"\b(?:it|its|that|this|they|them|there|those|these|"
    r"the (?:first|second|third|other|closest|nearest) one|"
    r"that (?:guidance|system|advice|status)|right now|what about)\b"
)
_SELECTED_FIRE_DEIXIS = re.compile(
    r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|record)\b", re.I
)


def focused_question(question: str) -> str:
    """Remove a long obvious preamble while preserving the final explicit question."""

    if len(question) < 500:
        return question
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", question)]
    explicit = [part for part in sentences if part.endswith("?") and len(part.split()) >= 4]
    if explicit and len(explicit[-1]) <= 500:
        return explicit[-1]
    return question


def _is_elliptical_followup(question: str) -> bool:
    current = focused_question(question)
    return len(current.split()) <= 16 and bool(_DEICTIC_FOLLOWUP.search(current.casefold()))


def prior_anchor_user_question(request: QueryRequest) -> str | None:
    """Return the nearest useful user subject while skipping bare deictic turns."""

    previous = [turn.content for turn in request.history if turn.role == "user"]
    for content in reversed(previous):
        if coarse_location_from_question(content) is not None:
            return content
        if extracted_located_fire_name(content) is not None:
            return content
        if not _is_elliptical_followup(content):
            return content
    return previous[-1] if previous else None


def resolved_user_question(request: QueryRequest) -> str:
    """Name the previous user subject for a genuinely elliptical follow-up."""

    current = focused_question(request.question)
    if not _is_elliptical_followup(current):
        return current
    prior = prior_anchor_user_question(request)
    if not prior:
        return current
    return f"Regarding the earlier question '{prior}', {current}"[:2_000]


def conversation_planning_question(request: QueryRequest) -> str:
    """Attach prior context unless the turn explicitly names a selected fire."""

    current = focused_question(request.question)
    if _SELECTED_FIRE_DEIXIS.search(current):
        return current
    return resolved_user_question(request)


def continues_prior_live_place(request: QueryRequest) -> bool:
    """Whether an elliptical turn should reuse the prior live location."""

    current = focused_question(request.question)
    if _SELECTED_FIRE_DEIXIS.search(current) or not _is_elliptical_followup(current):
        return False
    prior = prior_anchor_user_question(request)
    return bool(
        prior
        and parse_request_intent(prior).has_live_records
        and coarse_location_from_question(prior) is not None
    )


def _routing_texts(request: QueryRequest) -> tuple[str, ...]:
    """Use history only for a genuinely elliptical current question."""

    current = focused_question(request.question).lower()
    if not _is_elliptical_followup(current):
        return (current,)
    prior = prior_anchor_user_question(request)
    return (current, f"{prior.lower()} {current}") if prior else (current,)


def _deictic_action_boundary(request: QueryRequest) -> ReasonCode | None:
    """Resolve only a narrow high-risk antecedent for deictic actions."""

    lowered = request.question.lower()
    if not re.search(
        r"\bshould\s+(?:i|we)\s+(?:do|follow|take|use)\s+(?:that|this|it)\b|"
        r"\bshould\s+(?:i|we)\s+take\s+(?:that|this|the)\s+(?:road|route|way)\b|"
        r"\b(?:can|could|may)\s+(?:i|we)\s+return\b|"
        r"\bis it safe to do that\b",
        lowered,
    ):
        return None
    antecedent = " ".join(turn.content.lower() for turn in request.history[-2:])
    if any(
        term in antecedent for term in ("dose", "inhaler", "medication", "prescribe", "diagnos")
    ):
        return ReasonCode.PERSONALIZED_MEDICAL_ADVICE
    if any(
        term in antecedent
        for term in ("leave", "evacuat", "return", "stay", "route", "road", "alert", "order")
    ):
        return ReasonCode.PERSONALIZED_SAFETY_DECISION
    return None


def reviewed_guidance_intent(question: str) -> bool:
    """Recognize only topics represented by the reviewed static collection."""

    return bool(
        reviewed_return_condition_intent(question)
        or parse_request_intent(question).has_reviewed_guidance
    )


def explicit_corpus_attribution(question: str) -> bool:
    """Keep a reader's named-source request in the reviewed-evidence lane."""

    return bool(
        corpus_identifiers(question)
        or _EXPLICIT_SOURCE_ATTRIBUTION.search(question)
        or any(
            re.search(pattern, question.casefold()) for pattern in _CORPUS_REFERENCE_PATTERNS
        )
    )


def _selected_or_deictic_record_request(request: QueryRequest, question: str) -> bool:
    return bool(
        request.context.selected_live_result_id
        and (_SELECTED_FIRE_DEIXIS.search(question) or _is_elliptical_followup(question))
    )


def _historical_wildfire_explanation(question: str, *, temporal_scope: TemporalScope) -> bool:
    tokens = frozenset(re.findall(r"[a-z0-9]+", question.casefold()))
    return bool(
        temporal_scope == TemporalScope.NONCURRENT
        and tokens & {"fire", "wildfire", "fires", "wildfires"}
        and tokens & {"season", "seasons", "history", "historical"}
        and extracted_located_fire_name(question) is None
        and _NAMED_INDIVIDUAL_FIRE.search(question) is None
    )


def _named_individual_fire_request(question: str) -> bool:
    return bool(
        extracted_located_fire_name(question) is not None
        or _NAMED_INDIVIDUAL_FIRE.search(question) is not None
    )


def prefers_general_background(request: QueryRequest) -> bool:
    """Select the labelled background lane for deliberately ordinary discussion."""

    current = focused_question(request.question)
    if is_capability_question(current.casefold()):
        return False
    parsed = parse_request_intent(current)
    if parsed.has_live_records or explicit_corpus_attribution(current):
        return False
    if _selected_or_deictic_record_request(request, current):
        return False
    if _PACKING_EXCLUSION.search(current) is not None:
        context = " ".join(
            [current, *(turn.content for turn in request.history[-4:] if turn.role == "user")]
        )
        if _PACKING_CONTEXT.search(context) is not None:
            return True
    if reviewed_guidance_intent(current):
        return False
    if _historical_wildfire_explanation(current, temporal_scope=parsed.temporal_scope):
        return True
    return _GENERAL_MISTAKE_DISCUSSION.search(current) is not None


def skips_provider_planning(request: QueryRequest) -> bool:
    """Skip provider planning when reviewed guidance is already determined."""

    if reviewed_guidance_intent(request.question):
        return True
    resolved = resolved_user_question(request)
    return resolved != focused_question(request.question) and reviewed_guidance_intent(resolved)


def publication_question(request: QueryRequest) -> str:
    """Compile against the current ask, not a retrieved earlier subject."""

    if skips_provider_planning(request):
        return focused_question(request.question)
    return resolved_user_question(request)
