"""Fail-closed authority binding for claims entering a public AskResponse."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from firelens.contract_composition import canonical_live_or_mixed_answers
from firelens.live_claim_renderer import render_typed_live_claim
from firelens.publication.records import admitted_corpus_index, get_versioned
from firelens.publication_contracts import (
    LIVE_RENDERER_ID,
    QUOTE_RENDERER_ID,
    PublicationKind,
)

_CONTROL_STAGES = ("out of control", "being held", "under control")
_KILOMETRE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:km|kilomet(?:er|re)s?)\b",
    re.IGNORECASE,
)
_FIRE_COUNT = re.compile(
    r"\b(\d+)\s+(?:active\s+)?(?:wildfires?|fires?)\b(?!\s+of\s+note\b)",
    re.IGNORECASE,
)


def live_answer_binding_error(answer: str, live_results: Sequence[Any]) -> str | None:
    """Return why live prose is not bound to fetched official records."""

    if not answer or not live_results:
        return None
    statuses = {str(getattr(item, "status", "") or "").casefold() for item in live_results}
    lowered = answer.casefold()
    for stage in _CONTROL_STAGES:
        if stage in lowered and not any(stage in status for status in statuses if status):
            return "live answer control stages must match fetched official records"
    allowed_km = tuple(
        float(item.distance_km)
        for item in live_results
        if getattr(item, "distance_km", None) is not None
    )
    for match in _KILOMETRE.finditer(answer):
        value = float(match.group(1))
        if not any(abs(value - allowed) <= 0.1 for allowed in allowed_km):
            return "live answer kilometre quantities must match fetched official records"
    incident_count = sum(
        1
        for item in live_results
        if str(getattr(getattr(item, "kind", None), "value", getattr(item, "kind", "")))
        == "incident"
    )
    allowed_counts = {len(live_results), incident_count}
    # "12 fires ... as Out of Control": a per-status count of incident records.
    per_status: dict[str, int] = {}
    for item in live_results:
        kind = str(getattr(getattr(item, "kind", None), "value", getattr(item, "kind", "")))
        if kind != "incident":
            continue
        status = " ".join(str(getattr(item, "status", "") or "").casefold().split())
        per_status[status] = per_status.get(status, 0) + 1
    allowed_counts.update(per_status.values())
    for match in _FIRE_COUNT.finditer(answer):
        if int(match.group(1)) not in allowed_counts:
            return "live answer fire counts must match fetched official records"
    return None


def current_records_binding_error(
    answer: str | None,
    live_results: Sequence[Any],
    answer_sections: Sequence[Any],
) -> str | None:
    """Bind live current-records text without scanning reviewed-guidance sections."""

    sections = [
        (
            str(getattr(getattr(section, "kind", None), "value", getattr(section, "kind", ""))),
            section.text,
        )
        for section in answer_sections
    ]
    current = next((text for kind, text in sections if kind == "current_records"), None)
    if sections:
        allowed = canonical_live_or_mixed_answers(sections)
        if not allowed:
            return "live and mixed answers must use canonical section composition"
        if (answer or "") not in allowed:
            return "live top-level answer must match canonical current-record composition"
        return live_answer_binding_error(current or "", live_results)
    return live_answer_binding_error(answer or "", live_results)


def ask_claim_publication_error(response: Any) -> str | None:
    evidence_by_id = {item.evidence_id: item for item in response.evidence}
    live_results_by_id = {item.result_id: item for item in response.live_results}
    for claim in response.claims:
        error = public_claim_authority_error(
            claim,
            evidence_by_id=evidence_by_id,
            live_results_by_id=live_results_by_id,
        )
        if error:
            return f"claim {claim.claim_id}: {error}"
    return None


def public_claim_authority_error(
    claim: Any,
    *,
    evidence_by_id: dict[str, Any],
    live_results_by_id: dict[str, Any],
) -> str | None:
    """Return why a privileged claim is not bound to its governing source."""

    authority = claim.publication
    if authority is None:
        status = getattr(claim, "evidence_status", None)
        value = getattr(status, "value", status)
        if value == "verified_corpus":
            return "verified corpus claims require publication authority"
        return None
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
    if authority is None:
        return "structured publication authority is not currently bound"
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
    if authority is None:
        return "live publication authority is not bound to this response"
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
    if authority is None:
        return "quote-only publication authority is not exact-source bound"
    if len(claim.supports) != 1:
        return "quote-only publication authority requires one exact support"
    support = claim.supports[0]
    evidence = evidence_by_id.get(support.evidence_id)
    matches = (
        evidence is not None
        and claim.text == support.quote
        and support.quote in evidence.primary_text
        and _admitted_quote_matches(str(evidence.canonical_url), support.quote)
        and authority.review_status == "extraction_only"
        and authority.renderer_id == QUOTE_RENDERER_ID
        and authority.support_provenance == "exact_official_quote"
    )
    return None if matches else "quote-only publication authority is not exact-source bound"


def _admitted_quote_matches(canonical_url: str, quote: str) -> bool:
    """Fail closed unless the quote occurs in an admitted chunk at this URL."""

    if not canonical_url or not quote:
        return False
    claimed = canonical_url.rstrip("/")
    normalized_quote = " ".join(quote.split())
    for chunk in admitted_corpus_index().values():
        if chunk["canonical_url"].rstrip("/") != claimed:
            continue
        text = chunk["text"]
        if quote in text:
            return True
        if normalized_quote and normalized_quote in " ".join(text.split()):
            return True
    return False
