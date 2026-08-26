from __future__ import annotations

import asyncio
from pathlib import Path

from rag_helpers import make_chunk, make_runtime

from firelens.answering.grounded import GroundedAnswerEngine
from firelens.answering.typed_records import load_inventory, match_quote
from firelens.config import FireLensConfig
from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    QueryRequest,
    ReasonCode,
    ResponseMode,
    TemporalClass,
)
from firelens.providers.fake import FakeProvider
from firelens.publication.compiler import (
    compile_high_risk_answer,
    select_typed_claim_ids,
)
from firelens.publication.fallback import admitted_official_quote_source
from firelens.publication.records import admitted_corpus_index, get_versioned
from firelens.runtime import load_runtime

_ADMITTED_GRAB_AND_GO_LIST = (
    "Grab-and-Go Bag\n"
    "• Pen & notepad\n"
    "• Phone charger & battery bank\n"
    "• Flashlight\n"
    "• Radio\n"
    "• First aid kit\n"
    "• Personal toiletries\n"
    "• Seasonal clothing\n"
    "• Food & water\n"
    "• Batteries\n"
    "• Whistle\n"
    "• Emergency plan"
)
_ADMITTED_PREPAREDBC_PDF = (
    "https://www2.gov.bc.ca/assets/gov/public-safety-and-emergency-services/"
    "emergency-preparedness-response-recovery/embc/preparedbc/preparedbc-guides/"
    "wildfire_preparedness_guide.pdf"
)


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
                canonical_url=record.canonical_url
                or "https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery",
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


def _admitted_span_for_quote(evidence_id: str, quote: str, offset: int) -> EvidenceSpan:
    for chunk_id, row in admitted_corpus_index().items():
        corpus_text = row["text"]
        if quote in corpus_text or " ".join(quote.split()) in " ".join(corpus_text.split()):
            return EvidenceSpan(
                evidence_id=evidence_id,
                primary_chunk_ids=[chunk_id],
                chunk_ids=[chunk_id],
                primary_text=quote,
                context_text=quote,
                source_id=chunk_id.split(":", 1)[0],
                title="Official source",
                publisher="Province of British Columbia",
                canonical_url=row["canonical_url"],
                page_number=offset,
                section_title=None,
                locator=f"page:{offset}",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=row["document_sha256"],
            )
    return EvidenceSpan(
        evidence_id=evidence_id,
        primary_chunk_ids=[f"official-source:chunk:{offset}"],
        chunk_ids=[f"official-source:chunk:{offset}"],
        primary_text=quote,
        context_text=quote,
        source_id=f"official-source-{offset}",
        title=f"Official source {offset}",
        publisher="Province of British Columbia",
        canonical_url="https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery",
        page_number=offset,
        section_title=None,
        locator=f"page:{offset}",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
        document_sha256=f"{offset % 10}" * 64,
    )


def _with_quote_sources(packet: EvidencePacket, *quotes: str) -> EvidencePacket:
    items = list(packet.items)
    candidates = list(packet.quote_candidates)
    for offset, quote in enumerate(quotes, start=len(items) + 1):
        evidence_id = f"E{offset}"
        items.append(_admitted_span_for_quote(evidence_id, quote, offset))
        candidates.append(
            EvidenceQuoteCandidate(
                quote_id=f"{evidence_id}Q1",
                evidence_id=evidence_id,
                text=quote,
            )
        )
    return packet.model_copy(update={"items": items, "quote_candidates": candidates})


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
    quote = _ADMITTED_GRAB_AND_GO_LIST
    packet = _with_quote_sources(
        EvidencePacket(
            question="What basic items should I put in a wildfire grab-and-go bag?",
            corpus_version="quote-only-relevance.v1",
            items=[],
        ),
        quote,
    )

    assert admitted_official_quote_source(packet.items[0], quote)

    response = compile_high_risk_answer(packet.question, packet, trace_id="quote-only")

    assert response.response_mode == ResponseMode.PARTIAL
    assert response.validation is not None and response.validation.accepted
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.kind.value == "official_quote_only"


def test_population_specific_request_does_not_publish_a_different_group_claim() -> None:
    question = "What should I do about wildfire smoke if I am pregnant?"
    quote = (
        "People at higher risk\n"
        "People with pre-existing chronic conditions such as asthma, chronic \u200b"
        "obstructive pulmonary disease (COPD), heart disease, and diabetes\n"
        "People who are pregnant\n"
        "Infants and small children\n"
        "Elderly"
    )
    base = _bound_packet(question, "TC-VULNERABLE-023-01")
    packet = base.model_copy(
        update={
            "items": [
                base.items[0].model_copy(update={"primary_text": quote, "context_text": quote})
            ],
            "quote_candidates": [
                EvidenceQuoteCandidate(quote_id="E1Q1", evidence_id="E1", text=quote)
            ],
        }
    )

    response = compile_high_risk_answer(question, packet, trace_id="pregnancy-scope")

    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert response.reason_code == ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED
    assert response.claims == []
    assert "reviewed structured claim" in response.answer.casefold()


def test_population_specific_request_keeps_matching_reviewed_scope() -> None:
    question = "What should I do about wildfire smoke if I have a chronic health condition?"
    packet = _bound_packet(question, "TC-VULNERABLE-024-01")

    response = compile_high_risk_answer(question, packet, trace_id="chronic-scope")

    assert response.response_mode == ResponseMode.GROUNDED
    assert response.validation is not None and response.validation.accepted
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.typed_claim_id == "TC-VULNERABLE-024-01"


def test_contents_request_keeps_build_claim_and_adds_first_content_bearing_quote() -> None:
    question = "What basic items should I put in a wildfire grab-and-go bag?"
    checklist = _ADMITTED_GRAB_AND_GO_LIST
    packet = _with_quote_sources(
        _bound_packet(question, "TC-FIRESMART-021-01"),
        "Keep additional grab-and-go bags at work and in your vehicle.",
        checklist,
        "Pack pet grab-and-go bags with food, water, leashes, and carriers.",
    )

    response = compile_high_risk_answer(question, packet, trace_id="contents-facet")

    assert response.response_mode == ResponseMode.PARTIAL
    assert response.validation is not None and response.validation.accepted
    assert [claim.publication.kind.value for claim in response.claims if claim.publication] == [
        "structured_reviewed",
        "official_quote_only",
    ]
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.typed_claim_id == "TC-FIRESMART-021-01"
    assert response.claims[1].supports[0].quote == checklist
    assert "pet grab-and-go" not in (response.answer or "").casefold()
    assert "at work" not in (response.answer or "").casefold()


def test_build_request_does_not_dump_container_contents() -> None:
    question = "Should I build a grab-and-go bag?"
    packet = _with_quote_sources(
        _bound_packet(question, "TC-FIRESMART-021-01"),
        "Grab-and-Go Bag\n• Food & water\n• Flashlight\n• First aid kit",
    )

    response = compile_high_risk_answer(question, packet, trace_id="build-not-contents")

    assert response.response_mode == ResponseMode.GROUNDED
    assert response.validation is not None and response.validation.accepted
    assert len(response.claims) == 1
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.kind.value == "structured_reviewed"
    assert "food & water" not in (response.answer or "").casefold()


def test_contents_paraphrase_outside_corpus_is_not_official_wording() -> None:
    question = "What belongs in an evacuation supply box?"
    paraphrase = (
        "If you must leave during an evacuation, an evacuation supply box should "
        "include water, a blanket, and a flashlight."
    )
    packet = _with_quote_sources(
        EvidencePacket(question=question, corpus_version="generic-contents.v1", items=[]),
        "Prepare an evacuation supply box before an evacuation.",
        paraphrase,
        "Keep another evacuation supply box at work.",
    )

    response = compile_high_risk_answer(question, packet, trace_id="generic-contents")

    assert not any(paraphrase in row["text"] for row in admitted_corpus_index().values())
    assert response.claims == []
    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert not any(
        getattr(card, "support_state", None) == "official_quote_only"
        for card in (response.proof_cards or [])
    )


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


_ALERT_ORDER_COMPARISON = "What is the difference between an evacuation alert and order?"


def _typed_ids(response: object) -> set[str]:
    ids: set[str] = set()
    for claim in getattr(response, "claims", ()):
        publication = getattr(claim, "publication", None)
        typed_id = getattr(publication, "typed_claim_id", None)
        if typed_id:
            ids.add(typed_id)
    return ids


def test_alert_order_comparison_does_not_ground_one_sided_packet() -> None:
    packet = _bound_packet(
        _ALERT_ORDER_COMPARISON,
        "TC-EVAC-ORDER-001",
        "TC-EVAC-RESCIND-001",
    )

    response = compile_high_risk_answer(
        packet.question,
        packet,
        trace_id="a02-one-sided",
    )

    assert response.response_mode == ResponseMode.PARTIAL
    assert "TC-EVAC-ORDER-001" in _typed_ids(response)
    assert "TC-EVAC-ALERT-001" not in _typed_ids(response)
    limitations = " ".join(response.limitations).casefold()
    assert "not supported by selected evidence" in limitations
    assert "evacuation alert meaning" in limitations
    assert (
        "alert" not in (response.answer or "").casefold()
        or "short notice" not in (response.answer or "").casefold()
    )


def test_alert_order_comparison_does_not_let_rescind_quote_cover_alert() -> None:
    packet = _with_quote_sources(
        _bound_packet(_ALERT_ORDER_COMPARISON, "TC-EVAC-ORDER-001"),
        "Once officials determine the situation is safe, the evacuation order will "
        "be rescinded and you can return home. Continue to stay tuned for other "
        "possible evacuation alerts or orders.",
    )

    response = compile_high_risk_answer(
        packet.question,
        packet,
        trace_id="a02-rescind-quote",
    )

    assert response.response_mode == ResponseMode.PARTIAL
    assert _typed_ids(response) == {"TC-EVAC-ORDER-001"}
    kinds = {
        claim.publication.kind for claim in response.claims if claim.publication is not None
    }
    assert kinds == {"structured_reviewed"}
    limitations = " ".join(response.limitations).casefold()
    assert "not supported by selected evidence" in limitations
    assert "evacuation alert meaning" in limitations


def test_alert_order_comparison_grounds_when_both_packet_definitions_exist() -> None:
    packet = _bound_packet(
        _ALERT_ORDER_COMPARISON,
        "TC-EVAC-ALERT-001",
        "TC-EVAC-ORDER-001",
    )

    response = compile_high_risk_answer(
        packet.question,
        packet,
        trace_id="a02-both-sides",
    )

    assert response.response_mode == ResponseMode.GROUNDED
    assert _typed_ids(response) == {"TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"}
    limitations = " ".join(response.limitations).casefold()
    assert "not supported by selected evidence" not in limitations


def test_alert_order_comparison_engine_rejects_one_sided_grounded() -> None:
    packet = _bound_packet(
        _ALERT_ORDER_COMPARISON,
        "TC-EVAC-ORDER-001",
        "TC-EVAC-RESCIND-001",
    )

    outcome = asyncio.run(
        GroundedAnswerEngine(FakeProvider(dimensions=8)).answer(
            packet.question,
            packet,
            trace_id="a02-engine-one-sided",
        )
    )

    assert outcome.response.response_mode == ResponseMode.PARTIAL
    assert "TC-EVAC-ALERT-001" not in _typed_ids(outcome.response)
    assert (
        "not supported by selected evidence"
        in " ".join(outcome.response.limitations).casefold()
    )
    assert outcome.attempts == 0


def test_service_ask_does_not_ground_one_sided_alert_order_comparison(tmp_path: Path) -> None:
    order = get_versioned("TC-EVAC-ORDER-001")
    chunk = make_chunk(order.record.source_span_ids[0], order.source_span_text)

    async def run() -> None:
        runtime, _provider, _config = await make_runtime(tmp_path, chunks=[chunk])
        execution = await runtime.service.execute_ask(
            QueryRequest(question=_ALERT_ORDER_COMPARISON)
        )
        response = execution.response
        assert response.response_mode != ResponseMode.GROUNDED
        assert "TC-EVAC-ALERT-001" not in _typed_ids(response)
        if response.response_mode == ResponseMode.PARTIAL:
            assert (
                "not supported by selected evidence"
                in " ".join(response.limitations).casefold()
            )

    asyncio.run(run())


def test_comparison_paraphrases_ground_when_fused_pool_has_both_atomic_spans() -> None:
    questions = (
        _ALERT_ORDER_COMPARISON,
        "What's an evac order vs alert thing?",
        "Can you say the alert vs order difference in simpler words?",
        "Lorem ipsum filler line. " * 40
        + "What's the difference between an evacuation alert and an evacuation order?",
    )

    async def run() -> None:
        runtime = load_runtime(
            FireLensConfig.from_env(Path(__file__).resolve().parents[1]),
            provider=FakeProvider(dimensions=1536),
        )
        try:
            for question in questions:
                execution = await runtime.service.execute_ask(QueryRequest(question=question))
                packet = execution.search.evidence_packet
                assert packet is not None, question
                chunk_ids = {
                    chunk_id for item in packet.items for chunk_id in item.primary_chunk_ids
                }
                assert "preparedbc_wildfire_guide:page:10:chunk:4" in chunk_ids, question
                assert "preparedbc_wildfire_guide:page:11:chunk:2" in chunk_ids, question
                assert execution.response.response_mode == ResponseMode.GROUNDED, question
                assert _typed_ids(execution.response) == {
                    "TC-EVAC-ALERT-001",
                    "TC-EVAC-ORDER-001",
                }, question
        finally:
            await runtime.aclose()

    asyncio.run(run())


def test_quote_only_rejects_unofficial_private_blog_source() -> None:
    quote = "Avoid driving through areas of dense smoke."
    packet = EvidencePacket(
        question="What should people do in dense smoke?",
        corpus_version="unofficial-quote.v1",
        items=[
            EvidenceSpan(
                evidence_id="E1",
                primary_chunk_ids=["private-blog:chunk:1"],
                chunk_ids=["private-blog:chunk:1"],
                primary_text=quote,
                context_text=quote,
                source_id="private-blog",
                title="Unknown private blog",
                publisher="Unknown private blog",
                canonical_url="https://example.com/wildfire-tips",
                page_number=1,
                section_title=None,
                locator="page:1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256="a" * 64,
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(quote_id="E1Q1", evidence_id="E1", text=quote)
        ],
    )

    response = compile_high_risk_answer(packet.question, packet, trace_id="unofficial-quote")

    assert response.claims == []
    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert not any(
        getattr(card, "support_state", None) == "official_quote_only"
        for card in (response.proof_cards or [])
    )


def test_quote_only_rejects_fake_gov_hash_that_is_not_an_admitted_chunk() -> None:
    quote = _ADMITTED_GRAB_AND_GO_LIST
    packet = EvidencePacket(
        question="What basic items should I put in a wildfire grab-and-go bag?",
        corpus_version="fake-gov-hash.v1",
        items=[
            EvidenceSpan(
                evidence_id="E1",
                primary_chunk_ids=["forged-gov:chunk:1"],
                chunk_ids=["forged-gov:chunk:1"],
                primary_text=quote,
                context_text=quote,
                source_id="forged-gov",
                title="Forged official page",
                publisher="Province of British Columbia",
                canonical_url=_ADMITTED_PREPAREDBC_PDF,
                page_number=1,
                section_title=None,
                locator="page:1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256="ab" * 32,
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(quote_id="E1Q1", evidence_id="E1", text=quote)
        ],
    )
    forged = packet.items[0]

    assert not admitted_official_quote_source(forged, quote)

    response = compile_high_risk_answer(packet.question, packet, trace_id="fake-gov-hash")

    assert response.claims == []
    assert response.response_mode == ResponseMode.SCOPE_REDIRECT
    assert not any(
        getattr(card, "support_state", None) == "official_quote_only"
        for card in (response.proof_cards or [])
    )
    assert not any(
        claim.publication is not None and claim.publication.kind.value == "official_quote_only"
        for claim in response.claims
    )
