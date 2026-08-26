from __future__ import annotations

from datetime import UTC, datetime

import pytest

from firelens.claim_trust import GROUNDED_PUBLIC_WORDING, corpus_claim_trust
from firelens.contracts import (
    BACKGROUND_LIMITATION,
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
from firelens.proof_presentation import AnswerStatusBanner, ProofCard, make_proof_card
from firelens.publication.compiler import compile_structured_claim
from firelens.publication.fallback import explanation_authority
from firelens.publication_contracts import (
    QUOTE_RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
)
from firelens.safety_profile import PublicationState, TruthClass

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
                publication=explanation_authority(),
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
    assert response.supported_items == []
    assert response.unknown_items == ["Stable guidance only."]
    card = response.proof_cards[0]
    assert card.support_state == "source_linked_explanation"
    assert card.support_label == "Source-linked explanation"
    assert card.exact_passage == "Food & water"
    assert card.authority == "PreparedBC"
    assert card.source_revision == "PDF page 5"
    assert card.review_state == "Human-verified source transcription"
    assert card.critical_fields_checked == "Critical fields checked and preserved"
    assert str(card.official_url) == "https://example.test/guide.pdf"


def test_accepted_existing_cards_drop_orphans_and_preserve_matching_claim_card() -> None:
    original = _grounded()
    matching = original.proof_cards[0]
    orphan = matching.model_copy(
        update={"claim_id": "C2", "claim_text": "Stale structured orphan"}
    )
    response = AskResponse.model_validate(
        {
            **original.model_dump(mode="python"),
            "proof_cards": [
                matching.model_dump(mode="python"),
                orphan.model_dump(mode="python"),
            ],
        }
    )

    assert [card.claim_id for card in response.proof_cards] == ["C1"]
    assert response.proof_cards[0].authority == "PreparedBC"
    assert response.proof_cards[0].exact_passage == "Food & water"


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
    matching = response.proof_cards[0]
    orphan = matching.model_copy(
        update={"claim_id": "incident:orphan", "claim_text": "Stale live orphan"}
    )
    revalidated = AskResponse.model_validate(
        {
            **response.model_dump(mode="python"),
            "proof_cards": [
                matching.model_dump(mode="python"),
                orphan.model_dump(mode="python"),
            ],
        }
    )
    assert [card.claim_id for card in revalidated.proof_cards] == ["incident:7"]
    assert revalidated.proof_cards[0].support_state == "live_record"
    assert revalidated.proof_cards[0].authority == "BC Wildfire Service"


def test_preserved_live_card_rebinds_current_result_freshness_and_url() -> None:
    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    fresh = LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/incidents/fresh",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Out of Control",
        name="Test Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
    )
    original = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-live-rebind",
        response_mode=ResponseMode.LIVE,
        answer="Test Fire is Out of Control.",
        live_results=[fresh],
        limitations=["This uses official records and is not a safety determination."],
        aggregate_freshness="fresh",
    )
    assert original.proof_cards[0].publication_state is PublicationState.VERIFIED
    assert original.proof_cards[0].freshness == "fresh"
    stale = LiveResult.model_validate(
        {
            **fresh.model_dump(mode="python"),
            "freshness": Freshness.STALE,
            "source_url": "https://example.test/incidents/stale",
            "status": "Being Held",
        }
    )
    rebound = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-live-rebind-stale",
        response_mode=ResponseMode.LIVE,
        answer="Test Fire is Being Held.",
        live_results=[stale],
        limitations=["This uses official records and is not a safety determination."],
        aggregate_freshness="stale",
        proof_cards=[original.proof_cards[0]],
    )
    card = rebound.proof_cards[0]
    assert card.freshness == "stale"
    assert card.publication_state is PublicationState.REVIEW
    assert str(card.official_url) == "https://example.test/incidents/stale"
    assert card.exact_passage == "Being Held"


def _published_claim(
    *,
    claim_id: str,
    evidence_id: str,
    text: str,
    quote: str,
    kind: PublicationKind,
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED_CORPUS,
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
        renderer_id=(
            "firelens.test_renderer.v1"
            if kind == PublicationKind.STRUCTURED_REVIEWED
            else QUOTE_RENDERER_ID
        ),
        support_provenance="exact_official_quote",
    )
    supports = (
        []
        if evidence_status == EvidenceStatus.GENERAL_BACKGROUND
        else [ClaimSupport(evidence_id=evidence_id, quote=quote)]
    )
    return PublicClaim(
        claim_id=claim_id,
        text=text,
        evidence_status=evidence_status,
        supports=supports,
        trust=corpus_claim_trust(authority="PreparedBC", review_provenance="native_text"),
        publication=publication,
    )


def _forged_structured_reviewed_card(claim_id: str, text: str) -> ProofCard:
    return make_proof_card(
        claim_id=claim_id,
        claim_text=text,
        support_state="structured_reviewed",
        support_label="Reviewed structured claim",
        authority="PreparedBC",
        exact_passage=text,
        source_title="Official emergency guidance",
        source_revision="Emergency guidance",
        review_state="Human-verified source transcription",
        critical_fields_checked="Critical fields checked and preserved",
        freshness="Stable reviewed guidance",
        official_url="https://example.test/e1",
        publication=PublicationAuthority(
            kind=PublicationKind.STRUCTURED_REVIEWED,
            typed_claim_id="TC-FORGED",
            review_status="approved",
            source_revision_sha256="a" * 64,
            renderer_id="firelens.test_renderer.v1",
            support_provenance="typed_inventory",
        ),
    )


def _published_evidence(
    evidence_id: str,
    quote: str,
    *,
    canonical_url: str | None = None,
) -> PublicEvidence:
    return PublicEvidence(
        evidence_id=evidence_id,
        title="Official emergency guidance",
        publisher="PreparedBC",
        canonical_url=canonical_url or f"https://example.test/{evidence_id.lower()}",
        locator="Emergency guidance",
        temporal_class="stable_guidance",
        review_provenance="native_text",
        primary_text=quote,
        context_text=quote,
    )


_ADMITTED_QUOTE = (
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
_ADMITTED_QUOTE_URL = (
    "https://www2.gov.bc.ca/assets/gov/public-safety-and-emergency-services/"
    "emergency-preparedness-response-recovery/embc/preparedbc/preparedbc-guides/"
    "wildfire_preparedness_guide.pdf"
)


def test_quote_only_publication_controls_banner_and_proof_wording() -> None:
    quote = _ADMITTED_QUOTE
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
        evidence=[_published_evidence("E1", quote, canonical_url=_ADMITTED_QUOTE_URL)],
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
    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
    )
    reviewed = compiled.claim.text
    quote = _ADMITTED_QUOTE
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-mixed-publication",
        response_mode=ResponseMode.PARTIAL,
        answer=f"{reviewed} {quote}",
        claims=[
            compiled.claim,
            _published_claim(
                claim_id="C2",
                evidence_id="E2",
                text=quote,
                quote=quote,
                kind=PublicationKind.OFFICIAL_QUOTE_ONLY,
            ),
        ],
        evidence=[
            *compiled.evidence,
            _published_evidence("E2", quote, canonical_url=_ADMITTED_QUOTE_URL),
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
    if kind == PublicationKind.STRUCTURED_REVIEWED:
        compiled = compile_structured_claim(
            typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
        )
        claim = compiled.claim
        evidence = list(compiled.evidence)
    else:
        text = _ADMITTED_QUOTE
        claim = _published_claim(
            claim_id="C1", evidence_id="E1", text=text, quote=text, kind=kind
        )
        evidence = [_published_evidence("E1", text, canonical_url=_ADMITTED_QUOTE_URL)]
    text = claim.text
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=f"trace-rejected-{kind.value}",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=[claim],
        evidence=evidence,
        validation=_REJECTED_VALIDATION,
        proof_cards=[
            make_proof_card(
                claim_id="C1",
                claim_text=text,
                support_state="structured_reviewed",
                support_label="Reviewed structured claim",
                authority="PreparedBC",
                exact_passage=text,
                source_title="Official emergency guidance",
                source_revision="Emergency guidance",
                review_state="Human-verified source transcription",
                critical_fields_checked="Critical fields checked and preserved",
                freshness="Stable reviewed guidance",
                official_url="https://example.test/e1",
                publication=PublicationAuthority(
                    kind=PublicationKind.STRUCTURED_REVIEWED,
                    typed_claim_id="TC-FORGED",
                    review_status="approved",
                    source_revision_sha256="a" * 64,
                    renderer_id="firelens.test_renderer.v1",
                    support_provenance="typed_inventory",
                ),
            )
        ],
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Support not established"
    assert response.status_banner.freshness_label == "Freshness not established"
    assert response.supported_items == []
    card = response.proof_cards[0]
    assert card.support_state == "unknown"
    assert card.support_label == "Not established from FireLens sources"
    assert card.authority == "Authority not established"
    assert card.review_state == "Review state not established"
    assert card.critical_fields_checked == "Critical-field validation not established"
    assert card.freshness == "Freshness not established"
    assert card.exact_passage is None
    assert card.source_title is None
    assert card.source_revision is None
    assert card.official_url is None


def test_rejected_live_response_neutralizes_derived_no_claim_card() -> None:
    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-rejected-live-proof",
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
                freshness=Freshness.FRESH,
                status="Out of Control",
                name="Test Fire",
                geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
            )
        ],
        aggregate_freshness="fresh",
        validation=_REJECTED_VALIDATION,
    )

    card = response.proof_cards[0]
    assert card.support_state == "unknown"
    assert card.support_label == "Not established from FireLens sources"
    assert card.authority == "Authority not established"
    assert card.review_state == "Review state not established"
    assert card.critical_fields_checked == "Critical-field validation not established"
    assert card.freshness == "Freshness not established"
    assert card.exact_passage is None
    assert card.source_title is None
    assert card.source_revision is None
    assert card.official_url is None


def test_rejected_no_claim_response_replaces_strengthening_banner() -> None:
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-rejected-no-claim",
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer="Use the official air-quality service for current observations.",
        claims=[],
        evidence=[],
        limitations=[],
        validation=_REJECTED_VALIDATION,
        status_banner=AnswerStatusBanner(
            headline="Grounded in reviewed official sources",
            detail="All content was validated against reviewed sources.",
            freshness_label="Stable reviewed guidance",
            availability_label="Sources required for this request were available.",
            official_escalation_title="Current B.C. AQHI",
            official_escalation_url=(
                "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"
            ),
        ),
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Support not established"
    assert response.status_banner.detail == (
        "FireLens did not establish or validate support for this response."
    )
    assert response.status_banner.freshness_label == "Freshness not established"
    assert response.status_banner.availability_label == (
        "This request did not complete with established sources."
    )
    assert response.status_banner.official_escalation_title == "Current B.C. AQHI"
    assert str(response.status_banner.official_escalation_url) == (
        "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"
    )


def test_failed_critical_field_preservation_is_not_listed_as_supported() -> None:
    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
    )
    claim = compiled.claim
    text = claim.text
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
        evidence=list(compiled.evidence),
        validation=_VALIDATION,
    )

    assert response.status_banner is not None
    assert response.status_banner.headline == "Support not established"
    assert response.supported_items == []
    card = response.proof_cards[0]
    assert card.support_state == "unknown"
    assert card.authority == "Authority not established"
    assert card.review_state == "Review state not established"
    assert card.critical_fields_checked == "Critical-field validation not established"
    assert card.freshness == "Freshness not established"
    assert card.exact_passage is None
    assert card.source_title is None
    assert card.source_revision is None
    assert card.official_url is None


def test_matching_structured_reviewed_card_is_preserved() -> None:
    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
    )
    text = compiled.claim.text
    original = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-matching-structured",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=[compiled.claim],
        evidence=list(compiled.evidence),
        validation=_VALIDATION,
    )
    matching = original.proof_cards[0]
    assert matching.support_state == "structured_reviewed"
    assert matching.truth_class is TruthClass.SOURCE_FACT
    assert matching.publication_state is PublicationState.VERIFIED

    rebound = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-matching-structured-rebind",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=original.claims,
        evidence=original.evidence,
        validation=_VALIDATION,
        proof_cards=[matching],
    )
    card = rebound.proof_cards[0]
    assert card.support_state == "structured_reviewed"
    assert card.truth_class is TruthClass.SOURCE_FACT
    assert card.publication_state is PublicationState.VERIFIED
    assert card.exact_passage == compiled.card.exact_passage


def test_forged_structured_reviewed_card_text_rebinds_to_linked_claim() -> None:
    compiled = compile_structured_claim(
        typed_claim_id="TC-EVAC-ORDER-001", public_claim_id="C1"
    )
    text = compiled.claim.text
    original = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-structured-text-binding",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=[compiled.claim],
        evidence=list(compiled.evidence),
        validation=_VALIDATION,
    )
    forged = original.proof_cards[0].model_copy(
        update={"claim_text": "Evacuation is unnecessary."}
    )

    rebound = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-structured-text-binding-rebound",
        response_mode=ResponseMode.PARTIAL,
        answer=text,
        claims=original.claims,
        evidence=original.evidence,
        validation=_VALIDATION,
        proof_cards=[forged],
    )

    assert rebound.proof_cards[0].claim_text == text


def test_forged_official_live_typed_card_text_rebinds_to_compiled_claim() -> None:
    from firelens.publication.compiler import compile_live_fact

    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    result = LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/incidents/7",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Out of Control",
        name="Test Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
    )
    compiled = compile_live_fact(result, public_claim_id="C1")
    forged = compiled.card.model_copy(
        update={
            "claim_id": result.result_id,
            "claim_text": "There is no active wildfire.",
        }
    )

    rebound = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="trace-live-text-binding-rebound",
        response_mode=ResponseMode.LIVE,
        answer=compiled.claim.text,
        live_results=[result],
        aggregate_freshness=Freshness.FRESH,
        limitations=["This uses official records and is not a safety determination."],
        proof_cards=[forged],
    )

    assert rebound.proof_cards[0].claim_text == compiled.claim.text


def test_compiled_live_response_keeps_card_bound_by_typed_live_fact_id() -> None:
    from firelens.publication.compiler import compile_live_fact

    timestamp = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
    result = LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/incidents/7",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Out of Control",
        name="Test Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.89]},
    )

    compiled = compile_live_fact(result, public_claim_id="C1")

    assert [card.claim_id for card in compiled.response.proof_cards] == ["C1"]
    assert compiled.response.proof_cards[0].claim_text == compiled.claim.text
    assert compiled.response.proof_cards[0].publication.typed_live_fact_id == result.result_id


@pytest.mark.parametrize(
    ("kind", "mode", "evidence_status", "expect_state", "expect_truth", "expect_pub"),
    [
        (
            PublicationKind.SOURCE_LINKED_EXPLANATION,
            ResponseMode.PARTIAL,
            EvidenceStatus.VERIFIED_CORPUS,
            "source_linked_explanation",
            TruthClass.MODEL_SUMMARY,
            PublicationState.REVIEW,
        ),
        (
            PublicationKind.GENERAL_BACKGROUND,
            ResponseMode.BACKGROUND,
            EvidenceStatus.GENERAL_BACKGROUND,
            "background",
            TruthClass.MODEL_SUMMARY,
            PublicationState.REVIEW,
        ),
        (
            PublicationKind.UNSUPPORTED,
            ResponseMode.PARTIAL,
            EvidenceStatus.VERIFIED_CORPUS,
            "unknown",
            TruthClass.UNKNOWN,
            PublicationState.REJECTED,
        ),
    ],
)
def test_forged_structured_review_card_defers_to_publication_kind(
    kind: PublicationKind,
    mode: ResponseMode,
    evidence_status: EvidenceStatus,
    expect_state: str,
    expect_truth: TruthClass,
    expect_pub: PublicationState,
) -> None:
    text = "Keep an emergency kit ready."
    claims = [
        _published_claim(
            claim_id="C1",
            evidence_id="E1",
            text=text,
            quote=text,
            kind=kind,
            evidence_status=evidence_status,
        )
    ]
    evidence = (
        []
        if evidence_status == EvidenceStatus.GENERAL_BACKGROUND
        else [_published_evidence("E1", text)]
    )
    limitations = [BACKGROUND_LIMITATION] if mode == ResponseMode.BACKGROUND else []
    generated = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=f"trace-generated-{kind.value}",
        response_mode=mode,
        answer=text,
        claims=claims,
        evidence=evidence,
        limitations=limitations,
        validation=_VALIDATION,
    )
    generated_card = generated.proof_cards[0]
    assert generated_card.support_state == expect_state
    assert generated_card.truth_class is expect_truth
    assert generated_card.publication_state is expect_pub

    forged = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=f"trace-forged-{kind.value}",
        response_mode=mode,
        answer=text,
        claims=claims,
        evidence=evidence,
        limitations=limitations,
        validation=_VALIDATION,
        proof_cards=[_forged_structured_reviewed_card("C1", text)],
    )
    card = forged.proof_cards[0]
    assert card.support_state == expect_state
    assert card.truth_class is expect_truth
    assert card.publication_state is expect_pub
    assert card.publication_state is not PublicationState.VERIFIED
    if expect_state == "unknown":
        assert card.authority == "Authority not established"
        assert card.exact_passage is None
        assert card.official_url is None
