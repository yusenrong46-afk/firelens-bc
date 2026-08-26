"""Public OpenAPI publication fields stay compatible with origin/main."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

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
from firelens.proof_contracts import ProofCard
from firelens.publication_contracts import (
    QUOTE_RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
)
from firelens.safety_profile import PublicationState, TruthClass

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = json.loads((ROOT / "docs/openapi.v1.json").read_text(encoding="utf-8"))


def test_openapi_proof_card_does_not_require_publication() -> None:
    schema = OPENAPI["components"]["schemas"]["ProofCard"]
    assert "publication" not in schema.get("required", [])
    assert "publication" not in schema.get("properties", {})


def test_openapi_public_claim_publication_stays_optional_nullable() -> None:
    schema = OPENAPI["components"]["schemas"]["PublicClaim"]
    assert "publication" not in schema.get("required", [])
    publication = schema["properties"]["publication"]
    assert publication.get("anyOf") == [
        {"$ref": "#/components/schemas/PublicationAuthority"},
        {"type": "null"},
    ]


def test_python_proof_card_still_requires_internal_publication() -> None:
    with pytest.raises(ValidationError):
        ProofCard(
            claim_id="incident:7",
            claim_text="Mountain Fire",
            support_state="live_record",
            support_label="Official live record as published",
            authority="BC Wildfire Service",
            review_state="Official live feed as published",
            critical_fields_checked="Not applicable — live record, not a reviewed claim",
            freshness="fresh",
            truth_class=TruthClass.SOURCE_FACT,
            publication_state=PublicationState.VERIFIED,
        )


def test_verified_corpus_claim_still_requires_publication_authority() -> None:
    with pytest.raises(ValidationError):
        PublicClaim(
            claim_id="C1",
            text="Keep water and food in a grab-and-go bag.",
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[ClaimSupport(evidence_id="E1", quote="Food & water")],
        )


_ADMITTED_GRAB_AND_GO = (
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
_ACCEPTED = ValidationReport(
    accepted=True,
    schema_valid=True,
    citation_ids_valid=True,
    quotes_exact=True,
    claim_support_valid=True,
    policy_valid=True,
)


def _quote_only_response(*, url: str, quote: str) -> AskResponse:
    evidence = PublicEvidence(
        evidence_id="E1",
        title="Wildfire Preparedness Guide",
        publisher="PreparedBC",
        canonical_url=HttpUrl(url),
        locator="PDF page 5",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text=quote,
        context_text=quote,
    )
    claim = PublicClaim(
        claim_id="C1",
        text=quote,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote=quote)],
        publication=PublicationAuthority(
            kind=PublicationKind.OFFICIAL_QUOTE_ONLY,
            review_status="extraction_only",
            renderer_id=QUOTE_RENDERER_ID,
            support_provenance="exact_official_quote",
            risk_tier="A",
        ),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="quote-only-contract",
        response_mode=ResponseMode.PARTIAL,
        answer=quote,
        claims=[claim],
        evidence=[evidence],
        validation=_ACCEPTED,
    )


def test_direct_quote_only_contract_rejects_forged_government_url_and_text() -> None:
    with pytest.raises(ValidationError, match="quote-only publication authority"):
        _quote_only_response(
            url="https://www2.gov.bc.ca/forged-official-page",
            quote=_ADMITTED_GRAB_AND_GO,
        )
    with pytest.raises(ValidationError, match="quote-only publication authority"):
        _quote_only_response(
            url=_ADMITTED_PREPAREDBC_PDF,
            quote="Evacuate Kelowna immediately. This is not in the admitted corpus.",
        )


def test_direct_quote_only_contract_accepts_admitted_official_quote() -> None:
    response = _quote_only_response(
        url=_ADMITTED_PREPAREDBC_PDF,
        quote=_ADMITTED_GRAB_AND_GO,
    )
    assert response.claims[0].publication is not None
    assert response.claims[0].publication.kind == PublicationKind.OFFICIAL_QUOTE_ONLY
    assert response.evidence[0].canonical_url == HttpUrl(_ADMITTED_PREPAREDBC_PDF)
