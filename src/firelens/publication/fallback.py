"""Safe uncovered high-risk publication: quote-only, partial, or official handoff."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import HttpUrl

from firelens.answering.risk_policy import RiskTier
from firelens.claim_trust import corpus_claim_trust
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    EvidenceStatus,
    PublicClaim,
    PublicEvidence,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
)
from firelens.ingestion.acquire import APPROVED_SOURCE_HOSTS
from firelens.proof_presentation import ProofCard, make_proof_card
from firelens.publication.records import admitted_corpus_chunk
from firelens.publication_contracts import (
    QUOTE_RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
)

# A table-extraction artifact in the admitted PreparedBC PDF interleaves the
# three mutually exclusive evacuation stages on one line.  It remains an exact
# source substring, but is not one atomic proposition a person can safely use.
# Keep this deliberately narrow: this is not a general OCR-quality heuristic.
_EVACUATION_STAGE_HEADING = re.compile(
    r"\bevacuation\s+(alert|order|rescind)\s*:",
    re.IGNORECASE,
)

OFFICIAL_SOURCE_URL = (
    "https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery"
)
QUOTE_ONLY_LIMITATION = "Exact source wording — not a structured FireLens claim."
UNCOVERED_LIMITATION = (
    "Some requested high-risk guidance has no reviewed structured claim. "
    "FireLens is showing official wording or a handoff, not an interpreted claim."
)
MISSING_ASPECT_LIMITATION_PREFIX = "Not supported by selected evidence: "


def is_atomic_official_quote_only(quote: str) -> bool:
    """Return whether an exact quote can stand alone as one safety proposition.

    Reviewed structured records may intentionally compare stages.  Quote-only
    publication has no such typed interpretation layer, so a span that embeds
    two or more headed evacuation stages is omitted rather than rewritten.
    """

    stages = {match.group(1).casefold() for match in _EVACUATION_STAGE_HEADING.finditer(quote)}
    return len(stages) <= 1


def explanation_authority() -> PublicationAuthority:
    return PublicationAuthority(
        kind=PublicationKind.SOURCE_LINKED_EXPLANATION,
        review_status="none",
        renderer_id="firelens.grounded_generator.v1",
        support_provenance="validated_generated_explanation",
        risk_tier=RiskTier.C.value,
    )


def background_authority() -> PublicationAuthority:
    return PublicationAuthority(kind=PublicationKind.GENERAL_BACKGROUND)


def admitted_official_quote_source(
    item: PublicEvidence | EvidenceSpan | None,
    quote: str = "",
) -> bool:
    """Quote-only official wording requires an admitted chunk and exact quote."""

    if item is None or not quote:
        return False
    chunk_ids = tuple(getattr(item, "primary_chunk_ids", ()) or ())
    digest = str(getattr(item, "document_sha256", "") or "")
    claimed_url = str(getattr(item, "canonical_url", "") or "").rstrip("/")
    if (
        not chunk_ids
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return False
    for chunk_id in chunk_ids:
        admitted = admitted_corpus_chunk(str(chunk_id))
        if admitted is None or admitted["document_sha256"] != digest:
            continue
        admitted_url = admitted["canonical_url"].rstrip("/")
        if admitted_url != claimed_url:
            continue
        host = (urlparse(admitted_url).hostname or "").casefold()
        if host not in APPROVED_SOURCE_HOSTS and not host.endswith(".gov.bc.ca"):
            continue
        if _quote_occurs_in_admitted_text(quote, admitted["text"]):
            return True
    return False


def _quote_occurs_in_admitted_text(quote: str, corpus_text: str) -> bool:
    if quote in corpus_text:
        return True
    normalized_quote = " ".join(quote.split())
    return bool(normalized_quote) and normalized_quote in " ".join(corpus_text.split())


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
        publication=authority,
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
