from __future__ import annotations

from datetime import UTC, datetime

import pytest

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
from firelens.publication_contracts import PublicationAuthority, PublicationKind

_VALIDATION = ValidationReport(
    accepted=True,
    citation_ids_valid=True,
    quotes_exact=True,
    claim_support_valid=True,
    policy_valid=True,
    errors=[],
)
_REJECTED_VALIDATION = ValidationReport(
    accepted=False,
    schema_valid=False,
    citation_ids_valid=False,
    quotes_exact=False,
    claim_support_valid=False,
    policy_valid=False,
    errors=["forced validation failure"],
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


def _published_claim(
    *, claim_id: str, evidence_id: str, text: str, quote: str, kind: PublicationKind
) -> PublicClaim:
    publication = PublicationAuthority(
        kind=kind,
        typed_claim_id="TC-QUOTE" if kind == PublicationKind.STRUCTURED_REVIEWED else None,
        review_status=(
            "approved" if kind == PublicationKind.STRUCTURED_REVIEWED else "extraction_only"
        ),
        source_revision_sha256=(
            "a" * 64 if kind == PublicationKind.STRUCTURED_REVIEWED else None
        ),
        renderer_id="firelens.test_renderer.v1",
        support_provenance="exact_official_quote",
    )
    return PublicClaim(
        claim_id=claim_id,
        text=text,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id=evidence_id, quote=quote)],
        trust=corpus_claim_trust(authority="PreparedBC", review_provenance="native_text"),
        publication=publication,
    )


def _published_evidence(evidence_id: str, quote: str) -> PublicEvidence:
    return PublicEvidence(
        evidence_id=evidence_id,
        title="Official emergency guidance",
        publisher="PreparedBC",
        canonical_url=f"https://example.test/{evidence_id.lower()}",
        locator="Emergency guidance",
        temporal_class="stable_guidance",
        review_provenance="native_text",
        primary_text=quote,
        context_text=quote,
    )


def test_quote_only_publication_controls_banner_and_proof_wording() -> None:
    quote = "Follow the directions of local authorities during an evacuation."
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-quote-only",
        response_mode=ResponseMode.PARTIAL,
        answer=quote,
        claims=[
            _published_claim(
                claim_id="C1",
                evidence_id="E1",
                text=quote,
                quote=quote,
                kind=PublicationKind.OFFICIAL_QUOTE_ONLY,
            )
        ],
        evidence=[_published_evidence("E1", quote)],
        validation=_VALIDATION,
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Official wording from a source"
    assert response.status_banner.detail == (
        "FireLens is showing an exact source quotation. It has not been approved "
        "as a structured FireLens claim."
    )
    assert response.status_banner.freshness_label == "Stable source wording"
    assert response.supported_items == []
    card = response.proof_cards[0]
    assert card.support_state == "official_quote_only"
    assert card.support_label == "Exact source wording — not a structured FireLens claim"
    assert card.review_state == "Source extraction only; no structured-claim review"
    assert card.freshness == "Stable source wording"


def test_reviewed_and_quote_only_publications_use_mixed_banner() -> None:
    reviewed = "Keep an emergency kit ready."
    quote = "Follow the directions of local authorities during an evacuation."
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-mixed-publication",
        response_mode=ResponseMode.PARTIAL,
        answer=f"{reviewed} {quote}",
        claims=[
            _published_claim(
                claim_id="C1",
                evidence_id="E1",
                text=reviewed,
                quote=reviewed,
                kind=PublicationKind.STRUCTURED_REVIEWED,
            ),
            _published_claim(
                claim_id="C2",
                evidence_id="E2",
                text=quote,
                quote=quote,
                kind=PublicationKind.OFFICIAL_QUOTE_ONLY,
            ),
        ],
        evidence=[
            _published_evidence("E1", reviewed),
            _published_evidence("E2", quote),
        ],
        validation=_VALIDATION,
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Reviewed claims plus source wording"
    assert response.status_banner.detail == (
        "Reviewed structured claims and extraction-only source wording are labelled separately."
    )
    assert response.status_banner.freshness_label == "Stable guidance and source wording"


@pytest.mark.parametrize(
    "kind",
    [PublicationKind.STRUCTURED_REVIEWED, PublicationKind.OFFICIAL_QUOTE_ONLY],
)
def test_rejected_publication_is_not_strengthened_by_additive_proof_fields(
    kind: PublicationKind,
) -> None:
    text = "Follow the directions of local authorities during an evacuation."
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=f"trace-rejected-{kind.value}",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=[
            _published_claim(claim_id="C1", evidence_id="E1", text=text, quote=text, kind=kind)
        ],
        evidence=[_published_evidence("E1", text)],
        validation=_REJECTED_VALIDATION,
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Support not established"
    assert response.status_banner.freshness_label == "Freshness not established"
    assert response.supported_items == []
    assert response.proof_cards[0].support_state == "unknown"
    assert response.proof_cards[0].support_label == "Not established from FireLens sources"


def test_failed_critical_field_preservation_is_not_listed_as_supported() -> None:
    text = "Keep an emergency kit ready."
    claim = _published_claim(
        claim_id="C1",
        evidence_id="E1",
        text=text,
        quote=text,
        kind=PublicationKind.STRUCTURED_REVIEWED,
    )
    assert claim.trust is not None
    claim = claim.model_copy(
        update={
            "trust": claim.trust.model_copy(update={"critical_field_preservation": "failed"})
        }
    )
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-critical-field-failed",
        response_mode=ResponseMode.GROUNDED,
        answer=text,
        claims=[claim],
        evidence=[_published_evidence("E1", text)],
        validation=_VALIDATION,
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Support not established"
    assert response.supported_items == []
    assert response.proof_cards[0].support_state == "unknown"
