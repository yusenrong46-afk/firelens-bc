from __future__ import annotations

from datetime import UTC, datetime

from firelens.claim_trust import GROUNDED_PUBLIC_WORDING, corpus_claim_trust
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidenceStatus,
    Freshness,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    ResponseMode,
    ResponseStatus,
    ValidationReport,
)

_VALIDATION = ValidationReport(
    accepted=True,
    citation_ids_valid=True,
    quotes_exact=True,
    claim_support_valid=True,
    policy_valid=True,
    errors=[],
)


def _grounded() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-proof",
        response_mode=ResponseMode.GROUNDED,
        answer="Keep water and food in a grab-and-go bag.",
        claims=[
            PublicClaim(
                claim_id="C1",
                text="Keep water and food in a grab-and-go bag.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[ClaimSupport(evidence_id="E1", quote="Food & water")],
                trust=corpus_claim_trust(
                    authority="PreparedBC",
                    review_provenance="human_verified_repair",
                ),
            )
        ],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Wildfire Preparedness Guide",
                publisher="PreparedBC",
                canonical_url="https://example.test/guide.pdf",
                locator="PDF page 5",
                temporal_class="stable_guidance",
                review_provenance="human_verified_repair",
                primary_text="Grab-and-Go Bag: Food & water",
                context_text="Grab-and-Go Bag: Food & water and emergency supplies.",
            )
        ],
        limitations=["Stable guidance only."],
        validation=_VALIDATION,
    )


def test_grounded_response_carries_proof_cards_and_checklist() -> None:
    response = _grounded()
    assert response.status_banner is not None
    assert response.status_banner.headline == "Grounded in reviewed official sources"
    assert GROUNDED_PUBLIC_WORDING in response.status_banner.detail
    assert response.status_banner.freshness_label == "Stable reviewed guidance"
    assert response.supported_items == ["Keep water and food in a grab-and-go bag."]
    assert response.unknown_items == ["Stable guidance only."]
    card = response.proof_cards[0]
    assert card.support_state == "supported"
    assert card.support_label == "Supported by an exact reviewed quotation"
    assert card.exact_passage == "Food & water"
    assert card.authority == "PreparedBC"
    assert card.source_revision == "PDF page 5"
    assert card.review_state == "Human-verified source transcription"
    assert card.critical_fields_checked == "Critical fields checked and preserved"
    assert str(card.official_url) == "https://example.test/guide.pdf"


def test_stale_live_banner_escalates_to_official_map() -> None:
    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-live-proof",
        response_mode=ResponseMode.LIVE,
        answer="Test Fire is Out of Control.",
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
        unavailable_layers=[LiveResultKind.EVACUATION],
        limitations=[
            "A live refresh failed; some official records shown are cached and may be outdated."
        ],
    )
    assert response.status_banner is not None
    assert response.status_banner.headline == "Official cached records"
    assert "Stale" in response.status_banner.freshness_label
    assert "evacuation" in response.status_banner.availability_label
    assert "not an all-clear" in response.status_banner.availability_label.lower()
    assert response.status_banner.official_escalation_title == "Open BCWS map"
    assert response.supported_items == ["Test Fire (incident)"]
    assert response.proof_cards[0].support_state == "live_record"
    assert response.proof_cards[0].support_label == "Official live record as published"
    assert response.status_banner.retrieval_completed_at == timestamp
    assert response.status_banner.source_updated_at == timestamp
