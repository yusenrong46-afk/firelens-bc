"""Fail-closed authority binding for claims entering a public AskResponse."""

from __future__ import annotations

from typing import Any

from firelens.live_claim_renderer import render_typed_live_claim
from firelens.publication.records import get_versioned
from firelens.publication_contracts import (
    LIVE_RENDERER_ID,
    QUOTE_RENDERER_ID,
    PublicationKind,
)


def public_claim_authority_error(
    claim: Any,
    *,
    evidence_by_id: dict[str, Any],
    live_results_by_id: dict[str, Any],
) -> str | None:
    """Return why a privileged claim is not bound to its governing source."""

    authority = claim.publication
    if authority.kind == PublicationKind.STRUCTURED_REVIEWED:
        return _structured_authority_error(claim, evidence_by_id)
    if authority.kind == PublicationKind.OFFICIAL_LIVE_TYPED:
        return _live_authority_error(claim, live_results_by_id)
    if authority.kind == PublicationKind.OFFICIAL_QUOTE_ONLY:
        return _quote_authority_error(claim, evidence_by_id)
    return None


def _structured_authority_error(
    claim: Any,
    evidence_by_id: dict[str, Any],
) -> str | None:
    authority = claim.publication
    try:
        current = get_versioned(str(authority.typed_claim_id))
    except ValueError:
        return "structured publication authority references an unknown typed claim"

    expected_evidence_id = f"S-{current.claim_id}"
    expected_quote = current.source_span_text[:500]
    actual_support = [(item.evidence_id, item.quote) for item in claim.supports]
    evidence = evidence_by_id.get(expected_evidence_id)
    matches = (
        current.available_for_structured_support
        and claim.text == current.canonical_text
        and actual_support == [(expected_evidence_id, expected_quote)]
        and authority.review_status == current.human_review_state
        and authority.source_revision_sha256 == current.source_revision_sha256
        and authority.source_span_sha256 == current.source_span_sha256
        and authority.renderer_id == current.renderer_id
        and authority.support_provenance == "human_reviewed_typed_claim"
        and authority.risk_tier == current.risk_tier.value
        and evidence is not None
        and evidence.publisher == current.authority
        and str(evidence.canonical_url).rstrip("/") == str(current.canonical_url).rstrip("/")
        and evidence.locator == current.source_revision
        and evidence.primary_text == current.source_span_text
        and expected_quote in evidence.primary_text
    )
    return None if matches else "structured publication authority is not currently bound"


def _live_authority_error(
    claim: Any,
    live_results_by_id: dict[str, Any],
) -> str | None:
    authority = claim.publication
    result = live_results_by_id.get(str(authority.typed_live_fact_id))
    matches = (
        result is not None
        and claim.text == render_typed_live_claim(result)
        and authority.review_status == "official_live_record"
        and authority.renderer_id == LIVE_RENDERER_ID
        and authority.support_provenance == "typed_official_live_fact"
        and authority.risk_tier == "B"
        and not claim.supports
    )
    return None if matches else "live publication authority is not bound to this response"


def _quote_authority_error(
    claim: Any,
    evidence_by_id: dict[str, Any],
) -> str | None:
    authority = claim.publication
    if len(claim.supports) != 1:
        return "quote-only publication authority requires one exact support"
    support = claim.supports[0]
    evidence = evidence_by_id.get(support.evidence_id)
    matches = (
        evidence is not None
        and claim.text == support.quote
        and support.quote in evidence.primary_text
        and authority.review_status == "extraction_only"
        and authority.renderer_id == QUOTE_RENDERER_ID
        and authority.support_provenance == "exact_official_quote"
    )
    return None if matches else "quote-only publication authority is not exact-source bound"
