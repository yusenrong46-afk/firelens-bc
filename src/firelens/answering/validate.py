"""Deterministic traceability and policy validation for generated drafts."""

from __future__ import annotations

import re

from firelens.contracts import DraftAnswer, EvidencePacket, ValidationReport

_FORBIDDEN = (
    r"\bguarantee(?:d|s)?\s+(?:your\s+)?safety\b",
    r"\bguarantee(?:d|s)?\s+survival\b",
    r"\byou are safe\b",
    r"\bsafest evacuation route\b",
    r"\bignore (?:all |any )?(?:previous|prior) instructions\b",
)

_LIVE_CLAIMS = (
    r"\bcurrently (?:active|burning|in effect)\b",
    r"\bthere (?:is|are) (?:no )?(?:active )?(?:fire|wildfire)s?\b",
    r"\bno evacuation (?:alert|order) is in effect\b",
)


def validate_draft(draft: DraftAnswer, packet: EvidencePacket) -> ValidationReport:
    errors: list[str] = []
    evidence = {item.evidence_id: item for item in packet.items}
    candidates = {candidate.quote_id: candidate for candidate in packet.quote_candidates}
    citation_ids_valid = True
    quotes_exact = True
    policy_valid = True

    if draft.answer_type == "guidance" and not draft.claims:
        errors.append("guidance answer has no factual claims")
    if draft.answer_type == "guidance" and not draft.limitations:
        errors.append("guidance answer is missing its static-data limitation")
    if draft.answer_type == "guidance":
        rendered_answer = " ".join(claim.text.strip() for claim in draft.claims)
        if len(rendered_answer) > 2_500:
            errors.append("rendered guidance answer is too long")
    for limitation in packet.limitations:
        if draft.answer_type == "guidance" and limitation not in draft.limitations:
            policy_valid = False
            errors.append("guidance answer is missing a required evidence limitation")

    for claim_number, claim in enumerate(draft.claims, start=1):
        if len(claim.evidence_quote_ids) != len(set(claim.evidence_quote_ids)):
            quotes_exact = False
            errors.append(f"claim {claim_number} repeats an evidence quote ID")
        selected_candidates = []
        for quote_id in claim.evidence_quote_ids:
            candidate = candidates.get(quote_id)
            if candidate is None:
                citation_ids_valid = False
                quotes_exact = False
                errors.append(f"claim {claim_number} cites unknown quote ID {quote_id}")
                continue
            item = evidence.get(candidate.evidence_id)
            if item is None or candidate.text not in item.primary_text:
                citation_ids_valid = False
                quotes_exact = False
                errors.append(f"claim {claim_number} quote {quote_id} is not exact")
                continue
            selected_candidates.append(candidate)
        if not selected_candidates:
            citation_ids_valid = False
            errors.append(f"claim {claim_number} has no valid evidence quote ID")

    combined = "\n".join([draft.answer, *(claim.text for claim in draft.claims)])
    lowered = combined.lower()
    if any(re.search(pattern, lowered) for pattern in _FORBIDDEN):
        policy_valid = False
        errors.append("answer contains prohibited or prompt-injection language")
    if any(re.search(pattern, lowered) for pattern in _LIVE_CLAIMS):
        policy_valid = False
        errors.append("answer makes a live claim from static evidence")
    if draft.requires_live_verification and not draft.limitations:
        policy_valid = False
        errors.append("live verification flag requires an explicit limitation")

    return ValidationReport(
        accepted=not errors,
        citation_ids_valid=citation_ids_valid,
        quotes_exact=quotes_exact,
        policy_valid=policy_valid,
        errors=errors,
    )
