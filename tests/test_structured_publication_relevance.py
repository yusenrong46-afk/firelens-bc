from __future__ import annotations

import asyncio

from firelens.answering.grounded import GroundedAnswerEngine
from firelens.answering.typed_records import load_inventory, match_quote
from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    ReasonCode,
    ResponseMode,
    TemporalClass,
)
from firelens.providers.fake import FakeProvider
from firelens.publication.compiler import (
    compile_high_risk_answer,
    select_typed_claim_ids,
)
from firelens.publication.records import get_versioned


def _bound_packet(question: str, *claim_ids: str) -> EvidencePacket:
    items: list[EvidenceSpan] = []
    candidates: list[EvidenceQuoteCandidate] = []
    for index, claim_id in enumerate(claim_ids, start=1):
        record = get_versioned(claim_id)
        authority = (
            AuthorityClass.PROVINCIAL_PUBLIC_HEALTH
            if "Disease Control" in record.authority
            else AuthorityClass.PROVINCIAL_GOVERNMENT
        )
        evidence_id = f"E{index}"
        items.append(
            EvidenceSpan(
                evidence_id=evidence_id,
                primary_chunk_ids=list(record.source_span_ids),
                chunk_ids=list(record.source_span_ids),
                primary_text=record.source_span_text,
                context_text=record.source_span_text,
                source_id=f"source-{index}",
                title=f"Source {index}",
                publisher=record.authority,
                canonical_url=f"https://example.test/source-{index}",
                page_number=index,
                section_title=None,
                locator=f"page:{index}",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=authority,
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
        corpus_version="structured-relevance.v1",
        items=items,
        quote_candidates=candidates,
    )


def test_question_relevance_omits_unrelated_packet_claim() -> None:
    packet = _bound_packet(
        "What does an evacuation order mean?",
        "TC-EVAC-ORDER-001",
        "TC-SMOKE-012-01",
    )

    response = compile_high_risk_answer(
        packet.question,
        packet,
        trace_id="relevant-only",
    )

    typed_ids = {
        claim.publication.typed_claim_id
        for claim in response.claims
        if claim.publication is not None
    }
    assert typed_ids == {"TC-EVAC-ORDER-001"}
    assert response.response_mode == ResponseMode.GROUNDED
    assert response.validation is not None and response.validation.accepted


def test_supported_aspects_preserve_real_multi_aspect_coverage() -> None:
    packet = _bound_packet(
        "Explain both topics.",
        "TC-EVAC-ORDER-001",
        "TC-SMOKE-012-01",
    )

    outcome = asyncio.run(
        GroundedAnswerEngine(FakeProvider(dimensions=8)).answer(
            packet.question,
            packet,
            trace_id="multi-aspect",
            supported_aspects=(
                "evacuation order meaning",
                "wildfire smoke health risk",
            ),
        )
    )

    typed_ids = {
        claim.publication.typed_claim_id
        for claim in outcome.response.claims
        if claim.publication is not None
    }
    assert typed_ids == {"TC-EVAC-ORDER-001", "TC-SMOKE-012-01"}
    assert outcome.response.response_mode == ResponseMode.GROUNDED
    assert outcome.attempts == 0


def test_quote_only_high_risk_response_is_partial() -> None:
    quote = "Avoid driving through areas of dense smoke."
    packet = EvidencePacket(
        question="What should people do in dense smoke?",
        corpus_version="quote-only-relevance.v1",
        items=[
            EvidenceSpan(
                evidence_id="E1",
                primary_chunk_ids=["quote-only:chunk:1"],
                chunk_ids=["quote-only:chunk:1"],
                primary_text=quote,
                context_text=quote,
                source_id="official-smoke",
                title="Official smoke source",
                publisher="Province of British Columbia",
                canonical_url="https://example.test/smoke",
                page_number=1,
                section_title=None,
                locator="page:1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256="1" * 64,
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(quote_id="E1Q1", evidence_id="E1", text=quote)
        ],
    )

    response = compile_high_risk_answer(packet.question, packet, trace_id="quote-only")

    assert response.response_mode == ResponseMode.PARTIAL
    assert response.validation is not None and response.validation.accepted
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.kind.value == "official_quote_only"


def test_quote_only_fallback_is_omitted_when_structured_claim_covers_target() -> None:
    question = "What belongs in a grab-and-go bag?"
    packet = _bound_packet(question, "TC-FIRESMART-021-01")
    quote = "Keep additional grab-and-go bags at work and in your vehicle."
    extra_item = EvidenceSpan(
        evidence_id="E2",
        primary_chunk_ids=["official-grab-bag:chunk:2"],
        chunk_ids=["official-grab-bag:chunk:2"],
        primary_text=quote,
        context_text=quote,
        source_id="official-grab-bag",
        title="Official grab-and-go bag source",
        publisher="Province of British Columbia",
        canonical_url="https://example.test/grab-bag",
        page_number=2,
        section_title=None,
        locator="page:2",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
        document_sha256="2" * 64,
    )
    packet = EvidencePacket(
        question=question,
        corpus_version=packet.corpus_version,
        items=[*packet.items, extra_item],
        quote_candidates=[
            *packet.quote_candidates,
            EvidenceQuoteCandidate(quote_id="E2Q1", evidence_id="E2", text=quote),
        ],
    )

    response = compile_high_risk_answer(question, packet, trace_id="structured-covers-target")

    assert response.response_mode == ResponseMode.GROUNDED
    assert len(response.claims) == 1
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.kind.value == "structured_reviewed"


def test_compiler_rechecks_packet_identity_and_fails_closed() -> None:
    packet = _bound_packet(
        "What does an evacuation order mean?",
        "TC-EVAC-ORDER-001",
    )
    malformed = packet.model_copy(
        update={
            "quote_candidates": [
                packet.quote_candidates[0].model_copy(
                    update={"text": "This sentence is not present in the linked source."}
                )
            ]
        }
    )

    response = compile_high_risk_answer(
        malformed.question,
        malformed,
        trace_id="malformed-packet",
    )

    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert response.reason_code == ReasonCode.DRAFT_VALIDATION_FAILED
    assert response.claims == []
    assert response.validation is not None
    assert response.validation.accepted is False
    assert any("not exact primary source text" in error for error in response.validation.errors)


def test_match_quote_rejects_sub_atomic_fragments() -> None:
    assert len("Evacuation Order This") < 24
    assert match_quote("Evacuation Order This") == []


def test_atomic_floor_preserves_every_admitted_inventory_match() -> None:
    failures: dict[str, list[str]] = {}
    for record in load_inventory().records:
        if record.binding_kind != "corpus_chunk":
            continue
        if not get_versioned(record.claim_id).available_for_structured_support:
            continue
        packet = _bound_packet(record.canonical_text, record.claim_id)
        selected = select_typed_claim_ids(packet)
        if selected != [record.claim_id]:
            failures[record.claim_id] = selected
    assert failures == {}
