from __future__ import annotations

import pytest

from firelens.answering.context import decide_support
from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    QueryPlan,
    QueryRoute,
    RetrievalRequest,
    SupportStatus,
    TemporalClass,
)


def _packet(question: str, quote: str) -> EvidencePacket:
    return _packet_with_quotes(question, [quote])


def _packet_with_quotes(question: str, quotes: list[str]) -> EvidencePacket:
    return EvidencePacket(
        question=question,
        corpus_version="polarity-guard.v1",
        items=[
            EvidenceSpan(
                evidence_id=f"E{index}",
                primary_chunk_ids=[f"preparedbc:{index}"],
                chunk_ids=[f"preparedbc:{index}"],
                primary_text=quote,
                context_text=quote,
                source_id="preparedbc",
                title="PreparedBC guidance",
                publisher="PreparedBC",
                canonical_url="https://example.test/preparedbc",
                page_number=1,
                section_title="Grab-and-go bags",
                locator="page:1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256="a" * 64,
            )
            for index, quote in enumerate(quotes, start=1)
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(quote_id=f"E{index}Q1", evidence_id=f"E{index}", text=quote)
            for index, quote in enumerate(quotes, start=1)
        ],
    )


def _plan(question: str, retrieval_query: str) -> QueryPlan:
    return QueryPlan(
        original_question=question,
        normalized_question=question,
        route=QueryRoute.RELATED,
        retrieval_requests=[RetrievalRequest(query=retrieval_query)],
    )


_AFFIRMATIVE_BAG_GUIDANCE = (
    "Build grab-and-go bags with water, food, and copies of important documents."
)


@pytest.mark.parametrize(
    "question",
    [
        "According to PreparedBC, what is not needed in a grab-and-go bag?",
        "Which supplies are unnecessary for an emergency kit?",
        "Which items do I not need in an emergency kit?",
        "What is not required in a go bag?",
        "What should be omitted from a grab-and-go bag?",
    ],
)
def test_exclusion_requests_reject_affirmative_checklist_evidence(question: str) -> None:
    decision = decide_support(
        _plan(question, "What should I include in a grab-and-go bag?"),
        _packet(question, _AFFIRMATIVE_BAG_GUIDANCE),
    )

    assert decision.status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert decision.reason_code.value == "no_approved_evidence"


def test_exclusion_request_accepts_genuine_negative_guidance() -> None:
    question = "What is not needed in a grab-and-go bag?"
    quote = "You do not need glass containers in a grab-and-go bag."

    decision = decide_support(
        _plan(question, "What should I include in a grab-and-go bag?"),
        _packet(question, quote),
    )

    assert decision.status == SupportStatus.ANSWERABLE


@pytest.mark.parametrize(
    "quote",
    [
        "Do not forget to pack medication in a grab-and-go bag.",
        "Avoid forgetting to include water in an emergency kit.",
    ],
)
def test_exclusion_request_rejects_negated_inclusion_guidance(quote: str) -> None:
    question = "What is not needed in a grab-and-go bag?"

    decision = decide_support(
        _plan(question, "What should I include in a grab-and-go bag?"),
        _packet(question, quote),
    )

    assert decision.status == SupportStatus.INSUFFICIENT_EVIDENCE


def test_unrelated_exclusion_evidence_cannot_support_bag_omission_request() -> None:
    question = "What is not needed in a grab-and-go bag?"
    packet = _packet_with_quotes(
        question,
        [
            _AFFIRMATIVE_BAG_GUIDANCE,
            "You do not need paper copies for an online bank appointment.",
        ],
    )

    decision = decide_support(
        _plan(question, "What should I include in a grab-and-go bag?"), packet
    )

    assert decision.status == SupportStatus.INSUFFICIENT_EVIDENCE


def test_positive_bag_question_still_accepts_affirmative_guidance() -> None:
    question = "What should I include in a grab-and-go bag?"

    decision = decide_support(
        _plan(question, question),
        _packet(question, _AFFIRMATIVE_BAG_GUIDANCE),
    )

    assert decision.status == SupportStatus.ANSWERABLE
