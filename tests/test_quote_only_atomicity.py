"""Regression locks for quote-only evacuation-stage extraction artifacts."""

from __future__ import annotations

from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    ResponseMode,
    TemporalClass,
)
from firelens.publication.compiler import compile_high_risk_answer
from firelens.publication.fallback import is_atomic_official_quote_only
from firelens.publication.records import admitted_corpus_index, get_versioned

_INTERLEAVED_EVACUATION_TABLE = (
    "Evacuation Alert: Evacuation Order: Evacuation Rescind:\n"
    "Be ready to leave You are at risk. Leave All is now safe and you\n"
    "on short notice. IMMEDIATELY. can return home."
)


def _packet_for_admitted_quote(question: str, quote: str) -> EvidencePacket:
    chunk_id, row = next(
        (chunk_id, row)
        for chunk_id, row in admitted_corpus_index().items()
        if row["text"] == quote
    )
    item = EvidenceSpan(
        evidence_id="E1",
        primary_chunk_ids=[chunk_id],
        chunk_ids=[chunk_id],
        primary_text=quote,
        context_text=quote,
        source_id=chunk_id.split(":", maxsplit=1)[0],
        title="PreparedBC wildfire preparedness guide",
        publisher="PreparedBC",
        canonical_url=row["canonical_url"],
        page_number=10,
        section_title=None,
        locator="page:10",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
        document_sha256=row["document_sha256"],
    )
    return EvidencePacket(
        question=question,
        corpus_version="quote-only-atomicity.v1",
        items=[item],
        quote_candidates=[
            EvidenceQuoteCandidate(quote_id="E1Q1", evidence_id="E1", text=quote)
        ],
    )


def _packet_for_typed_claims(question: str, *claim_ids: str) -> EvidencePacket:
    items: list[EvidenceSpan] = []
    candidates: list[EvidenceQuoteCandidate] = []
    for index, claim_id in enumerate(claim_ids, start=1):
        record = get_versioned(claim_id)
        evidence_id = f"E{index}"
        items.append(
            EvidenceSpan(
                evidence_id=evidence_id,
                primary_chunk_ids=list(record.source_span_ids),
                chunk_ids=list(record.source_span_ids),
                primary_text=record.source_span_text,
                context_text=record.source_span_text,
                source_id=f"source-{index}",
                title=record.authority,
                publisher=record.authority,
                canonical_url=record.canonical_url,
                page_number=index,
                section_title=None,
                locator=f"page:{index}",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=record.record.source_document_sha256 or "0" * 64,
            )
        )
        candidates.append(
            EvidenceQuoteCandidate(
                quote_id=f"{evidence_id}Q1",
                evidence_id=evidence_id,
                text=record.source_span_text,
            )
        )
    return EvidencePacket(
        question=question,
        corpus_version="quote-only-atomicity.v1",
        items=items,
        quote_candidates=candidates,
    )


def test_interleaved_evacuation_table_is_not_atomic_quote_only_support() -> None:
    assert not is_atomic_official_quote_only(_INTERLEAVED_EVACUATION_TABLE)

    response = compile_high_risk_answer(
        "Can I leave Kelowna now?",
        _packet_for_admitted_quote("Can I leave Kelowna now?", _INTERLEAVED_EVACUATION_TABLE),
        trace_id="interleaved-evacuation-table",
    )

    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert response.claims == []
    assert _INTERLEAVED_EVACUATION_TABLE not in (response.answer or "")


def test_clean_single_stage_and_conditional_quotes_remain_atomic() -> None:
    assert is_atomic_official_quote_only("Evacuation Alert: Be ready to leave on short notice.")
    assert is_atomic_official_quote_only(
        "Evacuation Order: You are at risk and must leave immediately."
    )
    assert is_atomic_official_quote_only("Return only when officials say it is safe to do so.")


def test_structured_alert_and_order_comparison_remains_available() -> None:
    question = "What is the difference between an evacuation alert and an evacuation order?"
    response = compile_high_risk_answer(
        question,
        _packet_for_typed_claims(question, "TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"),
        trace_id="structured-stage-comparison",
    )

    assert response.response_mode == ResponseMode.GROUNDED
    assert {
        claim.publication.typed_claim_id
        for claim in response.claims
        if claim.publication is not None
    } == {"TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"}
