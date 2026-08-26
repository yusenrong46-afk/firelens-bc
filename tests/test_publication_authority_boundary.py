"""Missing publication authority cannot render a privileged PublicClaim or ProofCard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import HttpUrl, ValidationError

from firelens.claim_trust import corpus_claim_trust
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidenceStatus,
    PublicClaim,
    PublicEvidence,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.proof_presentation import build_proof_cards
from firelens.publication.compiler import compile_structured_claim
from firelens.publication_contracts import PublicationAuthority, PublicationKind
from firelens.safety_profile import PublicationState, TruthClass

_PRIVILEGED = {"supported", "structured_reviewed", "official_live_typed"}
_ACCEPTED = ValidationReport(
    accepted=True,
    schema_valid=True,
    citation_ids_valid=True,
    quotes_exact=True,
    claim_support_valid=True,
    policy_valid=True,
)


def _claim_without_publication() -> SimpleNamespace:
    return SimpleNamespace(
        claim_id="C1",
        text="Keep water and food in a grab-and-go bag.",
        evidence_status="verified_corpus",
        supports=[ClaimSupport(evidence_id="E1", quote="Food & water")],
        trust=corpus_claim_trust(
            authority="PreparedBC", review_provenance="human_verified_repair"
        ),
        publication=None,
    )


def test_verified_corpus_claim_without_publication_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PublicClaim(
            claim_id="C1",
            text="Keep water and food in a grab-and-go bag.",
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[ClaimSupport(evidence_id="E1", quote="Food & water")],
            publication=None,
        )


def test_empty_structured_reviewed_authority_is_still_rejected() -> None:
    with pytest.raises(ValidationError):
        PublicClaim(
            claim_id="C1",
            text="Keep water and food in a grab-and-go bag.",
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[ClaimSupport(evidence_id="E1", quote="Food & water")],
            publication=PublicationAuthority(kind=PublicationKind.STRUCTURED_REVIEWED),
        )


def test_missing_publication_cannot_project_a_privileged_proof_card() -> None:
    response = SimpleNamespace(
        claims=[_claim_without_publication()],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Wildfire Preparedness Guide",
                publisher="PreparedBC",
                canonical_url=HttpUrl("https://example.test/guide.pdf"),
                locator="PDF page 5",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                review_provenance="human_verified_repair",
                primary_text="Grab-and-Go Bag: Food & water",
                context_text="Grab-and-Go Bag: Food & water and emergency supplies.",
            )
        ],
        limitations=["Stable guidance only."],
        live_results=[],
        validation=SimpleNamespace(accepted=True),
        response_mode="grounded",
        related_links=[],
        unavailable_layers=[],
        answer_sections=[],
        aggregate_freshness=None,
    )
    card = build_proof_cards(response)[0]
    assert card.support_state not in _PRIVILEGED
    assert card.truth_class is not TruthClass.SOURCE_FACT
    assert card.publication_state is PublicationState.REJECTED
    assert card.support_label != "Supported by an exact reviewed quotation"


def test_valid_structured_reviewed_claim_keeps_its_conservative_label() -> None:
    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
    )
    assert compiled.claim.publication is not None
    assert compiled.claim.publication.kind == PublicationKind.STRUCTURED_REVIEWED
    assert compiled.card.support_state == "structured_reviewed"
    assert compiled.card.support_label == "Reviewed structured claim"
    assert compiled.card.publication_state is PublicationState.VERIFIED


def test_forged_structured_authority_is_rejected_even_with_all_true_validation() -> None:
    evidence = PublicEvidence(
        evidence_id="E1",
        title="Unrelated source",
        publisher="PreparedBC",
        canonical_url=HttpUrl("https://example.test/unrelated"),
        locator="page:1",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text="There is no evacuation order for Kelowna.",
        context_text="There is no evacuation order for Kelowna.",
    )
    claim = PublicClaim(
        claim_id="C1",
        text=evidence.primary_text,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote=evidence.primary_text)],
        publication=PublicationAuthority(
            kind=PublicationKind.STRUCTURED_REVIEWED,
            typed_claim_id="TC-FORGED-NOT-IN-INVENTORY",
            review_status="approved_static",
            source_revision_sha256="a" * 64,
            source_span_sha256="b" * 64,
            renderer_id="forged.renderer",
            support_provenance="forged",
            risk_tier="A",
        ),
    )

    with pytest.raises(ValidationError, match="structured publication authority"):
        AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="forged-structured",
            response_mode=ResponseMode.GROUNDED,
            answer=claim.text,
            claims=[claim],
            evidence=[evidence],
            validation=_ACCEPTED,
        )


def test_forged_live_typed_claim_without_bound_result_is_rejected() -> None:
    evidence = PublicEvidence(
        evidence_id="E1",
        title="Unrelated source",
        publisher="BC Wildfire Service",
        canonical_url=HttpUrl("https://example.test/unrelated"),
        locator="record:1",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text="No evacuation is needed.",
        context_text="No evacuation is needed.",
    )
    claim = PublicClaim(
        claim_id="C1",
        text=evidence.primary_text,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote=evidence.primary_text)],
        publication=PublicationAuthority(
            kind=PublicationKind.OFFICIAL_LIVE_TYPED,
            typed_live_fact_id="incident:forged-not-in-response",
            review_status="official_live_record",
            renderer_id="firelens.live_typed_renderer.v1",
            support_provenance="typed_official_live_fact",
            risk_tier="B",
        ),
    )

    with pytest.raises(ValidationError, match="live publication authority"):
        AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="forged-live",
            response_mode=ResponseMode.GROUNDED,
            answer=claim.text,
            claims=[claim],
            evidence=[evidence],
            validation=_ACCEPTED,
        )
