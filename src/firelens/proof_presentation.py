"""Additive proof-carrying fields derived from a public AskResponse.

Models stay out of contracts.py. Callers may pass an AskResponse duck-type.
This never invents official facts; it only restates typed response fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, HttpUrl, model_validator

from firelens.claim_trust import GROUNDED_PUBLIC_WORDING
from firelens.contract_base import FrozenStrictModel
from firelens.derivation_policy import derivation_policy_errors
from firelens.freshness_language import official_records_headline
from firelens.live_contracts import (
    DISTANCE_ALGORITHM,
    DISTANCE_UNIT,
    GEODESIC_CRS,
    DistanceDerivation,
)
from firelens.safety_profile import (
    PublicationState,
    TruthClass,
    bind_proof_profile,
    verified_critical_metadata_present,
)

BCWS_MAP_URL = "https://wildfiresituation.nrs.gov.bc.ca/map"

SupportState = Literal[
    "supported",
    "structured_reviewed",
    "official_live_typed",
    "official_quote_only",
    "source_linked_explanation",
    "unknown",
    "background",
    "conflict",
    "live_record",
]

_HEADLINES: dict[str, str] = {
    "grounded": "Grounded in reviewed official sources",
    "partial": "Partially supported by reviewed sources",
    "conflict": "Reviewed sources conflict",
    "background": "General background — not corpus-checked",
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


class AnswerStatusBanner(FrozenStrictModel):
    headline: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)
    freshness_label: str = Field(min_length=1, max_length=80)
    availability_label: str = Field(min_length=1, max_length=160)
    retrieval_completed_at: datetime | None = None
    source_updated_at: datetime | None = None
    official_escalation_title: str | None = Field(default=None, max_length=120)
    official_escalation_url: HttpUrl | None = None


class ProofCard(FrozenStrictModel):
    claim_id: str = Field(min_length=1, max_length=200)
    claim_text: str = Field(min_length=1, max_length=600)
    support_state: SupportState
    support_label: str = Field(min_length=1, max_length=120)
    authority: str = Field(min_length=1, max_length=160)
    exact_passage: str | None = Field(default=None, max_length=500)
    source_title: str | None = Field(default=None, max_length=200)
    source_revision: str | None = Field(default=None, max_length=200)
    review_state: str = Field(min_length=1, max_length=120)
    critical_fields_checked: str = Field(min_length=1, max_length=160)
    freshness: str = Field(min_length=1, max_length=80)
    conflicts_or_unknowns: list[str] = Field(default_factory=list, max_length=8)
    official_url: HttpUrl | None = None
    truth_class: TruthClass
    publication_state: PublicationState
    derivation: DistanceDerivation | None = None

    @model_validator(mode="after")
    def profile_metadata_matches_support_state(self) -> ProofCard:
        expected_truth, expected_state = bind_proof_profile(
            self.support_state, freshness=self.freshness
        )
        if self.truth_class != expected_truth or self.publication_state != expected_state:
            raise ValueError(
                "proof card profile metadata must match support state and freshness"
            )
        if (
            expected_state is PublicationState.VERIFIED
            and not verified_critical_metadata_present(self)
        ):
            raise ValueError("verified proof cards require complete critical metadata")
        if self.derivation is not None:
            if self.derivation.truth_class is not TruthClass.DETERMINISTIC_DERIVATION:
                raise ValueError(
                    "distance derivation cannot conceal a non-derivation truth class"
                )
            if (
                self.derivation.crs != GEODESIC_CRS
                or self.derivation.units != DISTANCE_UNIT
                or self.derivation.algorithm != DISTANCE_ALGORITHM
            ):
                raise ValueError("unsupported CRS or units cannot be emitted as supported")
            policy_errors = derivation_policy_errors(
                claim_id=self.claim_id,
                claim_text=self.claim_text,
                freshness=self.freshness,
                derivation=self.derivation,
            )
            if policy_errors:
                raise ValueError(policy_errors[0])
        elif "km geodesic" in self.claim_text.casefold():
            raise ValueError("distance-bearing claims require derivation binding")
        return self


def make_proof_card(
    *,
    claim_id: str,
    claim_text: str,
    support_state: SupportState,
    support_label: str,
    authority: str,
    review_state: str,
    critical_fields_checked: str,
    freshness: str,
    exact_passage: str | None = None,
    source_title: str | None = None,
    source_revision: str | None = None,
    conflicts_or_unknowns: list[str] | None = None,
    official_url: HttpUrl | None = None,
    rejected: bool = False,
    derivation: DistanceDerivation | None = None,
) -> ProofCard:
    """Construct a proof card with deterministic Safety Profile metadata."""

    if rejected:
        support_state = "unknown"
    truth_class, publication_state = bind_proof_profile(
        support_state, rejected=rejected, freshness=freshness
    )
    return ProofCard(
        claim_id=claim_id,
        claim_text=claim_text,
        support_state=support_state,
        support_label=support_label,
        authority=authority,
        exact_passage=exact_passage,
        source_title=source_title,
        source_revision=source_revision,
        review_state=review_state,
        critical_fields_checked=critical_fields_checked,
        freshness=freshness,
        conflicts_or_unknowns=list(conflicts_or_unknowns or []),
        official_url=official_url,
        truth_class=truth_class,
        publication_state=publication_state,
        derivation=derivation,
    )


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
        valid_card_ids = set(claims_by_id) or set(results_by_id)
        response.proof_cards = [
            _preserve_existing_card(card, response, claims_by_id, results_by_id)
            for card in existing_cards
            if card.claim_id in valid_card_ids
        ]


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
    headline = (
        publication_presentation[0]
        if publication_presentation
        else (
            official_records_headline(response.aggregate_freshness)
            if mode == "live"
            else _HEADLINES.get(mode, "FireLens response")
        )
    )
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
    )
    return _unknown_card(card) if state == "unknown" else card


def _preserve_existing_card(
    card: Any,
    response: Any,
    claims_by_id: dict[str, Any],
    results_by_id: dict[str, Any],
) -> ProofCard:
    claim = claims_by_id.get(card.claim_id)
    expected = _support_state(response, claim) if claim is not None else None
    if card.support_state == "unknown" or expected == "unknown":
        return _unknown_card(card)
    if claim is not None:
        if card.support_state != expected:
            return _claim_card(
                response,
                claim,
                {item.evidence_id: item for item in response.evidence},
            )
        return card if isinstance(card, ProofCard) else ProofCard.model_validate(card)
    result = results_by_id.get(card.claim_id)
    if result is None:
        derivation = getattr(card, "derivation", None)
        for source_id in getattr(derivation, "input_source_ids", None) or []:
            result = results_by_id.get(source_id)
            if result is not None:
                break
    if result is not None and card.support_state in {"live_record", "official_live_typed"}:
        if (
            "km geodesic" in str(card.claim_text).casefold()
            and getattr(result, "distance_derivation", None) is None
        ):
            return _unknown_card(card)
        return _rebind_live_card(card, response, result)
    return card if isinstance(card, ProofCard) else ProofCard.model_validate(card)


def _rebind_live_card(card: Any, response: Any, result: Any) -> ProofCard:
    rebound = make_proof_card(
        claim_id=card.claim_id,
        claim_text=card.claim_text,
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
    )
    return _unknown_card(rebound) if _validation_rejected(response) else rebound


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
            "These facts come from official BC wildfire records. "
            "This is not a safety determination."
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
        return "Use the related official service for information FireLens does not ingest live."
    if response.answer:
        return _clip(str(response.answer), 500)
    return "FireLens could not produce a validated answer from the available evidence."


def _freshness_label(response: Any) -> str:
    freshness = response.aggregate_freshness
    value = freshness.value if hasattr(freshness, "value") else freshness
    if value == "stale":
        return "Stale cached official records"
    if value == "mixed":
        return "Mixed freshness — check each record timestamp"
    if value == "fresh":
        return "Fresh official records"
    if response.evidence:
        return "Stable reviewed guidance"
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


def _publication_kind(claim: Any) -> str:
    publication = getattr(claim, "publication", None)
    if publication is None:
        return ""
    kind = getattr(publication, "kind", publication)
    return kind.value if hasattr(kind, "value") else str(kind)


def _support_state(response: Any, claim: Any) -> SupportState:
    validation = getattr(response, "validation", None)
    if validation is not None and getattr(validation, "accepted", True) is False:
        return "unknown"
    trust = claim.trust
    if trust is not None and trust.critical_field_preservation == "failed":
        return "unknown"
    kind = _publication_kind(claim)
    if kind == "structured_reviewed":
        if _mode(response) == "conflict":
            return "conflict"
        return "structured_reviewed"
    if kind == "official_live_typed":
        return "official_live_typed"
    if kind == "official_quote_only":
        return "official_quote_only"
    if kind == "source_linked_explanation":
        return "source_linked_explanation"
    if kind == "general_background":
        return "background"
    if kind == "unsupported":
        return "unknown"
    if _mode(response) == "conflict":
        return "conflict"
    status = claim.evidence_status
    value = status.value if hasattr(status, "value") else status
    if value == "general_background":
        return "background"
    if claim.supports:
        return "supported"
    return "unknown"


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
            "stable_guidance": "Stable reviewed guidance",
            "fresh": "Fresh official records",
            "stale": "Stale cached official records",
            "mixed": "Mixed freshness",
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
