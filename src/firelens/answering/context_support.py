"""Deterministic lexical support decisions for reviewed evidence packets.

This module intentionally owns the pure support and polarity checks.  Packet
assembly remains in :mod:`firelens.answering.context_packet`; the public
``answering.context`` module re-exports both surfaces for compatibility.
"""

from __future__ import annotations

import re
from functools import lru_cache

from firelens.contracts import (
    EvidencePacket,
    QueryPlan,
    QueryRoute,
    ReasonCode,
    RetrievalBundle,
    SupportDecision,
    SupportStatus,
)
from firelens.retrieval.bm25 import tokenize

_ASPECT_STOPWORDS = {
    "an",
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "into",
    "me",
    "my",
    "our",
    "on",
    "possible",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "user",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
    "your",
    "question",
    "say",
    "simpler",
    "difference",
    "information",
    "guidance",
    "word",
    "words",
}

_ADMINISTRATIVE_STEMS = (
    "apply",
    "application",
    "bylaw",
    "compensat",
    "certif",
    "deadline",
    "eligib",
    "fine",
    "penalt",
    "fee",
    "mandat",
    "permit",
    "policy",
    "register",
    "registration",
    "template",
)

SUPPORT_TOKEN_OVERLAP_FLOOR = 0.4

# A request for an omission has the opposite direction from guidance that
# lists what to include. Lexical topic overlap alone cannot establish that
# direction, particularly when a planner normalizes retrieval to a positive
# checklist request.
_EXCLUSION_REQUEST = re.compile(
    r"\b(?:what|which)\b.{0,100}\b(?:"
    r"(?:not|isn['’]t|aren['’]t)\s+(?:really\s+)?"
    r"(?:needed|necessary|essential|required)|"
    r"(?:do\s+(?:(?:i|we|you)\s+)?not|don['’]t)\s+need|"
    r"unnecessary|"
    r"(?:should|can)\s+be\s+(?:omitted|excluded|removed|skipped)|"
    r"(?:omit|exclude|remove|skip|leave\s+out)"
    r")\b|"
    r"\b(?:can|should)\s+(?:i|we|you)\s+"
    r"(?:omit|exclude|remove|skip|leave\s+out)\b",
    re.IGNORECASE,
)
_EXCLUSION_EVIDENCE = re.compile(
    r"\b(?:not|isn['’]t|aren['’]t)\s+(?:really\s+)?"
    r"(?:needed|necessary|essential|required|recommended)\b|"
    r"\b(?:do\s+not|don['’]t)\s+need\b|"
    r"\b(?:do\s+not|don['’]t|should\s+not|shouldn['’]t)\s+"
    r"(?:(?:ever|generally|just|only|really|typically|usually|a|an|any|extra|the)\s+){0,2}"
    r"(?:include|pack|bring|take|carry)\b|"
    r"\bavoid\s+(?:including|packing|bringing|taking|carrying)\b|"
    r"\b(?:omit|exclude|remove|skip|leave\s+out)\b",
    re.IGNORECASE,
)
_EXCLUSION_DIRECTION_TOKENS = frozenset(
    {
        "a",
        "an",
        "are",
        "aren",
        "be",
        "can",
        "do",
        "dont",
        "essential",
        "exclude",
        "excluded",
        "i",
        "is",
        "isnt",
        "leave",
        "necessary",
        "need",
        "needed",
        "not",
        "omit",
        "omitted",
        "out",
        "really",
        "remove",
        "removed",
        "required",
        "should",
        "skip",
        "skipped",
        "unnecessary",
        "we",
        "what",
        "which",
        "you",
    }
)


@lru_cache(maxsize=4_096)
def _support_tokens(text: str) -> frozenset[str]:
    """Normalize a small, domain-stable set of morphological equivalents."""

    normalized: set[str] = set()
    for token in tokenize(text):
        if token == "meaning":
            normalized.add("mean")
        elif token.startswith("prepar"):
            normalized.add("prepare")
        elif token.startswith("evacuat") or token in {"leave", "leaving"}:
            normalized.add("evacuate")
        elif token.startswith("famil") or token.startswith("household"):
            normalized.add("household")
        elif token.startswith("plan"):
            normalized.add("plan")
        elif token in {"bag", "bags", "kit", "kits"}:
            normalized.add("kit")
        elif token in {"phase", "phases", "stage", "stages"}:
            normalized.add("stage")
        elif token.endswith("s") and len(token) > 4:
            normalized.add(token[:-1])
        else:
            normalized.add(token)
    return frozenset(normalized)


@lru_cache(maxsize=8_192)
def support_token_overlap(text: str, target: str, *, minimum_overlap: int = 1) -> float:
    """Return deterministic normalized target-token coverage for ``text``.

    This is a lexical relevance floor, not a semantic-entailment decision. The
    target owns the denominator so unrelated source text cannot make an
    otherwise unsupported request appear covered.
    """

    required = {
        token
        for token in _support_tokens(target)
        if token not in _ASPECT_STOPWORDS and len(token) > 1
    }
    if not required:
        return 0.0
    available = _support_tokens(text)
    overlap = required & available
    if len(overlap) < min(minimum_overlap, len(required)):
        return 0.0
    return len(overlap) / len(required)


def _aspect_supported(
    aspect: str,
    packet: EvidencePacket,
    *,
    minimum_ratio: float = SUPPORT_TOKEN_OVERLAP_FLOOR,
) -> bool:
    return any(
        support_token_overlap(item.primary_text, aspect, minimum_overlap=2) >= minimum_ratio
        for item in packet.items
    )


def _requires_exclusion_evidence(question: str) -> bool:
    """Return whether the user explicitly asks what should be left out."""

    return _EXCLUSION_REQUEST.search(question) is not None


def _exclusion_topic(question: str) -> str:
    """Remove exclusion direction so support remains anchored to the topic."""

    return " ".join(
        token for token in tokenize(question) if token not in _EXCLUSION_DIRECTION_TOKENS
    )


def _direct_exclusion_evidence(text: str, topic: str) -> bool:
    return _EXCLUSION_EVIDENCE.search(text) is not None and (
        support_token_overlap(text, topic) >= SUPPORT_TOKEN_OVERLAP_FLOOR
    )


def _has_exclusion_evidence(question: str, packet: EvidencePacket) -> bool:
    """Require exclusion wording and topic overlap from the same evidence item."""

    topic = _exclusion_topic(question)
    if not topic:
        return False
    items_by_id = {item.evidence_id: item for item in packet.items}
    if any(_direct_exclusion_evidence(item.primary_text, topic) for item in packet.items):
        return True
    for candidate in packet.quote_candidates:
        item = items_by_id.get(candidate.evidence_id)
        if item is None or _EXCLUSION_EVIDENCE.search(candidate.text) is None:
            continue
        if (
            _direct_exclusion_evidence(candidate.text, topic)
            or support_token_overlap(item.primary_text, topic) >= SUPPORT_TOKEN_OVERLAP_FLOOR
        ):
            return True
    return False


def decide_support(
    plan: QueryPlan,
    packet: EvidencePacket | None,
    retrieval: RetrievalBundle | None = None,
) -> SupportDecision:
    immediate = _immediate_support_decision(plan, packet, retrieval)
    if immediate is not None:
        return immediate
    assert packet is not None
    authority = _authority_support_decision(plan, packet)
    if authority is not None:
        return authority
    aspect = _aspect_support_decision(plan, packet)
    if aspect is not None:
        return aspect
    return SupportDecision(
        status=SupportStatus.ANSWERABLE,
        reason_code=ReasonCode.APPROVED_STATIC_EVIDENCE,
        explanation="Approved stable guidance is available.",
        supported_aspects=list(plan.required_aspects),
    )


def _immediate_support_decision(
    plan: QueryPlan,
    packet: EvidencePacket | None,
    retrieval: RetrievalBundle | None,
) -> SupportDecision | None:
    if plan.route == QueryRoute.PROHIBITED:
        return SupportDecision(
            status=SupportStatus.PROHIBITED,
            reason_code=plan.boundary_reason or ReasonCode.PERSONALIZED_SAFETY_DECISION,
            explanation=(
                "FireLens cannot provide personalized medical advice."
                if plan.boundary_reason == ReasonCode.PERSONALIZED_MEDICAL_ADVICE
                else (
                    "Conversation text cannot override FireLens safety and evidence rules."
                    if plan.boundary_reason == ReasonCode.POLICY_MANIPULATION
                    else (
                        "FireLens cannot provide personalized safety advice, select evacuation "
                        "routes, or decide whether you should stay, leave, evacuate, or return."
                    )
                )
            ),
        )
    if plan.route == QueryRoute.LIVE:
        return SupportDecision(
            status=SupportStatus.REQUIRES_LIVE_DATA,
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            explanation="This question requires current official information that is not available in static RAG.",
        )
    if retrieval is not None and not retrieval.complete:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.RETRIEVAL_INCOMPLETE,
            explanation="The required retrieval pipeline did not complete.",
        )
    if packet is None or not packet.items:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation="No approved static evidence was available for this question.",
        )
    if any(item.temporal_class != "stable_guidance" for item in packet.items):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.WRONG_TEMPORAL_CLASS,
            explanation="Retrieved evidence has an unsupported temporal classification.",
        )
    if _requires_exclusion_evidence(plan.original_question) and not _has_exclusion_evidence(
        plan.original_question, packet
    ):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation=(
                "The request asks what should be omitted, but the selected evidence only "
                "describes what to include."
            ),
        )
    support_queries = [
        plan.original_question,
        *(request.query for request in plan.retrieval_requests),
    ]
    if not any(
        _aspect_supported(query, packet, minimum_ratio=0.5) for query in support_queries
    ):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation=(
                "The reviewed sources are related, but they do not verify the requested "
                "claim as official guidance."
            ),
        )
    if packet.conflicts:
        return SupportDecision(
            status=SupportStatus.CONFLICT,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            explanation=(
                "The selected approved sources contain conflicting guidance that must be "
                "shown rather than resolved silently."
            ),
        )
    return None


def _authority_support_decision(
    plan: QueryPlan, packet: EvidencePacket
) -> SupportDecision | None:
    required = set().union(
        *(request.required_authorities for request in plan.retrieval_requests)
    )
    available = {item.authority_class for item in packet.items}
    if required and not required.issubset(available):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.REQUIRED_AUTHORITY_MISSING,
            explanation="One or more required authority classes were absent from selected evidence.",
            # Retrieval queries can be planner-normalized. Reader-facing limitations
            # must instead repeat only the user's original target.
            missing_aspects=[plan.original_question],
        )
    for request in plan.retrieval_requests:
        if not request.required_authorities:
            continue
        authoritative_packet = packet.model_copy(
            update={
                "items": [
                    item
                    for item in packet.items
                    if item.authority_class in request.required_authorities
                ]
            }
        )
        if not (
            _aspect_supported(request.query, authoritative_packet)
            or _aspect_supported(plan.original_question, authoritative_packet)
        ):
            return SupportDecision(
                status=SupportStatus.INSUFFICIENT_EVIDENCE,
                reason_code=ReasonCode.REQUIRED_AUTHORITY_MISSING,
                explanation=(
                    "The required authority appears in retrieval, but its evidence does not "
                    "directly support the retrieval request."
                ),
                # A retrieval query may be model-planned or normalized. Preserve the
                # user-owned request, not planner wording, in public limitations.
                missing_aspects=[plan.original_question],
            )
    if any(
        stem in plan.original_question.casefold() for stem in _ADMINISTRATIVE_STEMS
    ) and not (_aspect_supported(plan.original_question, packet, minimum_ratio=0.8)):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation=(
                "The selected evidence mentions the topic but does not directly establish "
                "the requested administrative process or policy."
            ),
        )
    return None


def _aspect_support_decision(plan: QueryPlan, packet: EvidencePacket) -> SupportDecision | None:
    if plan.required_aspects:
        supported_aspects = [
            aspect for aspect in plan.required_aspects if _aspect_supported(aspect, packet)
        ]
        missing_aspects = [
            aspect for aspect in plan.required_aspects if aspect not in supported_aspects
        ]
        # A planner may over-decompose a simple question, but its rewrite may not
        # lower the evidence bar. Only strong lexical coverage of the user's own
        # wording can override a missing proposed aspect.
        deictic_question = any(
            marker in plan.original_question.casefold()
            for marker in ("that", "those", "this", "simpler", "why does it", "why does that")
        )
        resolved_request_supported = deictic_question and any(
            _aspect_supported(request.query, packet, minimum_ratio=0.6)
            for request in plan.retrieval_requests
        )
        question_directly_supported = (
            _aspect_supported(plan.original_question, packet, minimum_ratio=0.5)
            or resolved_request_supported
        )
        explicit_multi_topic = len(plan.retrieval_requests) > 1 and any(
            marker in f" {plan.original_question.casefold()} "
            for marker in (" and ", " also ", " both ", ";")
        )
        if (
            missing_aspects
            and not question_directly_supported
            and not (supported_aspects and explicit_multi_topic)
        ):
            return SupportDecision(
                status=SupportStatus.INSUFFICIENT_EVIDENCE,
                reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
                explanation="The selected evidence does not directly cover the required answer aspects.",
                missing_aspects=missing_aspects,
            )
        if missing_aspects and supported_aspects and explicit_multi_topic:
            return SupportDecision(
                status=SupportStatus.PARTIAL,
                reason_code=ReasonCode.RETRIEVAL_INCOMPLETE,
                explanation="The selected evidence supports only part of the request.",
                supported_aspects=supported_aspects,
                missing_aspects=missing_aspects,
            )
    return None
