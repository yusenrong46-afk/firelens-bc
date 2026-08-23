from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rag_helpers import make_chunk, write_test_corpus

from firelens.agent.fallback_brain import fallback_write
from firelens.agent.packet import AgentPacket, live_record_fact
from firelens.agent.rails import output_rail_errors
from firelens.answering.context import build_evidence_packet
from firelens.answering.grounded import GroundedAnswerEngine
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.claim_trust import corpus_claim_trust
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    DraftProposalClaim,
    EvidenceStatus,
    Freshness,
    GroundedDraft,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    ValidationReport,
)
from firelens.proof_presentation import build_proof_cards
from firelens.providers.fake import FakeProvider
from firelens.retrieval.vector import retrieval_hit_from_chunk

SMOKE_QUOTE = "Avoid driving through areas of dense smoke."
SMOKE_MUTATION = "Drive through areas of dense smoke."


def _packet_for(tmp_path: Path, quote: str):
    chunk = make_chunk("smoke-span", quote)
    config = write_test_corpus(tmp_path, [chunk])
    return build_evidence_packet(
        "What should people do in dense smoke?",
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="round3-path.v1",
        config=config,
    )


def test_salvage_cannot_keep_avoid_to_perform(tmp_path: Path) -> None:
    packet = _packet_for(tmp_path, SMOKE_QUOTE)
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(text=SMOKE_QUOTE, evidence_quote_ids=[quote_id]),
            DraftProposalClaim(text=SMOKE_MUTATION, evidence_quote_ids=[quote_id]),
        ],
        limitations=packet.limitations,
    )
    assert validate_draft(draft, packet).accepted is False
    salvaged = salvage_valid_grounded_claims(draft, packet)
    assert salvaged is not None
    kept, report = salvaged
    assert report.accepted is True
    assert SMOKE_MUTATION not in [claim.text for claim in kept.claims]


def test_grounded_engine_does_not_publish_smoke_mutation(tmp_path: Path) -> None:
    packet = _packet_for(tmp_path, SMOKE_QUOTE)
    quote_id = packet.quote_candidates[0].quote_id

    class MutatingProvider(FakeProvider):
        async def generate_grounded(self, messages, *, output_schema):  # type: ignore[no-untyped-def]
            result = await super().generate_grounded(messages, output_schema=output_schema)
            draft = GroundedDraft(
                answer_type="grounded",
                claims=[DraftProposalClaim(text=SMOKE_MUTATION, evidence_quote_ids=[quote_id])],
                limitations=packet.limitations,
            )
            return result.model_copy(update={"draft": draft})

    engine = GroundedAnswerEngine(MutatingProvider(dimensions=8))
    response = asyncio.run(
        engine.answer("What about smoke?", packet, trace_id="trace-smoke")
    ).response
    text = (response.answer or "").casefold()
    assert "drive through areas of dense smoke" not in text
    assert response.response_mode != ResponseMode.GROUNDED or SMOKE_MUTATION not in [
        claim.text for claim in response.claims
    ]


def test_output_rail_rejects_rewritten_avoid_to_perform() -> None:
    packet = AgentPacket()
    packet.static_response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-rail",
        response_mode=ResponseMode.GROUNDED,
        answer=SMOKE_QUOTE,
        claims=[
            PublicClaim(
                claim_id="C1",
                text=SMOKE_QUOTE,
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[ClaimSupport(evidence_id="E1", quote=SMOKE_QUOTE)],
            )
        ],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Smoke guidance",
                publisher="PreparedBC",
                canonical_url="https://example.test/smoke.pdf",
                locator="PDF page 1",
                temporal_class="stable_guidance",
                review_provenance="native_text",
                primary_text=SMOKE_QUOTE,
                context_text=SMOKE_QUOTE,
            )
        ],
        limitations=["Grounded in reviewed sources."],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
            errors=[],
        ),
    )
    errors = output_rail_errors(SMOKE_MUTATION, packet)
    assert errors


def test_failed_critical_fields_cannot_appear_supported_on_proof_cards() -> None:
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-proof",
        response_mode=ResponseMode.GROUNDED,
        answer=SMOKE_MUTATION,
        claims=[
            PublicClaim(
                claim_id="C1",
                text=SMOKE_MUTATION,
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[ClaimSupport(evidence_id="E1", quote=SMOKE_QUOTE)],
                trust=corpus_claim_trust(
                    authority="PreparedBC",
                    review_provenance="native_text",
                    critical_fields_preserved=False,
                ),
            )
        ],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Smoke guidance",
                publisher="PreparedBC",
                canonical_url="https://example.test/smoke.pdf",
                locator="PDF page 1",
                temporal_class="stable_guidance",
                review_provenance="native_text",
                primary_text=SMOKE_QUOTE,
                context_text=SMOKE_QUOTE,
            )
        ],
        limitations=["Critical-field check failed."],
        validation=ValidationReport(
            accepted=False,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=False,
            policy_valid=True,
            errors=["reverses an avoidance instruction"],
        ),
    )
    cards = build_proof_cards(response)
    assert cards
    assert cards[0].support_state != "supported"
    assert "drive through" not in cards[0].support_label.casefold()


def test_mixed_composition_cannot_promote_unvalidated_mutation() -> None:
    static = AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id="trace-mixed",
        response_mode=ResponseMode.ABSTENTION,
        answer="FireLens could not validate that claim.",
        claims=[],
        limitations=["Draft validation failed."],
        validation=ValidationReport(
            accepted=False,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=False,
            policy_valid=True,
            errors=["reverses an avoidance instruction"],
        ),
    )
    merged = supported_static_when_live_missing(
        static,
        "Official live sources were unavailable.",
        limitations=["Official live sources were unavailable."],
    )
    assert merged is None


def test_live_record_fact_keeps_retrieval_and_source_times_distinct() -> None:
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
    )
    fact = live_record_fact(record)
    assert fact["source_updated_at"] == updated.isoformat()
    assert fact["retrieved_at"] == retrieved.isoformat()
    assert fact["source_updated_at"] != fact["retrieved_at"]
    assert fact["freshness"] == "stale"


def test_fallback_write_does_not_call_stale_records_current() -> None:
    retrieved = datetime(2026, 8, 17, 14, 5, tzinfo=UTC)
    packet = AgentPacket()
    packet.live_results = [
        LiveResult(
            result_id="incident:9",
            kind=LiveResultKind.INCIDENT,
            authority="BC Wildfire Service",
            source_url="https://example.test/incidents/9",
            source_updated_at=retrieved,
            retrieved_at=retrieved,
            freshness=Freshness.STALE,
            status="Out of Control",
            name="Exam Fire",
            geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
        )
    ]
    answer = fallback_write(QueryRequest(question="What fires are near Kamloops?"), packet)
    lowered = answer.casefold()
    assert "current official information" not in lowered
    assert "latest" not in lowered
