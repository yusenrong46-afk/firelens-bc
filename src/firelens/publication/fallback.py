"""Safe uncovered high-risk publication: quote-only, partial, or official handoff."""

from __future__ import annotations

from pydantic import HttpUrl

from firelens.answering.risk_policy import RiskTier
from firelens.claim_trust import corpus_claim_trust
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceStatus,
    PublicClaim,
    PublicEvidence,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
)
from firelens.proof_presentation import ProofCard, make_proof_card
from firelens.publication_contracts import (
    QUOTE_RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
)

OFFICIAL_SOURCE_URL = (
    "https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery"
)
QUOTE_ONLY_LIMITATION = "Exact source wording — not a structured FireLens claim."
UNCOVERED_LIMITATION = (
    "Some requested high-risk guidance has no reviewed structured claim. "
    "FireLens is showing official wording or a handoff, not an interpreted claim."
)


def quote_only_claim(
    candidate: EvidenceQuoteCandidate, *, public_claim_id: str, packet: EvidencePacket
) -> tuple[PublicClaim, PublicEvidence, ProofCard]:
    text = candidate.text
    evidence_id = candidate.evidence_id
    item = next((row for row in packet.items if row.evidence_id == evidence_id), None)
    evidence = PublicEvidence(
        evidence_id=evidence_id,
        title=item.title if item is not None else "Official source",
        publisher=item.publisher if item is not None else "Official source",
        canonical_url=HttpUrl(item.canonical_url if item is not None else OFFICIAL_SOURCE_URL),
        locator=item.locator if item is not None else None,
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        review_provenance=item.review_provenance if item is not None else "native_text",
        primary_text=item.primary_text if item is not None else text,
        context_text=item.context_text if item is not None else text,
    )
    authority = PublicationAuthority(
        kind=PublicationKind.OFFICIAL_QUOTE_ONLY,
        review_status="extraction_only",
        renderer_id=QUOTE_RENDERER_ID,
        support_provenance="exact_official_quote",
        risk_tier=RiskTier.A.value,
    )
    claim = PublicClaim(
        claim_id=public_claim_id,
        text=text[:600],
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id=evidence.evidence_id, quote=text[:500])],
        trust=corpus_claim_trust(
            authority=evidence.publisher,
            review_provenance=evidence.review_provenance,
        ),
        publication=authority,
    )
    card = make_proof_card(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        support_state="official_quote_only",
        support_label="Exact source wording — not a structured FireLens claim",
        authority=evidence.publisher,
        exact_passage=claim.supports[0].quote,
        source_title=evidence.title,
        source_revision=evidence.locator,
        review_state="Source extraction only; no structured-claim review",
        critical_fields_checked="Exact official wording, not a FireLens interpretation",
        freshness="Stable source wording",
        official_url=evidence.canonical_url,
    )
    return claim, evidence, card


def official_handoff_response(trace_id: str) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=trace_id,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            "FireLens does not have a reviewed structured claim for this high-risk "
            "question. Use the issuing authority for official wording."
        ),
        reason_code=ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED,
        limitations=[UNCOVERED_LIMITATION],
    )
