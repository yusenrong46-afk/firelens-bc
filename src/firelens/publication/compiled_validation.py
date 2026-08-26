"""Deterministic validation for compiler-produced high-risk publications."""

from __future__ import annotations

from collections.abc import Sequence

from firelens.contracts import (
    AskResponse,
    EvidencePacket,
    EvidenceStatus,
    PublicClaim,
    PublicEvidence,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    ValidationReport,
    render_claim_texts,
)
from firelens.derivation_policy import as_distance_derivation, derivation_policy_errors
from firelens.live_contracts import (
    COORDINATE_ORDER,
    DISTANCE_ALGORITHM,
    DISTANCE_UNIT,
    GEODESIC_CRS,
)
from firelens.proof_presentation import ProofCard
from firelens.publication.fallback import UNCOVERED_LIMITATION
from firelens.publication.records import get_versioned
from firelens.publication_contracts import PublicationKind
from firelens.safety_profile import (
    PublicationState,
    TruthClass,
    bind_proof_profile,
    verified_critical_metadata_present,
)


def atomic_quote_overlap(candidate_text: str, source_text: str) -> bool:
    candidate = " ".join(candidate_text.split()).casefold()
    source = " ".join(source_text.split()).casefold()
    if min(len(candidate), len(source)) < 24:
        return False
    return candidate in source or source in candidate


def packet_identity_errors(packet: EvidencePacket) -> list[str]:
    """Recheck identity at the publication boundary, including unchecked copies."""

    errors: list[str] = []
    evidence_ids = [item.evidence_id for item in packet.items]
    quote_ids = [item.quote_id for item in packet.quote_candidates]
    conflict_ids = [item.conflict_id for item in packet.conflicts]
    for label, values in (
        ("evidence", evidence_ids),
        ("quote", quote_ids),
        ("conflict", conflict_ids),
    ):
        if len(values) != len(set(values)):
            errors.append(f"packet contains duplicate {label} IDs")

    all_chunk_ids = [chunk_id for item in packet.items for chunk_id in item.chunk_ids]
    if len(all_chunk_ids) != len(set(all_chunk_ids)):
        errors.append("packet contains duplicate chunk IDs")

    evidence_by_id = {item.evidence_id: item for item in packet.items}
    quote_by_id = {item.quote_id: item for item in packet.quote_candidates}
    for item in packet.items:
        if not set(item.primary_chunk_ids).issubset(item.chunk_ids):
            errors.append(
                f"evidence {item.evidence_id} primary chunks are not contained in chunk IDs"
            )
    for candidate in packet.quote_candidates:
        linked_item = evidence_by_id.get(candidate.evidence_id)
        if linked_item is None:
            errors.append(
                f"quote {candidate.quote_id} references unknown evidence {candidate.evidence_id}"
            )
        elif candidate.text not in linked_item.primary_text:
            errors.append(f"quote {candidate.quote_id} is not exact primary source text")
    for conflict in packet.conflicts:
        if len(conflict.quote_ids) != len(set(conflict.quote_ids)):
            errors.append(f"conflict {conflict.conflict_id} repeats a quote ID")
            continue
        referenced = [quote_by_id.get(quote_id) for quote_id in conflict.quote_ids]
        if any(candidate is None for candidate in referenced):
            errors.append(f"conflict {conflict.conflict_id} references an unknown quote ID")
            continue
        documents = {
            evidence_by_id[candidate.evidence_id].document_sha256
            for candidate in referenced
            if candidate is not None and candidate.evidence_id in evidence_by_id
        }
        if len(documents) != len(conflict.quote_ids):
            errors.append(
                f"conflict {conflict.conflict_id} does not reference distinct documents"
            )
    return errors


def compiler_validation_report(
    errors: list[str],
    *,
    schema_valid: bool,
    citation_ids_valid: bool,
    quotes_exact: bool,
    claim_support_valid: bool,
    policy_valid: bool,
) -> ValidationReport:
    return ValidationReport(
        accepted=not errors,
        schema_valid=schema_valid,
        citation_ids_valid=citation_ids_valid,
        quotes_exact=quotes_exact,
        claim_support_valid=claim_support_valid,
        policy_valid=policy_valid,
        errors=errors,
    )


def validate_compiled_publication(
    *,
    packet: EvidencePacket | None,
    claims: Sequence[PublicClaim],
    evidence: Sequence[PublicEvidence],
    cards: Sequence[ProofCard],
    answer: str,
) -> ValidationReport:
    """Execute all deterministic invariants for a compiler-produced answer."""

    errors = packet_identity_errors(packet) if packet is not None else []
    schema_valid = not errors
    citation_ids_valid = True
    quotes_exact = True
    claim_support_valid = True
    policy_valid = True

    claim_ids = [claim.claim_id for claim in claims]
    evidence_ids = [item.evidence_id for item in evidence]
    card_ids = [card.claim_id for card in cards]
    if len(claim_ids) != len(set(claim_ids)):
        schema_valid = False
        errors.append("compiled claims do not have unique IDs")
    if len(evidence_ids) != len(set(evidence_ids)):
        schema_valid = False
        errors.append("compiled evidence does not have unique IDs")
    if len(card_ids) != len(set(card_ids)) or set(card_ids) != set(claim_ids):
        schema_valid = False
        errors.append("compiled proof cards do not map one-to-one to claims")

    evidence_by_id = {item.evidence_id: item for item in evidence}
    support_ids = {support.evidence_id for claim in claims for support in claim.supports}
    if support_ids != set(evidence_ids):
        citation_ids_valid = False
        errors.append("compiled evidence IDs do not equal the cited support IDs")

    card_by_id = {card.claim_id: card for card in cards}
    packet_candidates = (
        {(candidate.evidence_id, candidate.text) for candidate in packet.quote_candidates}
        if packet is not None
        else set()
    )
    packet_items = (
        {item.evidence_id: item for item in packet.items} if packet is not None else {}
    )

    for proof_card in cards:
        for error in _proof_card_policy_errors(proof_card):
            policy_valid = False
            errors.append(error)

    for claim in claims:
        card = card_by_id.get(claim.claim_id)
        if card is None or card.claim_text != claim.text:
            claim_support_valid = False
            errors.append(f"claim {claim.claim_id} does not equal its proof card")
        if claim.evidence_status != EvidenceStatus.VERIFIED_CORPUS or not claim.supports:
            claim_support_valid = False
            errors.append(f"claim {claim.claim_id} lacks verified support")
        for support in claim.supports:
            item = evidence_by_id.get(support.evidence_id)
            if item is None:
                citation_ids_valid = False
                errors.append(
                    f"claim {claim.claim_id} references unavailable evidence {support.evidence_id}"
                )
            elif support.quote not in item.primary_text:
                quotes_exact = False
                errors.append(f"claim {claim.claim_id} support is not exact source text")

        authority = getattr(claim, "publication", None)
        if authority is None:
            policy_valid = False
            errors.append(f"claim {claim.claim_id} has no publication authority")
            continue
        if authority.kind == PublicationKind.STRUCTURED_REVIEWED:
            if authority.typed_claim_id is None:
                policy_valid = False
                errors.append(f"claim {claim.claim_id} has no typed claim identity")
                continue
            try:
                current = get_versioned(authority.typed_claim_id)
            except ValueError:
                policy_valid = False
                errors.append(f"claim {claim.claim_id} references an unknown typed claim")
                continue
            expected_support = (f"S-{current.claim_id}", current.source_span_text[:500])
            actual_support = {
                (support.evidence_id, support.quote) for support in claim.supports
            }
            binding_matches = (
                current.available_for_structured_support
                and claim.text == current.canonical_text
                and authority.review_status == current.human_review_state
                and authority.source_revision_sha256 == current.source_revision_sha256
                and authority.source_span_sha256 == current.source_span_sha256
                and authority.renderer_id == current.renderer_id
                and actual_support == {expected_support}
            )
            if not binding_matches:
                policy_valid = False
                claim_support_valid = False
                errors.append(
                    f"claim {claim.claim_id} does not equal its current structured authority"
                )
            if packet is not None:
                source_bound = any(
                    candidate.evidence_id in packet_items
                    and set(packet_items[candidate.evidence_id].primary_chunk_ids).intersection(
                        current.source_span_ids
                    )
                    and atomic_quote_overlap(candidate.text, current.source_span_text)
                    for candidate in packet.quote_candidates
                )
                if not source_bound:
                    claim_support_valid = False
                    errors.append(
                        f"claim {claim.claim_id} is not bound to selected packet source text"
                    )
        elif authority.kind == PublicationKind.OFFICIAL_QUOTE_ONLY:
            actual_support = {
                (support.evidence_id, support.quote) for support in claim.supports
            }
            if (
                len(actual_support) != 1
                or not actual_support.issubset(packet_candidates)
                or claim.text not in {quote for _evidence_id, quote in actual_support}
                or authority.review_status != "extraction_only"
                or authority.support_provenance != "exact_official_quote"
            ):
                policy_valid = False
                claim_support_valid = False
                errors.append(
                    f"claim {claim.claim_id} is not an exact packet-bound quote-only claim"
                )
        else:
            policy_valid = False
            errors.append(
                f"claim {claim.claim_id} uses an unavailable compiled publication kind"
            )

    rendered = render_claim_texts(claims)
    if answer != rendered or rendered != render_claim_texts(tuple(claims)):
        claim_support_valid = False
        errors.append("compiled answer is not the deterministic claim rendering")

    return compiler_validation_report(
        errors,
        schema_valid=schema_valid,
        citation_ids_valid=citation_ids_valid,
        quotes_exact=quotes_exact,
        claim_support_valid=claim_support_valid,
        policy_valid=policy_valid,
    )


def _proof_card_policy_errors(card: ProofCard) -> list[str]:
    """Defense-in-depth profile and derivation checks, including model_construct cards."""

    errors: list[str] = []
    expected_truth, expected_state = bind_proof_profile(
        card.support_state, freshness=card.freshness
    )
    if card.truth_class != expected_truth or card.publication_state != expected_state:
        errors.append(
            f"claim {card.claim_id} proof card has non-deterministic profile metadata"
        )
    if expected_state == PublicationState.VERIFIED and not verified_critical_metadata_present(
        card
    ):
        errors.append(f"claim {card.claim_id} verified critical metadata is incomplete")
    if "km geodesic" in card.claim_text.casefold() and card.derivation is None:
        errors.append(f"claim {card.claim_id} conceals a distance derivation")
    if card.derivation is not None:
        derivation = as_distance_derivation(card.derivation)
        if derivation.truth_class is not TruthClass.DETERMINISTIC_DERIVATION:
            errors.append(f"claim {card.claim_id} derivation truth class is not deterministic")
        if (
            derivation.units != DISTANCE_UNIT
            or derivation.crs != GEODESIC_CRS
            or derivation.algorithm != DISTANCE_ALGORITHM
            or derivation.coordinate_order != COORDINATE_ORDER
        ):
            errors.append(f"claim {card.claim_id} emits unsupported distance units or CRS")
        errors.extend(
            derivation_policy_errors(
                claim_id=card.claim_id,
                claim_text=card.claim_text,
                freshness=card.freshness,
                derivation=derivation,
            )
        )
    return errors


def compiled_validation_handoff(trace_id: str, validation: ValidationReport) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=trace_id,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            "FireLens found official source material, but its compiled high-risk answer "
            "did not pass deterministic publication validation. Use the issuing authority "
            "for official wording."
        ),
        reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
        limitations=[UNCOVERED_LIMITATION],
        validation=validation,
    )


def unique_public_evidence(evidence: Sequence[PublicEvidence]) -> list[PublicEvidence]:
    seen: set[str] = set()
    unique: list[PublicEvidence] = []
    for item in evidence:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        unique.append(item)
    return unique
