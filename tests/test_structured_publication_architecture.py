"""Architectural tests for mandatory structured publication (ADR 0014).

These tests encode user-visible and contract-level properties. They must fail
on the examined Round-3 candidate, where typed inventory is optional
post-validation canonicalization.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from rag_helpers import make_chunk, write_test_corpus

from firelens.agent.chat import ChatTurn
from firelens.agent.compose import compose_response
from firelens.agent.loop import _rewrite
from firelens.agent.packet import AgentPacket
from firelens.answering.context import build_evidence_packet, decide_support
from firelens.answering.generate import draft_schema
from firelens.answering.grounded import GroundedAnswerEngine, compile_without_generation
from firelens.answering.service import _with_support_limitations
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    AuthorityClass,
    ClaimSupport,
    DraftProposalClaim,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    EvidenceStatus,
    Freshness,
    GroundedDraft,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    QueryPlan,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    RetrievalBundle,
    RetrievalRequest,
    SupportStatus,
    TemporalClass,
)
from firelens.live_contracts import bind_distance_derivation
from firelens.proof_presentation import build_proof_cards
from firelens.providers.fake import FakeProvider
from firelens.publication.records import get_versioned
from firelens.retrieval.vector import retrieval_hit_from_chunk
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "src/firelens/publication/compiler.py"
SUPPORTED_KINDS = {"structured_reviewed", "official_live_typed"}
SAFE_UNCOVERED = {"official_quote_only", "partial", "official_handoff"}
ORDER_QUOTE = "Evacuation Order This means you are at risk and must leave IMMEDIATELY."
ARBITRARY_GENERATED = (
    "Residents may remain in place if they personally judge the risk acceptable."
)
UNCOVERED_HIGH_RISK = "Avoid driving through areas of dense smoke."


def _load(name: str):
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        pytest.fail(f"missing structured-publication module {name}: {exc}")


def _packet(tmp_path: Path, quote: str, question: str = "What does the official guidance say?"):
    chunk = make_chunk("structured-span", quote)
    config = write_test_corpus(tmp_path, [chunk])
    return build_evidence_packet(
        question,
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="structured-pub.v1",
        config=config,
    )


def _publication_kind(claim: PublicClaim) -> str:
    publication = getattr(claim, "publication", None)
    if publication is None:
        return ""
    kind = getattr(publication, "kind", publication)
    return kind.value if hasattr(kind, "value") else str(kind)


def _is_structured_supported(claim: PublicClaim) -> bool:
    kind = _publication_kind(claim)
    if kind in SUPPORTED_KINDS:
        return True
    if kind in {
        "official_quote_only",
        "source_linked_explanation",
        "general_background",
        "unsupported",
    }:
        return False
    return claim.evidence_status == EvidenceStatus.VERIFIED_CORPUS


def test_a_constructor_requires_publication_authority() -> None:
    contracts = _load("firelens.publication_contracts")
    with pytest.raises((ValidationError, TypeError, ValueError)):
        contracts.StructuredReviewedClaimBlock(
            public_claim_id="C1",
            text="An evacuation order means you must leave immediately.",
        )
    with pytest.raises((ValidationError, TypeError, ValueError)):
        PublicClaim(
            claim_id="C1",
            text="An evacuation order means you must leave immediately.",
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[ClaimSupport(evidence_id="E1", quote=ORDER_QUOTE)],
            publication=contracts.PublicationAuthority(
                kind=contracts.PublicationKind.STRUCTURED_REVIEWED,
            ),
        )


def test_b_high_risk_plan_has_no_factual_text_field() -> None:
    contracts = _load("firelens.publication_contracts")
    fields = set(contracts.HighRiskAnswerPlan.model_fields)
    forbidden = {
        "claim_text",
        "text",
        "answer",
        "claims",
        "claim",
        "factual_text",
        "canonical_text",
    }
    assert not fields.intersection(forbidden)
    schema = contracts.HighRiskAnswerPlan.model_json_schema()
    claim_props = schema.get("properties", {})
    assert "text" not in claim_props
    grounded = draft_schema()
    # High-risk answering must not use the free-form grounded claim schema.
    assert "DraftProposalClaim" not in str(contracts.HighRiskAnswerPlan.model_json_schema())
    del grounded


def test_c_free_generated_claim_cannot_become_tier_ab_supported(tmp_path: Path) -> None:
    generated = "Do not drive through areas of dense smoke."
    packet = _packet(tmp_path, UNCOVERED_HIGH_RISK, "What should people do in dense smoke?")
    quote_id = packet.quote_candidates[0].quote_id

    class GeneratedProvider(FakeProvider):
        async def generate_grounded(self, messages, *, output_schema):  # type: ignore[no-untyped-def]
            result = await super().generate_grounded(messages, output_schema=output_schema)
            draft = GroundedDraft(
                answer_type="grounded",
                claims=[
                    DraftProposalClaim(
                        text=generated,
                        evidence_quote_ids=[quote_id],
                    )
                ],
                limitations=packet.limitations,
            )
            return result.model_copy(update={"draft": draft})

    response = asyncio.run(
        GroundedAnswerEngine(GeneratedProvider(dimensions=8)).answer(
            "What should people do in dense smoke?",
            packet,
            trace_id="trace-free-gen",
        )
    ).response
    assert not any(_is_structured_supported(claim) for claim in response.claims)
    assert generated not in (response.answer or "")
    for card in build_proof_cards(response):
        assert card.support_state != "supported"
        assert generated not in card.claim_text


def test_d_uncovered_high_risk_is_quote_only_partial_or_handoff(tmp_path: Path) -> None:
    packet = _packet(tmp_path, UNCOVERED_HIGH_RISK, "What should people do in dense smoke?")
    response = asyncio.run(
        GroundedAnswerEngine(FakeProvider(dimensions=8)).answer(
            "What should people do in dense smoke?",
            packet,
            trace_id="trace-uncovered",
        )
    ).response
    kinds = {_publication_kind(claim) for claim in response.claims}
    mode = response.response_mode
    reason = getattr(response.reason_code, "value", response.reason_code)
    uncovered_ok = kinds <= SAFE_UNCOVERED | {""} and (
        "official_quote_only" in kinds
        or mode in {ResponseMode.PARTIAL, ResponseMode.ABSTENTION, ResponseMode.SCOPE_REDIRECT}
        or reason == "high_risk_claim_not_structured"
    )
    assert uncovered_ok
    assert not any(_is_structured_supported(claim) for claim in response.claims)
    for card in build_proof_cards(response):
        assert card.support_state != "supported"


def test_h04_forced_partial_rebuilds_authority_history_through_contract_validation() -> None:
    """Partial support must not retain a grounded-only history label.

    H04 has reviewed alert/order definitions but no support for the requested
    North Bend tag colour.  The compiler can safely publish the two reviewed
    claims, while the orchestration layer must force the response to partial.
    """

    question = (
        "Harder multi-aspect: Explain evacuation alert vs order AND the exact "
        "North Bend tag colour."
    )
    items: list[EvidenceSpan] = []
    candidates: list[EvidenceQuoteCandidate] = []
    for index, claim_id in enumerate(("TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"), 1):
        record = get_versioned(claim_id)
        assert record.canonical_url is not None
        evidence_id = f"E{index}"
        items.append(
            EvidenceSpan(
                evidence_id=evidence_id,
                primary_chunk_ids=list(record.source_span_ids),
                chunk_ids=list(record.source_span_ids),
                primary_text=record.source_span_text,
                context_text=record.source_span_text,
                source_id=f"h04-source-{index}",
                title="Reviewed PreparedBC guidance",
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
    packet = EvidencePacket(
        question=question,
        corpus_version="h04-force-partial.v1",
        items=items,
        quote_candidates=candidates,
        limitations=["Not supported by selected evidence: exact North Bend tag colour."],
    )
    aspects = ("evacuation alert meaning", "evacuation order meaning")

    baseline = compile_without_generation(
        question,
        packet,
        trace_id="h04-baseline",
        supported_aspects=aspects,
    )
    assert baseline is not None
    assert baseline.response_mode == ResponseMode.GROUNDED

    compiled = compile_without_generation(
        question,
        packet,
        trace_id="h04-compiled",
        supported_aspects=aspects,
        force_partial=True,
    )
    generated = asyncio.run(
        GroundedAnswerEngine(FakeProvider(dimensions=8)).answer(
            question,
            packet,
            trace_id="h04-generated",
            supported_aspects=aspects,
            force_partial=True,
        )
    ).response
    for response in (compiled, generated):
        assert response is not None
        assert response.response_mode == ResponseMode.PARTIAL
        assert response.validation is not None and response.validation.accepted
        assert all(
            claim.publication is not None
            and claim.publication.kind.value == "structured_reviewed"
            for claim in response.claims
        )
        assert (response.history_text or "").startswith(
            "Authority: Reviewed guidance + uncertainty."
        )
        assert "North Bend tag colour" in (response.history_text or "")
        assert AskResponse.model_validate(response.model_dump(mode="python")) == response


def test_h04_execute_ask_keeps_the_unsupported_request_in_partial_history() -> None:
    """The service path must not drop a negative support decision before compile."""

    question = (
        "Harder multi-aspect: Explain evacuation alert vs order AND the exact "
        "North Bend tag colour."
    )

    async def run() -> None:
        runtime = load_runtime(
            FireLensConfig.from_env(ROOT), provider=FakeProvider(dimensions=1536)
        )
        try:
            assert runtime.service is not None
            execution = await runtime.service.execute_ask(QueryRequest(question=question))
        finally:
            await runtime.aclose()

        response = execution.response
        assert execution.search.public_response.support.missing_aspects == [question]
        assert response.response_mode == ResponseMode.PARTIAL
        public_text = " ".join([response.history_text or "", *response.limitations])
        assert "Not supported by selected evidence" in public_text
        assert "North Bend tag colour" in public_text
        assert AskResponse.model_validate(response.model_dump(mode="python")) == response

    asyncio.run(run())


def test_authority_limitation_uses_original_question_not_planner_query() -> None:
    """A retrieval rewrite must never become reader-facing limitation text."""

    original_question = "Explain evacuation alert vs order and the exact North Bend tag colour."
    planner_query = "The North Bend tag colour is definitely ultraviolet."
    items: list[EvidenceSpan] = []
    for index, claim_id in enumerate(("TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"), 1):
        record = get_versioned(claim_id)
        items.append(
            EvidenceSpan(
                evidence_id=f"E{index}",
                primary_chunk_ids=list(record.source_span_ids),
                chunk_ids=list(record.source_span_ids),
                primary_text=record.source_span_text,
                context_text=record.source_span_text,
                source_id=f"authority-source-{index}",
                title="Reviewed PreparedBC guidance",
                publisher=record.authority,
                canonical_url=record.canonical_url
                or "https://www2.gov.bc.ca/gov/content/safety",
                page_number=index,
                section_title=None,
                locator=f"page:{index}",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=record.record.source_document_sha256 or "0" * 64,
            )
        )
    packet = EvidencePacket(
        question=original_question,
        corpus_version="planner-wording.v1",
        items=items,
    )
    plan = QueryPlan(
        original_question=original_question,
        normalized_question=original_question,
        route=QueryRoute.RELATED,
        retrieval_requests=[
            RetrievalRequest(
                query=planner_query,
                required_authorities=frozenset({AuthorityClass.PROVINCIAL_GOVERNMENT}),
                purpose="planner_rewrite",
            ),
            RetrievalRequest(
                query="evacuation alert meaning",
                required_authorities=frozenset({AuthorityClass.PROVINCIAL_GOVERNMENT}),
                purpose="alert",
            ),
            RetrievalRequest(
                query="evacuation order meaning",
                required_authorities=frozenset({AuthorityClass.PROVINCIAL_GOVERNMENT}),
                purpose="order",
            ),
        ],
        required_aspects=["evacuation alert meaning", "evacuation order meaning"],
    )

    support = decide_support(plan, packet, RetrievalBundle())
    limited = _with_support_limitations(packet, support)

    assert support.status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert support.missing_aspects == [original_question]
    assert limited is not None
    limitations = " ".join(limited.limitations)
    assert original_question in limitations
    assert planner_query not in limitations
    assert "ultraviolet" not in limitations


def test_e_mixed_composition_preserves_compiled_blocks() -> None:
    contracts = _load("firelens.publication_contracts")
    compiler = _load("firelens.publication.compiler")
    compiled = compiler.compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001",
        public_claim_id="C1",
    )
    packet = AgentPacket()
    packet.static_response = compiled.response
    packet.live_results = [
        LiveResult(
            result_id="incident:1",
            kind=LiveResultKind.INCIDENT,
            authority="BC Wildfire Service",
            source_url="https://example.test/incidents/1",
            source_updated_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
            retrieved_at=datetime(2026, 8, 17, 14, 5, tzinfo=UTC),
            freshness=Freshness.STALE,
            status="Out of Control",
            name="Exam Fire",
            geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
        )
    ]
    rewritten = (
        "Exam Fire is out of control. Residents may remain if they feel safe "
        "despite the evacuation order."
    )
    mixed = compose_response(
        QueryRequest(question="What is happening near the fire?"),
        packet,
        rewritten,
    )
    assert compiled.claim.text in (mixed.answer or "")
    assert "remain if they feel safe" not in (mixed.answer or "")
    assert all(
        _publication_kind(claim) == contracts.PublicationKind.STRUCTURED_REVIEWED.value
        or _publication_kind(claim) == "structured_reviewed"
        for claim in mixed.claims
        if claim.claim_id == compiled.claim.claim_id
    )


def test_f_rewrite_cannot_modify_compiled_tier_ab_text() -> None:
    compiler = _load("firelens.publication.compiler")
    compiled = compiler.compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001",
        public_claim_id="C1",
    )
    packet = AgentPacket()
    packet.static_response = compiled.response
    request = QueryRequest(question="What does an evacuation order mean?")

    class Rewriter(FakeProvider):
        async def chat_turn(self, messages, tools=None):  # type: ignore[no-untyped-def]
            del messages, tools
            return ChatTurn(content="An evacuation order is now only a suggestion.")

    rewritten = asyncio.run(
        _rewrite(
            Rewriter(dimensions=8),
            request,
            packet,
            compiled.claim.text,
            ["safety_or_medical_language"],
        )
    )
    assert compiled.claim.text in rewritten
    assert "only a suggestion" not in rewritten


def test_g_salvage_cannot_promote_untyped_high_risk(tmp_path: Path) -> None:
    packet = _packet(tmp_path, ORDER_QUOTE)
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(text=ORDER_QUOTE, evidence_quote_ids=[quote_id]),
            DraftProposalClaim(text=ARBITRARY_GENERATED, evidence_quote_ids=[quote_id]),
        ],
        limitations=packet.limitations,
    )
    salvaged = salvage_valid_grounded_claims(draft, packet)
    if salvaged is not None:
        kept, report = salvaged
        assert ARBITRARY_GENERATED not in [claim.text for claim in kept.claims]
        assert report.accepted is True
    response = asyncio.run(
        GroundedAnswerEngine(FakeProvider(dimensions=8)).answer(
            "What does an evacuation order mean?",
            packet,
            trace_id="trace-salvage",
        )
    ).response
    assert ARBITRARY_GENERATED not in [claim.text for claim in response.claims]
    assert not any(
        _is_structured_supported(claim) and not getattr(claim, "publication", None)
        for claim in response.claims
    )


def test_h_proof_card_shares_compiled_object() -> None:
    compiler = _load("firelens.publication.compiler")
    compiled = compiler.compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001",
        public_claim_id="C1",
    )
    cards = compiled.response.proof_cards or build_proof_cards(compiled.response)
    assert cards
    card = next(item for item in cards if item.claim_id == compiled.claim.claim_id)
    authority = compiled.claim.publication
    assert card.claim_text == compiled.claim.text
    assert card.support_state == "structured_reviewed" or card.support_state == "supported"
    assert authority is not None
    assert card.source_revision == authority.source_revision_sha256
    assert compiled.claim.claim_id in {card.claim_id, compiled.claim.claim_id}
    assert (
        authority.review_status in card.review_state
        or authority.review_status == "approved_static"
    )


def test_i_source_revision_or_span_hash_change_invalidates() -> None:
    compiler = _load("firelens.publication.compiler")
    records = _load("firelens.publication.records")
    compiled = compiler.compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001",
        public_claim_id="C1",
    )
    assert compiled.claim.publication is not None
    with pytest.raises((ValidationError, ValueError)):
        compiler.compile_structured_claim(
            typed_claim_id="TC-EVAC-ORDER-001",
            public_claim_id="C1",
            source_revision_sha256="0" * 64,
        )
    try:
        mutated = records.invalidate_source_binding(
            "TC-EVAC-ORDER-001",
            source_span_sha256="f" * 64,
        )
        assert mutated.available_for_structured_support is False
    finally:
        records.clear_authority_caches()


def test_j_compositional_laundering_cannot_support_one_unsafe_clause(tmp_path: Path) -> None:
    packet = _packet(tmp_path, ORDER_QUOTE)
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(
                text="An evacuation order means you are at risk and must leave immediately.",
                evidence_quote_ids=[quote_id],
            ),
            DraftProposalClaim(
                text="Close doors and windows on your way out.",
                evidence_quote_ids=[quote_id],
            ),
            DraftProposalClaim(text=ARBITRARY_GENERATED, evidence_quote_ids=[quote_id]),
        ],
        limitations=packet.limitations,
    )
    report = validate_draft(draft, packet)
    if report.accepted:
        pytest.fail("mixed safe+unsafe draft must not validate as one supported unit")
    salvaged = salvage_valid_grounded_claims(draft, packet)
    if salvaged is not None:
        assert ARBITRARY_GENERATED not in [claim.text for claim in salvaged[0].claims]


def test_k_live_typed_facts_are_rendered_from_records_not_model_prose() -> None:
    compiler = _load("firelens.publication.compiler")
    retrieved = datetime(2026, 8, 17, 14, 5, tzinfo=UTC)
    updated = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
    record = LiveResult(
        result_id="incident:9",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/incidents/9",
        source_updated_at=updated,
        retrieved_at=retrieved,
        freshness=Freshness.STALE,
        status="Out of Control",
        name="Exam Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
        distance_km=12.5,
        distance_basis="incident_point",
        distance_derivation=bind_distance_derivation(
            result_id="incident:9",
            distance_km=12.5,
            distance_basis="incident_point",
            calculated_at=retrieved,
            extra_input_ids=("place:49.89,-119.50",),
            input_freshness=Freshness.STALE,
        ),
    )
    block = compiler.compile_live_fact(record, public_claim_id="L1")
    assert _publication_kind(block.claim) in {"official_live_typed", "OFFICIAL_LIVE_TYPED"}
    text = block.claim.text
    assert "Out of Control" in text
    assert "12.5" in text or "12.5 km" in text.casefold()
    assert updated.date().isoformat() in text or "source updated" in text.casefold()
    assert "all-clear" not in text.casefold()
    assert block.claim.publication is not None
    assert block.claim.publication.typed_live_fact_id == "incident:9"
    assert block.card.derivation is not None
    assert block.card.derivation.validation_status.value == "valid"
    assert block.card.derivation.publication_state.value == "review"
    assert block.card.publication_state.value == "review"


def test_l_only_compiler_may_create_structured_reviewed_claims() -> None:
    assert COMPILER.is_file(), "structured publication compiler is missing"
    allowed = {COMPILER.resolve()}
    offenders: list[str] = []
    for path in (ROOT / "src/firelens").rglob("*.py"):
        if path.resolve() in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in {
                "StructuredReviewedClaimBlock",
                "compile_structured_claim",
                "compile_live_fact",
            }:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
            if name == "PublicClaim":
                for keyword in node.keywords:
                    if keyword.arg == "publication" and "STRUCTURED_REVIEWED" in ast.dump(
                        keyword.value
                    ):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}:PublicClaim.STRUCTURED_REVIEWED"
                        )
    assert not offenders, "only the compiler may construct STRUCTURED_REVIEWED:\n" + "\n".join(
        offenders
    )


def test_risk_may_only_rise() -> None:
    policy = _load("firelens.publication.risk")
    assert policy.effective_risk("A", "C") == "A"
    assert policy.effective_risk("B", "C") == "B"
    assert policy.effective_risk("C", "A") == "A"
    with pytest.raises((ValueError, TypeError)):
        policy.lower_risk("A", "C")
