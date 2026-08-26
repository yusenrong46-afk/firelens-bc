"""Deterministic abstention, infrastructure-error, and conflict responses."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import HttpUrl

from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidencePacket,
    EvidenceStatus,
    PublicClaim,
    PublicEvidence,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.publication.fallback import explanation_authority


def provider_abstention(
    trace_id: str,
    *,
    reason_code: ReasonCode,
    error_kind: str,
    limitations: Sequence[str],
) -> AskResponse:
    """Fail closed without presenting a provider formatting failure as an answer."""

    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=trace_id,
        response_mode=ResponseMode.ABSTENTION,
        answer="FireLens could not produce a validated answer from the available evidence.",
        reason_code=reason_code,
        error_kind=error_kind,
        limitations=list(limitations),
    )


def unavailable_response(
    trace_id: str,
    *,
    reason_code: ReasonCode,
    error_kind: str,
    limitations: Sequence[str],
) -> AskResponse:
    """Preserve the typed infrastructure-error contract for retrieval failures."""

    return AskResponse(
        status=ResponseStatus.ERROR,
        trace_id=trace_id,
        response_mode=ResponseMode.ABSTENTION,
        reason_code=reason_code,
        error_kind=error_kind,
        limitations=list(limitations),
    )


def safe_abstention(
    trace_id: str,
    *,
    answer: str,
    reason_code: ReasonCode,
    limitations: Sequence[str],
) -> AskResponse:
    """Return a user-visible abstention with a stable reason code."""

    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=trace_id,
        response_mode=ResponseMode.ABSTENTION,
        answer=answer,
        limitations=list(limitations),
        reason_code=reason_code,
    )


def conflict_response(trace_id: str, packet: EvidencePacket) -> AskResponse:
    """Render deterministic source disagreement without choosing a winner."""

    conflict = packet.conflicts[0]
    candidates = {candidate.quote_id: candidate for candidate in packet.quote_candidates}
    evidence_spans = {item.evidence_id: item for item in packet.items}
    selected = [candidates[quote_id] for quote_id in conflict.quote_ids]
    public_claims: list[PublicClaim] = []
    public_evidence: list[PublicEvidence] = []
    seen_evidence: set[str] = set()
    for claim_index, candidate in enumerate(selected, start=1):
        span = evidence_spans[candidate.evidence_id]
        public_claims.append(
            PublicClaim(
                claim_id=f"C{claim_index}",
                text=f"{span.title} contains one of the conflicting requirements.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[
                    ClaimSupport(evidence_id=candidate.evidence_id, quote=candidate.text)
                ],
                publication=explanation_authority(),
            )
        )
        if candidate.evidence_id in seen_evidence:
            continue
        seen_evidence.add(candidate.evidence_id)
        public_evidence.append(
            PublicEvidence(
                evidence_id=candidate.evidence_id,
                title=span.title,
                publisher=span.publisher,
                canonical_url=HttpUrl(span.canonical_url),
                locator=span.locator,
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                review_provenance=span.review_provenance,
                primary_text=span.primary_text,
                context_text=span.context_text,
            )
        )
    validation = ValidationReport(
        accepted=True,
        citation_ids_valid=True,
        quotes_exact=True,
        claim_support_valid=True,
        policy_valid=True,
        errors=[],
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=trace_id,
        response_mode=ResponseMode.CONFLICT,
        answer=(
            "The selected approved sources conflict. FireLens is showing both statements and "
            "cannot determine which version governs; check the issuing authority or the most "
            "recent official document before acting."
        ),
        claims=public_claims,
        evidence=public_evidence,
        limitations=[*packet.limitations, conflict.explanation],
        reason_code=ReasonCode.CONFLICTING_EVIDENCE,
        validation=validation,
    )
