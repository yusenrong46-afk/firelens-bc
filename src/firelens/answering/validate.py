"""Deterministic traceability and policy validation for generated drafts."""

from __future__ import annotations

import re

from firelens.contracts import (
    BACKGROUND_LIMITATION,
    BackgroundDraft,
    EvidencePacket,
    GroundedDraft,
    ValidationReport,
)

_FORBIDDEN = (
    r"\bguarantee(?:d|s)?\s+(?:your\s+)?safety\b",
    r"\bguarantee(?:d|s)?\s+survival\b",
    r"\byou are safe\b",
    r"\bsafest evacuation route\b",
    r"\bignore (?:all |any )?(?:previous|prior) instructions\b",
    r"\b(?:i recommend|i advise|my advice is)\b.{0,60}\b(?:stay|leave|evacuate|return)\b",
    r"\byou (?:should|must|need to|ought to)\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:stay|leave|evacuate|return)\s+(?:now|immediately)\b",
    r"\b(?:take|use)\s+(?:highway|road|route)\b",
    r"\byou (?:have|are experiencing)\s+(?:smoke inhalation|carbon monoxide poisoning|asthma)\b",
    r"\b(?:take|use|stop)\s+(?:your|an? extra|[0-9]+\s*(?:mg|mcg|ml))\b.{0,40}\b(?:medicine|medication|dose|inhaler)\b",
    r"\bif i were you\b.{0,60}\bi would\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:staying|leaving|evacuating|returning)\s+would be\s+(?:the\s+)?(?:safest|best|right)\b",
)

_LIVE_CLAIMS = (
    r"\bcurrently (?:active|burning|in effect)\b",
    r"\bthere (?:is|are) (?:no )?(?:active )?(?:fire|wildfire)s?\b",
    r"\bno evacuation (?:alert|order) is in effect\b",
    r"\b(?:a |the )?(?:wildfire|fire)\s+(?:is|remains)\s+(?:active|burning|out of control|being held)\b",
    r"\b(?:an? )?evacuation (?:alert|order)\s+(?:is|remains)\s+(?:active|in effect)\b",
    r"\b(?:road|highway)\b.{0,30}\b(?:is|remains)\s+(?:closed|open|blocked)\b",
    r"\bair quality\s+(?:is|remains)\s+(?:poor|hazardous|unhealthy|good)\b",
    r"\b(?:wildfire|fire|evacuation|alert|order|smoke|air quality|road|highway)\b.{0,80}\b(?:right now|currently|latest|today|tonight|at the moment)\b",
    r"\b(?:as of\s+)?(?:right now|currently|latest|today|tonight|at the moment)\b.{0,80}\b(?:wildfire|fire|evacuation|alert|order|smoke|air quality|road|highway)\b",
    r"\b(?:is|are)\s+under\s+(?:an?\s+)?evacuation\s+(?:alert|order)\b",
)

_SAFE_NON_AUTHORIZATION = (
    r"\b(?:does not|doesn't)\s+(?:mean|tell you|indicate|say)\b.{0,50}\byou\s+(?:should|must|need to|ought to)\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:is|does)\s+not\s+(?:itself\s+)?(?:an?\s+)?evacuation instruction\b",
)

_SAFE_CONDITIONAL_STATUS = (
    r"\b(?:if|when)\s+(?:you|someone|a household|a community)\s+(?:is|are)\s+under\s+(?:an?\s+)?evacuation\s+(?:alert|order)\b",
    # A generic glossary definition is not an assertion about an actual fire.
    # Keep this exemption narrow: indefinite subjects plus an explicit condition.
    r"\b(?:a|any)\s+(?:wildfire|fire)\s+(?:is|remains)\s+(?:active|burning|out of control|being held)\s+(?:if|when)\b",
    r"\b(?:an?\s+)?evacuation order\s+(?:means|requires|directs|tells (?:people|residents|you) to)\b.{0,80}\b(?:leave|evacuate) immediately\b",
    r"\bwhen\s+(?:an?\s+)?evacuation order is issued\b.{0,80}\b(?:leave|evacuate) immediately\b",
)


def _policy_text(text: str) -> str:
    """Remove narrow negated safety statements before advice-pattern checks."""

    for pattern in _SAFE_NON_AUTHORIZATION:
        text = re.sub(pattern, " ", text)
    for pattern in _SAFE_CONDITIONAL_STATUS:
        text = re.sub(pattern, " ", text)
    return text


def validate_draft(draft: GroundedDraft, packet: EvidencePacket) -> ValidationReport:
    errors: list[str] = []
    evidence = {item.evidence_id: item for item in packet.items}
    candidates = {candidate.quote_id: candidate for candidate in packet.quote_candidates}
    citation_ids_valid = True
    quotes_exact = True
    policy_valid = True

    is_guidance = draft.answer_type == "grounded"
    if is_guidance and not draft.claims:
        errors.append("guidance answer has no factual claims")
    if is_guidance:
        rendered_answer = " ".join(claim.text.strip() for claim in draft.claims)
        if len(rendered_answer) > 2_500:
            errors.append("rendered guidance answer is too long")
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

    combined = "\n".join(claim.text for claim in draft.claims)
    lowered = combined.lower()
    policy_text = _policy_text(lowered)
    forbidden_rule = next(
        (
            rule_number
            for rule_number, pattern in enumerate(_FORBIDDEN, start=1)
            if re.search(pattern, policy_text)
        ),
        None,
    )
    if forbidden_rule is not None:
        policy_valid = False
        errors.append(f"answer violates deterministic policy rule P{forbidden_rule}")
    if any(re.search(pattern, policy_text) for pattern in _LIVE_CLAIMS):
        policy_valid = False
        errors.append("answer makes a live claim from static evidence")
    return ValidationReport(
        accepted=not errors,
        citation_ids_valid=citation_ids_valid,
        quotes_exact=quotes_exact,
        policy_valid=policy_valid,
        errors=errors,
    )


_BACKGROUND_FORBIDDEN = (
    *_FORBIDDEN,
    *_LIVE_CLAIMS,
    r"\b(?:take|use|stop)\s+.{0,40}\b(?:medicine|medication|dose|inhaler)\b",
    r"\b(?:you|your family)\s+should\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:take|use)\s+(?:highway|road|route)\b",
    r"https?://",
    r"\b(?:official|verified)\s+(?:source|guidance|evidence|recommendation)\b",
    r"\baccording to\b",
    r"\b(?:bc wildfire service|preparedbc|firesmart bc|bccdc|government of british columbia)\s+(?:says|advises|recommends)\b",
)


def validate_background_draft(draft: BackgroundDraft) -> ValidationReport:
    """Enforce the visible separation between background and verified evidence."""

    errors: list[str] = []
    policy_valid = True
    if BACKGROUND_LIMITATION not in draft.limitations:
        policy_valid = False
        errors.append("background answer is missing its required limitation")
    combined = _policy_text("\n".join(claim.text for claim in draft.claims).lower())
    if any(re.search(pattern, combined) for pattern in _BACKGROUND_FORBIDDEN):
        policy_valid = False
        errors.append("background answer contains prohibited content")
    return ValidationReport(
        accepted=not errors,
        citation_ids_valid=True,
        quotes_exact=True,
        policy_valid=policy_valid,
        errors=errors,
    )
