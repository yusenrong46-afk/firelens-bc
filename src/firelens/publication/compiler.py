"""Only module allowed to construct STRUCTURED_REVIEWED and OFFICIAL_LIVE_TYPED."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import HttpUrl

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
from firelens.live_contracts import LiveResult
from firelens.proof_presentation import ProofCard
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

OFFICIAL_SOURCE_URL = (
    "https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery"
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
        canonical_url=HttpUrl(OFFICIAL_SOURCE_URL),
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
    text = _live_text(result)
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
    card = ProofCard(
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
) -> AskResponse:
    del question
    selected = select_typed_claim_ids(packet)
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
    covered_quotes = {support.quote for claim in claims for support in claim.supports}
    quote_index = len(claims)
    for candidate in packet.quote_candidates:
        if classify_text(candidate.text) not in {RiskTier.A, RiskTier.B}:
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
    return _grounded_response(
        claims, evidence, cards, trace_id=trace_id, limitations=limitations, reason=reason
    )


def select_typed_claim_ids(packet: EvidencePacket) -> list[str]:
    selected: list[str] = []
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
            if versioned.available_for_structured_support and record.claim_id not in selected:
                selected.append(record.claim_id)
    return selected


def _atomic_quote_overlap(candidate_text: str, source_text: str) -> bool:
    candidate = " ".join(candidate_text.split()).casefold()
    source = " ".join(source_text.split()).casefold()
    if min(len(candidate), len(source)) < 24:
        return False
    return candidate in source or source in candidate


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


def _live_text(result: LiveResult) -> str:
    name = result.name or result.incident_number or result.result_id
    freshness = (
        result.freshness.value if hasattr(result.freshness, "value") else result.freshness
    )
    parts = [
        f"{name} status is {result.status} according to {result.authority}.",
        f"Official source updated {result.source_updated_at.date().isoformat()}.",
        f"FireLens retrieved this record {result.retrieved_at.isoformat()}.",
        f"Freshness is {freshness}.",
    ]
    if result.distance_km is not None:
        parts.append(f"Distance {result.distance_km} km.")
    parts.append("This is not a safety determination.")
    return " ".join(parts)


def _card_from_claim(
    claim: PublicClaim,
    evidence: PublicEvidence,
    support_state: str,
    support_label: str,
) -> ProofCard:
    authority = claim.publication
    return ProofCard(
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
    )


def _grounded_response(
    claims: list[PublicClaim],
    evidence: list[PublicEvidence],
    cards: list[ProofCard],
    *,
    trace_id: str,
    limitations: list[str] | None = None,
    reason: ReasonCode | None = None,
) -> AskResponse:
    seen: set[str] = set()
    unique_evidence: list[PublicEvidence] = []
    for item in evidence:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        unique_evidence.append(item)
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=trace_id,
        response_mode=ResponseMode.GROUNDED,
        answer=render_claim_texts(claims),
        claims=claims,
        evidence=unique_evidence,
        limitations=limitations or ["Grounded in reviewed official sources."],
        reason_code=reason,
        validation=ValidationReport(
            accepted=True,
            schema_valid=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
            errors=[],
        ),
        proof_cards=cards,
    )
