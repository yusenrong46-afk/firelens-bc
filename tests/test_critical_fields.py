from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rag_helpers import make_chunk, write_test_corpus

from firelens.agent.packet import AgentPacket
from firelens.agent.rails import output_rail_errors
from firelens.answering.context import build_evidence_packet
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.semantic_invariants import preservation_errors
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
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
    ResponseMode,
    ResponseStatus,
    ValidationReport,
)
from firelens.publication.compiler import explanation_authority
from firelens.retrieval.vector import retrieval_hit_from_chunk

FABLE_MUTATIONS = [
    (
        "leave_to_stay",
        "An evacuation order means you must leave the area immediately.",
        "An evacuation order means you may stay in the area.",
    ),
    (
        "immediate_to_delayed",
        "An evacuation order means you must leave the area immediately.",
        "An evacuation order means you can leave the area later today.",
    ),
    (
        "required_to_optional",
        "You must register at the reception centre after evacuating.",
        "You may register at the reception centre if you want.",
    ),
    (
        "unit_swap",
        "Maintain a non-combustible area extending 1.5 metres around the home.",
        "Maintain a non-combustible area extending 1.5 feet around the home.",
    ),
    (
        "comparator_flip",
        "Keep at least 10 metres between woodpiles and the house.",
        "Keep at most 10 metres between woodpiles and the house.",
    ),
    (
        "authority_swap",
        "BC Wildfire Service publishes the provincial fire danger rating.",
        "Environment Canada publishes the provincial fire danger rating.",
    ),
    (
        "exception_reversal",
        "Sprinklers help unless water pressure is too low.",
        "Sprinklers help especially when water pressure is too low.",
    ),
    (
        "stale_as_current",
        "The 2017 plan recommended these routes.",
        "The current plan recommends these routes.",
    ),
    (
        "overlap_opposite",
        "An evacuation alert does not mean you must leave immediately.",
        "An evacuation alert does mean you must leave immediately.",
    ),
]

FAITHFUL_CASES = [
    (
        "metre_alias",
        "Maintain a non-combustible area extending 1.5 metres around the home.",
        "Maintain a non-combustible area extending 1.5 meters around the home.",
    ),
    (
        "feet_conversion",
        "Maintain a non-combustible area extending 1.5 metres around the home.",
        "Maintain a non-combustible area extending approximately 5 feet around the home.",
    ),
    (
        "at_least_alias",
        "Keep at least 10 metres between woodpiles and the house.",
        "Keep no less than 10 metres between woodpiles and the house.",
    ),
    (
        "bc_alias",
        "This guidance applies in British Columbia.",
        "This guidance applies in BC.",
    ),
    (
        "optional_restatement",
        "You may register at the reception centre if you want.",
        "Registration at the reception centre is optional.",
    ),
    (
        "kit_reorder",
        "Include water, medication, and copies of important documents.",
        "Medication, water, and copies of important documents should be included.",
    ),
]


def test_checker_rejects_fable_nearby_mutations() -> None:
    for name, quote, claim in FABLE_MUTATIONS:
        assert preservation_errors(claim, [quote]), name


def test_checker_accepts_faithful_paraphrases_and_conversions() -> None:
    for name, quote, claim in FAITHFUL_CASES:
        assert preservation_errors(claim, [quote]) == [], name


def test_partial_salvage_cannot_keep_a_unit_swap(tmp_path: Path) -> None:
    quote = "Maintain a non-combustible area extending 1.5 metres around the home."
    chunk = make_chunk("zone", quote)
    config = write_test_corpus(tmp_path, [chunk])
    packet = build_evidence_packet(
        "How large is the non-combustible zone?",
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="test-corpus.v1",
        config=config,
    )
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(text=quote, evidence_quote_ids=[quote_id]),
            DraftProposalClaim(
                text="Maintain a non-combustible area extending 1.5 feet around the home.",
                evidence_quote_ids=[quote_id],
            ),
        ],
        limitations=packet.limitations,
    )

    assert validate_draft(draft, packet).accepted is False
    salvaged = salvage_valid_grounded_claims(draft, packet)
    assert salvaged is not None
    kept, report = salvaged
    assert report.accepted is True
    assert [claim.text for claim in kept.claims] == [quote]


def test_mutated_claim_alone_cannot_be_published(tmp_path: Path) -> None:
    quote = "Keep at least 10 metres between woodpiles and the house."
    chunk = make_chunk("buffer", quote)
    config = write_test_corpus(tmp_path, [chunk])
    packet = build_evidence_packet(
        "How far should woodpiles be?",
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="test-corpus.v1",
        config=config,
    )
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(
                text="Keep at most 10 metres between woodpiles and the house.",
                evidence_quote_ids=[quote_id],
            )
        ],
        limitations=packet.limitations,
    )
    assert validate_draft(draft, packet).accepted is False
    assert salvage_valid_grounded_claims(draft, packet) is None


def test_stale_proof_card_and_banner_do_not_claim_current() -> None:
    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-stale-current",
        response_mode=ResponseMode.LIVE,
        answer="Cached official information (refresh failed): Test Fire is Out of Control.",
        live_results=[
            LiveResult(
                result_id="incident:7",
                kind=LiveResultKind.INCIDENT,
                authority="BC Wildfire Service",
                source_url="https://example.test/incidents/7",
                source_updated_at=timestamp,
                retrieved_at=timestamp,
                freshness=Freshness.STALE,
                status="Out of Control",
                name="Test Fire",
                geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
            )
        ],
        aggregate_freshness="stale",
        limitations=["A live refresh failed; some official records shown are cached."],
    )
    assert response.status_banner is not None
    headline = response.status_banner.headline.casefold()
    for banned in ("current", "latest", "live", "up to date"):
        assert banned not in headline
    assert "current" not in response.status_banner.freshness_label.casefold()
    card = response.proof_cards[0]
    assert "current" not in card.freshness.casefold()
    assert "latest" not in card.freshness.casefold()


def test_output_rail_blocks_current_language_on_stale_records() -> None:
    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    packet = AgentPacket()
    packet.live_results = [
        LiveResult(
            result_id="incident:7",
            kind=LiveResultKind.INCIDENT,
            authority="BC Wildfire Service",
            source_url="https://example.test/incidents/7",
            source_updated_at=timestamp,
            retrieved_at=timestamp,
            freshness=Freshness.STALE,
            status="Out of Control",
            name="Test Fire",
            geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
        )
    ]
    errors = output_rail_errors("These are the current latest live conditions.", packet)
    assert "stale_described_as_current" in errors


def test_live_missing_composition_does_not_call_static_current() -> None:
    static = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-mixed-static",
        response_mode=ResponseMode.GROUNDED,
        answer="Include water, medication, and copies of important documents.",
        claims=[
            PublicClaim(
                claim_id="C1",
                text="Include water, medication, and copies of important documents.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[ClaimSupport(evidence_id="E1", quote="Include water")],
                publication=explanation_authority(),
            )
        ],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Preparedness Guide",
                publisher="PreparedBC",
                canonical_url="https://example.test/guide.pdf",
                locator="PDF page 1",
                temporal_class="stable_guidance",
                review_provenance="native_text",
                primary_text="Include water, medication, and copies of important documents.",
                context_text="Include water, medication, and copies of important documents.",
            )
        ],
        limitations=["Stable guidance only."],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
            errors=[],
        ),
    )
    merged = supported_static_when_live_missing(
        static,
        "Official live sources were unavailable.",
        limitations=["Official live sources were unavailable."],
    )
    assert merged is not None
    lowered = (merged.answer or "").casefold()
    assert "current official information" not in lowered
