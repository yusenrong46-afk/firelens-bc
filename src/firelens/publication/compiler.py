"""Only module allowed to construct STRUCTURED_REVIEWED and OFFICIAL_LIVE_TYPED."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from pydantic import HttpUrl

from firelens.answering.context import (
    SUPPORT_TOKEN_OVERLAP_FLOOR,
    support_token_overlap,
)
from firelens.answering.request_facets import requests_contents
from firelens.answering.risk_policy import RiskTier
from firelens.answering.typed_records import load_inventory, match_quote
from firelens.answering.typed_snapshot import classify_text
from firelens.claim_trust import corpus_claim_trust
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
    aggregate_live_freshness,
    render_claim_texts,
)
from firelens.live_claim_renderer import render_typed_live_claim
from firelens.live_contracts import LiveResult
from firelens.proof_presentation import ProofCard, make_proof_card
from firelens.publication.compiled_validation import (
    atomic_quote_overlap as _atomic_quote_overlap,
)
from firelens.publication.compiled_validation import (
    compiled_validation_handoff as _compiled_validation_handoff,
)
from firelens.publication.compiled_validation import (
    compiler_validation_report as _compiler_validation_report,
)
from firelens.publication.compiled_validation import (
    packet_identity_errors as _packet_identity_errors,
)
from firelens.publication.compiled_validation import (
    unique_public_evidence as _unique_public_evidence,
)
from firelens.publication.compiled_validation import (
    validate_compiled_publication as _validate_compiled_publication,
)
from firelens.publication.fallback import (
    QUOTE_ONLY_LIMITATION,
    UNCOVERED_LIMITATION,
    official_handoff_response,
    quote_only_claim,
)
from firelens.publication.records import get_versioned
from firelens.publication_contracts import (
    LIVE_RENDERER_ID,
    RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
    StructuredReviewedClaimBlock,
)

_APPLICABILITY_QUALIFIERS = (
    re.compile(
        r"\bif\s+(?:i|we|you|someone|a person|people)\s+"
        r"(?:am|are|is|have|has)\s+(?P<scope>[^?.,;]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:for|about)\s+(?:a\s+)?(?:person|people|someone|residents?|individuals?)\s+"
        r"(?:who\s+(?:is|are|have|has)|with)\s+(?P<scope>[^?.,;]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bas\s+(?:a|an)\s+(?P<scope>[^?.,;]{1,60}?)\s+"
        r"(?:person|resident|individual)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class CompiledClaim:
    claim: PublicClaim
    evidence: tuple[PublicEvidence, ...]
    card: ProofCard
    response: AskResponse | None = None


def compile_structured_claim(
    *,
    typed_claim_id: str,
    public_claim_id: str,
    source_revision_sha256: str | None = None,
    root: str | None = None,
) -> CompiledClaim:
    record = get_versioned(typed_claim_id, root=root)
    if source_revision_sha256 and source_revision_sha256 != record.source_revision_sha256:
        raise ValueError("source revision mismatch invalidates structured support")
    if not record.available_for_structured_support:
        raise ValueError(f"{typed_claim_id} is not available for structured support")
    if record.canonical_url is None:
        raise ValueError(f"{typed_claim_id} has no exact structured source URL")
    block = StructuredReviewedClaimBlock(
        public_claim_id=public_claim_id,
        typed_claim_id=record.claim_id,
        review_status=record.human_review_state,
        source_revision_sha256=record.source_revision_sha256,
        renderer_id=RENDERER_ID,
        support_provenance="human_reviewed_typed_claim",
    )
    quote = record.source_span_text[:500]
    evidence = PublicEvidence(
        evidence_id=f"S-{record.claim_id}",
        title=f"{record.authority} reviewed guidance",
        publisher=record.authority,
        canonical_url=HttpUrl(record.canonical_url),
        locator=record.source_revision,
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        review_provenance="native_text",
        primary_text=record.source_span_text,
        context_text=record.source_span_text,
    )
    authority = PublicationAuthority(
        kind=PublicationKind.STRUCTURED_REVIEWED,
        typed_claim_id=block.typed_claim_id,
        review_status=block.review_status,
        source_revision_sha256=block.source_revision_sha256,
        source_span_sha256=record.source_span_sha256,
        renderer_id=block.renderer_id,
        support_provenance=block.support_provenance,
        risk_tier=record.risk_tier.value,
    )
    claim = PublicClaim(
        claim_id=public_claim_id,
        text=record.canonical_text,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id=evidence.evidence_id, quote=quote)],
        trust=corpus_claim_trust(
            authority=record.authority,
            review_provenance=record.human_review_state,
        ),
        publication=authority,
    )
    card = _card_from_claim(claim, evidence, "structured_reviewed", "Reviewed structured claim")
    response = _grounded_response(
        [claim], [evidence], [card], trace_id=f"structured-{typed_claim_id}"
    )
    return CompiledClaim(claim=claim, evidence=(evidence,), card=card, response=response)


def compile_live_fact(result: LiveResult, public_claim_id: str) -> CompiledClaim:
    text = render_typed_live_claim(result)
    authority = PublicationAuthority(
        kind=PublicationKind.OFFICIAL_LIVE_TYPED,
        typed_live_fact_id=result.result_id,
        review_status="official_live_record",
        renderer_id=LIVE_RENDERER_ID,
        support_provenance="typed_official_live_fact",
        risk_tier=RiskTier.B.value,
    )
    claim = PublicClaim(
        claim_id=public_claim_id,
        text=text,
        evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
        trust=None,
        publication=authority,
    )
    card = make_proof_card(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        support_state="official_live_typed",
        support_label="Official live record",
        authority=result.authority,
        exact_passage=result.status,
        source_title=result.name or result.result_id,
        source_revision=result.source_updated_at.isoformat(),
        review_state="Official live record as published",
        critical_fields_checked="Rendered from typed live fields",
        freshness=str(
            result.freshness.value if hasattr(result.freshness, "value") else result.freshness
        ),
        official_url=result.source_url,
        derivation=result.distance_derivation,
        publication=authority,
    )
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=f"live-{result.result_id}",
        response_mode=ResponseMode.LIVE,
        answer=text,
        claims=[],
        live_results=[result],
        aggregate_freshness=aggregate_live_freshness([result]),
        limitations=["This uses official records and is not a safety determination."],
        proof_cards=[card],
    )
    return CompiledClaim(claim=claim, evidence=(), card=card, response=response)


def compile_high_risk_answer(
    question: str,
    packet: EvidencePacket,
    *,
    trace_id: str,
    supported_aspects: Sequence[str] = (),
) -> AskResponse:
    packet_errors = _packet_identity_errors(packet)
    if packet_errors:
        return _compiled_validation_handoff(
            trace_id,
            _compiler_validation_report(
                packet_errors,
                schema_valid=False,
                citation_ids_valid=False,
                quotes_exact=False,
                claim_support_valid=False,
                policy_valid=False,
            ),
        )
    targets = _publication_targets(question, supported_aspects)
    selected = select_typed_claim_ids(
        packet,
        question=question,
        supported_aspects=supported_aspects,
    )
    claims: list[PublicClaim] = []
    evidence: list[PublicEvidence] = []
    cards: list[ProofCard] = []
    for index, claim_id in enumerate(selected, start=1):
        compiled = compile_structured_claim(
            typed_claim_id=claim_id,
            public_claim_id=f"C{index}",
        )
        claims.append(compiled.claim)
        evidence.extend(compiled.evidence)
        cards.append(compiled.card)
    uncovered_targets = list(_uncovered_publication_targets(claims, targets))
    covered_quotes = {support.quote for claim in claims for support in claim.supports}
    quote_index = len(claims)
    for candidate in packet.quote_candidates:
        if classify_text(candidate.text) not in {RiskTier.A, RiskTier.B}:
            continue
        matched_targets = tuple(
            target
            for target in uncovered_targets
            if _quote_candidate_covers_target(candidate.text, target)
        )
        if not matched_targets:
            continue
        if any(
            candidate.text[:80].casefold() in quote.casefold()
            or quote[:80].casefold() in candidate.text.casefold()
            for quote in covered_quotes
        ):
            continue
        quote_index += 1
        claim, item, card = quote_only_claim(
            candidate, public_claim_id=f"C{quote_index}", packet=packet
        )
        claims.append(claim)
        evidence.append(item)
        cards.append(card)
        uncovered_targets = [
            target for target in uncovered_targets if target not in matched_targets
        ]
    if not claims:
        return official_handoff_response(trace_id)
    limitations = list(packet.limitations)
    reason = None
    if any(
        claim.publication and claim.publication.kind == PublicationKind.OFFICIAL_QUOTE_ONLY
        for claim in claims
    ):
        limitations.append(QUOTE_ONLY_LIMITATION)
        limitations.append(UNCOVERED_LIMITATION)
        reason = ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED
    evidence = _unique_public_evidence(evidence)
    answer = render_claim_texts(claims)
    validation = _validate_compiled_publication(
        packet=packet,
        claims=claims,
        evidence=evidence,
        cards=cards,
        answer=answer,
    )
    if not validation.accepted:
        return _compiled_validation_handoff(trace_id, validation)
    return _grounded_response(
        claims,
        evidence,
        cards,
        trace_id=trace_id,
        limitations=limitations,
        reason=reason,
        response_mode=(
            ResponseMode.PARTIAL
            if any(
                claim.publication
                and claim.publication.kind == PublicationKind.OFFICIAL_QUOTE_ONLY
                for claim in claims
            )
            else ResponseMode.GROUNDED
        ),
        validation=validation,
    )


def select_typed_claim_ids(
    packet: EvidencePacket,
    *,
    question: str | None = None,
    supported_aspects: Sequence[str] = (),
) -> list[str]:
    selected: list[str] = []
    targets = _publication_targets(question or packet.question, supported_aspects)
    evidence_by_id = {item.evidence_id: item for item in packet.items}
    for candidate in packet.quote_candidates:
        evidence = evidence_by_id.get(candidate.evidence_id)
        span_records = []
        if evidence is not None:
            span_ids = set(evidence.primary_chunk_ids)
            span_records = [
                record
                for record in load_inventory().records
                if span_ids.intersection(record.source_span_ids)
                and _atomic_quote_overlap(candidate.text, record.source_span_text)
            ]
        records = [*span_records, *match_quote(candidate.text)]
        for record in records:
            versioned = get_versioned(record.claim_id)
            if (
                versioned.available_for_structured_support
                and _typed_record_matches_publication_target(
                    record.claim_id,
                    versioned.approved_surface_sha256,
                    versioned.source_span_sha256,
                    targets,
                )
                and record.claim_id not in selected
            ):
                selected.append(record.claim_id)
    return selected


def _publication_targets(question: str, supported_aspects: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            target.strip() for target in (question, *supported_aspects) if target.strip()
        )
    )


def _matches_publication_target(text: str, targets: Sequence[str]) -> bool:
    return any(
        support_token_overlap(text, target) >= SUPPORT_TOKEN_OVERLAP_FLOOR for target in targets
    )


def _quote_candidate_covers_target(text: str, target: str) -> bool:
    if support_token_overlap(text, target) < SUPPORT_TOKEN_OVERLAP_FLOOR:
        return False
    if any(
        support_token_overlap(text, qualifier) < 1.0
        for qualifier in _applicability_qualifiers(target)
    ):
        return False
    return not requests_contents(target) or _supplies_contents(text)


def _supplies_contents(text: str) -> bool:
    """Return whether source wording supplies actual contents, not just a container."""

    item_lines = [
        line for line in text.splitlines() if re.match(r"^\s*(?:[•¢*\-]|\d+[.)])\s*\S", line)
    ]
    if len(item_lines) >= 2:
        return True

    normalized = " ".join(text.casefold().split())
    relation = re.search(
        r"\b(?:include(?:s|d|ing)?|contain(?:s|ed|ing)?|consist(?:s|ed|ing)?\s+of|"
        r"pack(?:s|ed|ing)?\b.{0,20}\bwith|items?\s+such\s+as|such\s+as)\b"
        r"(?P<contents>.{0,300})",
        normalized,
    )
    if relation is None:
        return False
    contents = relation.group("contents")
    separators = len(re.findall(r",|;|\b(?:and|or)\b|&", contents))
    return separators >= 2


def _uncovered_publication_targets(
    claims: Sequence[PublicClaim], targets: Sequence[str]
) -> tuple[str, ...]:
    """Keep quote-only fallback for requested aspects lacking structured coverage."""

    structured_text = "\n".join(
        text
        for claim in claims
        if claim.publication and claim.publication.kind == PublicationKind.STRUCTURED_REVIEWED
        for text in (claim.text, *(support.quote for support in claim.supports))
    )
    return tuple(
        target
        for target in targets
        if support_token_overlap(structured_text, target) < SUPPORT_TOKEN_OVERLAP_FLOOR
        or (requests_contents(target) and not _supplies_contents(structured_text))
    )


@lru_cache(maxsize=1_024)
def _typed_record_matches_publication_target(
    claim_id: str,
    approved_surface_sha256: str,
    source_span_sha256: str,
    targets: tuple[str, ...],
) -> bool:
    current = get_versioned(claim_id)
    if (
        current.approved_surface_sha256 != approved_surface_sha256
        or current.source_span_sha256 != source_span_sha256
    ):
        return False
    scope_text = "\n".join(
        value
        for value in (
            current.record.subject,
            current.record.status_stage,
            *current.record.conditions,
            *current.record.applies_to,
        )
        if value
    )
    if any(
        qualifier and support_token_overlap(scope_text, qualifier) < 1.0
        for target in targets
        for qualifier in _applicability_qualifiers(target)
    ):
        return False
    return _matches_publication_target(
        f"{current.canonical_text}\n{current.source_span_text}", targets
    )


@lru_cache(maxsize=2_048)
def _applicability_qualifiers(target: str) -> tuple[str, ...]:
    """Extract user-stated applicability constraints without a domain phrase list.

    A broad topic overlap must not let a reviewed claim about one population
    answer a question explicitly scoped to another. The qualifier is compared
    only with the claim's reviewed typed scope fields, and every qualifier token
    must be represented there before structured publication is allowed.
    """

    action_boundary = re.compile(
        r"\b(?:do not|don't|should|must|can|could|may|will|would)\b",
        re.IGNORECASE,
    )
    return tuple(
        qualifier
        for pattern in _APPLICABILITY_QUALIFIERS
        if (match := pattern.search(target)) is not None
        if (
            qualifier := " ".join(
                action_boundary.split(match.group("scope"), maxsplit=1)[0].split()
            )
        )
    )


def packet_requires_structured(packet: EvidencePacket, question: str = "") -> bool:
    texts = [question, *(item.primary_text for item in packet.items)]
    texts.extend(candidate.text for candidate in packet.quote_candidates)
    return any(classify_text(text) in {RiskTier.A, RiskTier.B} for text in texts if text)


def public_mixed_answer(packet: object, connective: str) -> str:
    static = getattr(packet, "static_response", None)
    claims = getattr(static, "claims", None) if static is not None else None
    if not claims:
        return connective
    guidance = render_claim_texts(claims)
    if _live_connective_safe(connective, guidance):
        if guidance and guidance in connective:
            return connective
        return "\n\n".join(part for part in (connective.strip(), guidance) if part)
    live_results = getattr(packet, "live_results", []) or []
    live_text = _compact_live_statuses(live_results)
    return "\n\n".join(part for part in (live_text, guidance) if part)


def _live_connective_safe(connective: str, guidance: str) -> bool:
    remainder = connective.replace(guidance, " ") if guidance else connective
    return classify_text(remainder) not in {RiskTier.A, RiskTier.B}


def _compact_live_statuses(results: list[LiveResult]) -> str:
    lines: list[str] = []
    for result in results:
        name = result.name or result.incident_number or result.result_id
        lines.append(f"{name} status is {result.status} according to {result.authority}.")
    return " ".join(lines)


def compiled_static_text(packet: object) -> str | None:
    static = getattr(packet, "static_response", None)
    if static is None or not getattr(static, "claims", None):
        return None
    if any(getattr(claim, "publication", None) for claim in static.claims):
        return (static.answer or "").strip() or None
    return None


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


def _card_from_claim(
    claim: PublicClaim,
    evidence: PublicEvidence,
    support_state: str,
    support_label: str,
) -> ProofCard:
    authority = claim.publication
    return make_proof_card(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        support_state=support_state,  # type: ignore[arg-type]
        support_label=support_label,
        authority=(
            claim.trust.source_authority if claim.trust is not None else evidence.publisher
        ),
        exact_passage=claim.supports[0].quote if claim.supports else None,
        source_title=evidence.title,
        source_revision=authority.source_revision_sha256 if authority else evidence.locator,
        review_state=authority.review_status if authority else "none",
        critical_fields_checked="Compiled from a reviewed typed record"
        if support_state == "structured_reviewed"
        else "Exact official wording, not a FireLens interpretation",
        freshness="Stable reviewed guidance",
        official_url=evidence.canonical_url,
        publication=(
            authority
            if authority is not None
            else PublicationAuthority(kind=PublicationKind.UNSUPPORTED)
        ),
    )


def _grounded_response(
    claims: list[PublicClaim],
    evidence: list[PublicEvidence],
    cards: list[ProofCard],
    *,
    trace_id: str,
    limitations: list[str] | None = None,
    reason: ReasonCode | None = None,
    response_mode: ResponseMode = ResponseMode.GROUNDED,
    validation: ValidationReport | None = None,
) -> AskResponse:
    unique_evidence = _unique_public_evidence(evidence)
    answer = render_claim_texts(claims)
    executed_validation = validation or _validate_compiled_publication(
        packet=None,
        claims=claims,
        evidence=unique_evidence,
        cards=cards,
        answer=answer,
    )
    if not executed_validation.accepted:
        raise ValueError(
            "compiled publication validation failed: " + "; ".join(executed_validation.errors)
        )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=trace_id,
        response_mode=response_mode,
        answer=answer,
        claims=claims,
        evidence=unique_evidence,
        limitations=limitations or ["Grounded in reviewed official sources."],
        reason_code=reason,
        validation=executed_validation,
        proof_cards=cards,
    )
