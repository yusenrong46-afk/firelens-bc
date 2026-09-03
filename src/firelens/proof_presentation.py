"""Additive proof-carrying fields derived from a public AskResponse.

Models stay out of contracts.py. Callers may pass an AskResponse duck-type.
This never invents official facts; it only restates typed response fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import HttpUrl

from firelens._publication_authority import (
    _UNSUPPORTED_PUBLICATION,
    _bound_publication,
    _live_publication,
    _official_live_id_matches,
    _publication_support_state,
)
from firelens.claim_trust import GROUNDED_PUBLIC_WORDING
from firelens.freshness_language import official_records_headline
from firelens.live_claim_renderer import render_typed_live_claim
from firelens.proof_contracts import (
    AnswerStatusBanner as AnswerStatusBanner,
)
from firelens.proof_contracts import (
    ProofCard as ProofCard,
)
from firelens.proof_contracts import (
    SupportState,
)
from firelens.proof_contracts import (
    make_proof_card as make_proof_card,
)
from firelens.publication_contracts import PublicationKind

BCWS_MAP_URL = "https://wildfiresituation.nrs.gov.bc.ca/map"

_HEADLINES: dict[str, str] = {
    "grounded": "Grounded in reviewed official sources",
    "partial": "Partially supported by reviewed sources",
    "conflict": "Reviewed sources conflict",
    "background": "General model knowledge — not checked against reviewed sources",
    "mixed": "Official records plus reviewed guidance",
    "capability": "What you can ask FireLens",
    "scope_redirect": "Outside FireLens live sources",
    "abstention": "FireLens could not establish this",
    "requires_input": "A BC place is needed to continue",
}

_SUPPORT_LABELS: dict[SupportState, str] = {
    "supported": "Supported by an exact reviewed quotation",
    "structured_reviewed": "Reviewed structured claim",
    "official_live_typed": "Official live record",
    "official_quote_only": "Exact source wording — not a structured FireLens claim",
    "source_linked_explanation": "Source-linked explanation",
    "unknown": "Not established from FireLens sources",
    "background": "General background — not a reviewed quotation",
    "conflict": "Conflicting reviewed sources; no winner chosen",
    "live_record": "Official live record as published",
}


def attach_proof_presentation(response: Any) -> None:
    """Fill additive proof fields and neutralize any unestablished cards."""

    if _validation_rejected(response) or getattr(response, "status_banner", None) is None:
        response.status_banner = build_status_banner(response)
    if not getattr(response, "supported_items", None):
        response.supported_items = build_supported_items(response)
    if not getattr(response, "unknown_items", None):
        response.unknown_items = build_unknown_items(response)
    existing_cards = list(getattr(response, "proof_cards", None) or [])
    if _validation_rejected(response):
        response.proof_cards = build_proof_cards(response)
    elif not existing_cards:
        response.proof_cards = build_proof_cards(response)
    else:
        claims_by_id = {claim.claim_id: claim for claim in response.claims}
        results_by_id = {
            result.result_id: result for result in getattr(response, "live_results", None) or []
        }
        response.proof_cards = [
            _preserve_existing_card(card, response, claims_by_id, results_by_id)
            for card in existing_cards
            if _card_has_response_owner(card, claims_by_id, results_by_id)
        ]


def _card_has_response_owner(
    card: Any,
    claims_by_id: dict[str, Any],
    results_by_id: dict[str, Any],
) -> bool:
    if card.claim_id in claims_by_id or card.claim_id in results_by_id:
        return True
    publication = _bound_publication(card)
    return (
        getattr(card, "support_state", None) == "official_live_typed"
        and publication.kind == PublicationKind.OFFICIAL_LIVE_TYPED
        and publication.typed_live_fact_id in results_by_id
    )


def build_status_banner(response: Any) -> AnswerStatusBanner:
    mode = _mode(response)
    if _validation_rejected(response):
        title, url = _escalation(response)
        return AnswerStatusBanner(
            headline="Support not established",
            detail="FireLens did not establish or validate support for this response.",
            freshness_label="Freshness not established",
            availability_label="This request did not complete with established sources.",
            retrieval_completed_at=_latest_attr(response.live_results, "retrieved_at"),
            source_updated_at=_latest_attr(response.live_results, "source_updated_at"),
            official_escalation_title=title,
            official_escalation_url=url,
        )
    publication_presentation = _publication_banner(response)
    freshness = (
        publication_presentation[2]
        if publication_presentation is not None
        else _freshness_label(response)
    )
    reason = getattr(response, "reason_code", None)
    reason_value = getattr(reason, "value", reason)
    if publication_presentation:
        headline = publication_presentation[0]
    elif mode == "live":
        headline = official_records_headline(response.aggregate_freshness)
    elif mode == "scope_redirect" and reason_value == "live_data_required":
        headline = "Select an official record to continue"
    else:
        headline = _HEADLINES.get(mode, "FireLens response")
    title, url = _escalation(response)
    return AnswerStatusBanner(
        headline=headline,
        detail=(
            publication_presentation[1]
            if publication_presentation is not None
            else _banner_detail(response, mode)
        ),
        freshness_label=freshness,
        availability_label=_availability_label(response),
        retrieval_completed_at=_latest_attr(response.live_results, "retrieved_at"),
        source_updated_at=_latest_attr(response.live_results, "source_updated_at"),
        official_escalation_title=title,
        official_escalation_url=url,
    )


def build_supported_items(response: Any) -> list[str]:
    items: list[str] = []
    for claim in response.claims:
        state = _support_state(response, claim)
        if state in {"supported", "structured_reviewed", "official_live_typed"}:
            items.append(_clip(claim.text))
    for result in response.live_results:
        name = result.name or result.incident_number or result.result_id
        items.append(_clip(f"{name} ({result.kind})"))
    return items[:12]


def build_unknown_items(response: Any) -> list[str]:
    items: list[str] = []
    for limitation in response.limitations:
        text = limitation.strip()
        if text:
            items.append(_clip(text))
    for kind in response.unavailable_layers:
        items.append(_clip(f"Official {kind} layer unavailable this turn"))
    for section in response.answer_sections:
        if section.kind == "uncertainty" and section.text.strip():
            items.append(_clip(section.text))
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique[:12]


def build_proof_cards(response: Any) -> list[ProofCard]:
    evidence_by_id = {item.evidence_id: item for item in response.evidence}
    cards = [_claim_card(response, claim, evidence_by_id) for claim in response.claims]
    if cards:
        return cards[:12]
    return [_live_card(response, result) for result in response.live_results][:12]


def _claim_card(response: Any, claim: Any, evidence_by_id: dict[str, Any]) -> ProofCard:
    support = claim.supports[0] if claim.supports else None
    evidence = evidence_by_id.get(support.evidence_id) if support is not None else None
    trust = claim.trust
    state = _support_state(response, claim)
    unknowns = list(response.limitations[:4])
    if trust is not None and trust.conflict_or_supersession != "none":
        unknowns.insert(0, f"Conflict or supersession: {trust.conflict_or_supersession}")
    card = make_proof_card(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        support_state=state,
        support_label=_SUPPORT_LABELS[state],
        authority=_authority(trust, evidence, response),
        exact_passage=support.quote if support is not None else None,
        source_title=evidence.title if evidence is not None else None,
        source_revision=(
            evidence.locator if evidence is not None and evidence.locator else None
        ),
        review_state=(
            "Source extraction only; no structured-claim review"
            if state == "official_quote_only"
            else _review_state(trust, evidence)
        ),
        critical_fields_checked=_critical_fields(trust),
        freshness=(
            "Stable source wording"
            if state == "official_quote_only"
            else _card_freshness(response, trust)
        ),
        conflicts_or_unknowns=[_clip(item) for item in unknowns if item][:8],
        official_url=(
            evidence.canonical_url if evidence is not None else _escalation(response)[1]
        ),
        rejected=state == "unknown" or _validation_rejected(response),
        publication=_bound_publication(claim),
    )
    return _unknown_card(card) if state == "unknown" else card


def _preserve_existing_card(
    card: Any,
    response: Any,
    claims_by_id: dict[str, Any],
    results_by_id: dict[str, Any],
) -> ProofCard:
    claim = claims_by_id.get(card.claim_id)
    if claim is not None:
        expected = _support_state(response, claim)
        if getattr(card, "support_state", None) == "unknown" or expected == "unknown":
            return _unknown_card(card)
        if not _proof_card_matches_claim(card, claim, expected):
            return _claim_card(
                response,
                claim,
                {item.evidence_id: item for item in response.evidence},
            )
        return card if isinstance(card, ProofCard) else ProofCard.model_validate(card)
    result = results_by_id.get(card.claim_id)
    card_publication = _bound_publication(card)
    live_id = getattr(card_publication, "typed_live_fact_id", None)
    if result is None and live_id:
        result = results_by_id.get(live_id)
    is_live_typed = (
        card_publication.kind == PublicationKind.OFFICIAL_LIVE_TYPED
        or getattr(card, "support_state", None) == "official_live_typed"
    )
    if result is None and not is_live_typed:
        derivation = getattr(card, "derivation", None)
        for source_id in getattr(derivation, "input_source_ids", None) or []:
            result = results_by_id.get(source_id)
            if result is not None:
                break
    if is_live_typed and (
        result is None or not _official_live_id_matches(card, result=result, claim=None)
    ):
        return _unknown_card(card)
    if result is not None and getattr(card, "support_state", None) in {
        "live_record",
        "official_live_typed",
    }:
        if (
            "km geodesic" in str(card.claim_text).casefold()
            and getattr(result, "distance_derivation", None) is None
        ):
            return _unknown_card(card)
        return _rebind_live_card(card, response, result)
    if getattr(card, "support_state", None) == "unknown":
        return _unknown_card(card)
    return card if isinstance(card, ProofCard) else ProofCard.model_validate(card)


def _proof_card_matches_claim(card: Any, claim: Any, expected: SupportState) -> bool:
    return (
        getattr(card, "support_state", None) == expected
        and getattr(card, "claim_text", None) == getattr(claim, "text", None)
        and _bound_publication(card) == _bound_publication(claim)
        and _official_live_id_matches(card, result=None, claim=claim)
    )


def _rebind_live_card(card: Any, response: Any, result: Any) -> ProofCard:
    claim_text = _live_result_claim_text(card, result)
    rebound = make_proof_card(
        claim_id=card.claim_id,
        claim_text=claim_text,
        support_state=card.support_state,
        support_label=card.support_label,
        authority=result.authority,
        exact_passage=result.status,
        source_title=card.source_title or result.name or result.result_id,
        source_revision=result.source_updated_at.isoformat(),
        review_state=card.review_state,
        critical_fields_checked=card.critical_fields_checked,
        freshness=str(
            result.freshness.value if hasattr(result.freshness, "value") else result.freshness
        ),
        conflicts_or_unknowns=list(card.conflicts_or_unknowns),
        official_url=result.source_url,
        rejected=_validation_rejected(response),
        derivation=getattr(result, "distance_derivation", None),
        publication=_live_publication(result),
    )
    return _unknown_card(rebound) if _validation_rejected(response) else rebound


def _live_result_claim_text(card: Any, result: Any) -> str:
    if getattr(card, "support_state", None) == "official_live_typed":
        return render_typed_live_claim(result)
    return str(result.name or result.incident_number or result.result_id)


def _live_card(response: Any, result: Any) -> ProofCard:
    name = result.name or result.incident_number or result.result_id
    card = make_proof_card(
        claim_id=result.result_id,
        claim_text=name,
        support_state="live_record",
        support_label=_SUPPORT_LABELS["live_record"],
        authority=result.authority,
        exact_passage=result.status,
        source_title=name,
        source_revision=result.source_updated_at.isoformat(),
        review_state="Official live feed as published",
        critical_fields_checked="Not applicable — live record, not a reviewed claim",
        freshness=str(result.freshness),
        official_url=result.source_url,
        rejected=_validation_rejected(response),
        derivation=getattr(result, "distance_derivation", None),
        publication=_live_publication(result),
    )
    return _unknown_card(card) if _validation_rejected(response) else card


def _unknown_card(card: Any) -> ProofCard:
    return make_proof_card(
        claim_id=card.claim_id,
        claim_text=card.claim_text,
        support_state="unknown",
        support_label=_SUPPORT_LABELS["unknown"],
        authority="Authority not established",
        review_state="Review state not established",
        critical_fields_checked="Critical-field validation not established",
        freshness="Freshness not established",
        conflicts_or_unknowns=list(card.conflicts_or_unknowns),
        rejected=True,
        publication=_UNSUPPORTED_PUBLICATION,
    )


def _mode(response: Any) -> str:
    mode = response.response_mode
    return mode.value if hasattr(mode, "value") else str(mode)


def _validation_rejected(response: Any) -> bool:
    validation = getattr(response, "validation", None)
    return validation is not None and getattr(validation, "accepted", True) is False


def _publication_banner(response: Any) -> tuple[str, str, str] | None:
    """Return conservative answer-level copy for explicit publication authority."""

    states = {_support_state(response, claim) for claim in response.claims}
    if states == {"unknown"}:
        return (
            "Support not established",
            "FireLens could not validate support for the claims in this response.",
            "Freshness not established",
        )
    if "official_quote_only" not in states:
        return None
    reviewed = bool(states & {"structured_reviewed", "official_live_typed"})
    if reviewed:
        return (
            "Reviewed claims plus source wording",
            "Reviewed structured claims and extraction-only source wording are labelled separately.",
            "Stable guidance and source wording",
        )
    return (
        "Official wording from a source",
        (
            "FireLens is showing an exact source quotation. It has not been "
            "approved as a structured FireLens claim."
        ),
        "Stable source wording",
    )


def _banner_detail(response: Any, mode: str) -> str:
    if mode in {"grounded", "partial"}:
        return GROUNDED_PUBLIC_WORDING
    if mode == "conflict":
        return (
            "FireLens is showing both reviewed statements and cannot determine "
            "which version governs."
        )
    if mode == "background":
        return "This explanation uses general model knowledge, not reviewed quotations."
    if mode == "live":
        return (
            "These facts come from official B.C. wildfire records. "
            "This is not a safety assessment."
        )
    if mode == "mixed":
        return "Official records and reviewed guidance are labelled separately below."
    if mode == "capability":
        return "Ask about reviewed preparedness guidance or official BC wildfire records."
    if mode == "requires_input":
        return (
            "FireLens needs a BC community or approximate location to continue "
            "this live request."
        )
    if mode == "scope_redirect":
        reason = getattr(response, "reason_code", None)
        reason_value = getattr(reason, "value", reason)
        if reason_value == "live_data_required":
            return (
                "Click a fire on the map or name a British Columbia community, then ask again."
            )
        return "Use the related official service for information FireLens does not ingest live."
    if response.answer:
        return _clip(str(response.answer), 500)
    return "FireLens could not produce a validated answer from the available evidence."


def _freshness_label(response: Any) -> str:
    freshness = response.aggregate_freshness
    value = freshness.value if hasattr(freshness, "value") else freshness
    if value == "stale":
        return "Cached official records; the live refresh failed"
    if value == "mixed":
        return "Some records are out of date; check each record's time"
    if value == "fresh":
        return "Current official records"
    if response.evidence:
        return "Reviewed guidance; does not change day to day"
    return "Freshness not applicable"


def _availability_label(response: Any) -> str:
    layers = [str(kind) for kind in response.unavailable_layers]
    if layers:
        names = ", ".join(layers)
        return f"Unavailable layers: {names}. That is not an all-clear."
    if response.status == "error" or _mode(response) == "abstention":
        return "This request did not complete with established sources."
    return "Sources required for this request were available."


def _escalation(response: Any) -> tuple[str | None, HttpUrl | None]:
    if response.related_links:
        link = response.related_links[0]
        return link.title, link.url
    if response.evidence:
        return "Open official source", response.evidence[0].canonical_url
    if response.live_results:
        return "Open BCWS map", HttpUrl(BCWS_MAP_URL)
    banner = getattr(response, "status_banner", None)
    banner_title = getattr(banner, "official_escalation_title", None)
    banner_url = getattr(banner, "official_escalation_url", None)
    if banner_title and banner_url:
        return banner_title, banner_url
    return None, None


def _support_state(response: Any, claim: Any) -> SupportState:
    validation = getattr(response, "validation", None)
    if validation is not None and getattr(validation, "accepted", True) is False:
        return "unknown"
    trust = getattr(claim, "trust", None)
    if trust is not None and getattr(trust, "critical_field_preservation", None) == "failed":
        return "unknown"
    return _publication_support_state(claim)


def _authority(trust: Any, evidence: Any, response: Any) -> str:
    if trust is not None and trust.source_authority:
        return str(trust.source_authority)
    if evidence is not None:
        return str(evidence.publisher)
    if response.live_results:
        return str(response.live_results[0].authority)
    return "FireLens reviewed sources"


def _review_state(trust: Any, evidence: Any) -> str:
    if trust is not None:
        mapping = {
            "approved_static": "Approved static corpus",
            "human_verified_repair": "Human-verified source transcription",
            "pending_review": "Pending human review",
            "none": "No human-review state recorded",
        }
        return mapping.get(trust.human_review_state, str(trust.human_review_state))
    if evidence is not None and evidence.review_provenance == "human_verified_repair":
        return "Human-verified source transcription"
    if evidence is not None:
        return "Native reviewed text"
    return "No reviewed passage attached"


def _critical_fields(trust: Any) -> str:
    if trust is None:
        return "Not applicable"
    mapping = {
        "preserved": "Critical fields checked and preserved",
        "failed": "Critical-field check failed",
        "not_applicable": "Critical-field check not applicable",
    }
    return mapping.get(trust.critical_field_preservation, "Not applicable")


def _card_freshness(response: Any, trust: Any) -> str:
    if trust is not None:
        mapping = {
            "stable_guidance": "Reviewed guidance; does not change day to day",
            "fresh": "Current official records",
            "stale": "Cached official records; the live refresh failed",
            "mixed": "Some records are out of date",
            "unknown": "Freshness unknown",
        }
        return mapping.get(trust.freshness, str(trust.freshness))
    return _freshness_label(response)


def _latest_attr(results: list[Any], name: str) -> datetime | None:
    values = [getattr(item, name) for item in results if getattr(item, name, None) is not None]
    return max(values) if values else None


def _clip(text: str, limit: int = 200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"
