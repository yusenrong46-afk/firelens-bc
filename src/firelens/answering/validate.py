"""Deterministic traceability and policy validation for generated drafts."""

from __future__ import annotations

import re

from firelens.answering.risk_policy import RiskTier
from firelens.answering.semantic_invariants import preservation_errors
from firelens.answering.typed_snapshot import classify_text
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    MAX_GROUNDED_ANSWER_CHARS,
    BackgroundDraft,
    DraftProposalClaim,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    GroundedDraft,
    ValidationReport,
    render_claim_texts,
)
from firelens.retrieval.bm25 import tokenize

_CLAIM_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "with",
        "you",
        "your",
    }
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
    r"\b(?:is|are)\s+(?:completely\s+|generally\s+)?safe\b",
    r"\b(?:you|we|people|residents?|famil(?:y|ies)|(?:your|our)\s+family|"
    r"households?|visitors?|(?:the\s+)?community)\s+"
    r"(?:can|could|may|should|must|need to|ought to)\s+(?:safely\s+)?"
    r"(?:stay|leave|evacuate|return|go back)\b",
    r"\bit\s+is\s+(?:okay|safe)\s+to\s+(?:stay|leave|evacuate|return|go back)\b",
    r"\b(?:drive|take|use|follow)\s+(?:the\s+)?(?:highway|road|route)\s*"
    r"[a-z0-9-]*\b.{0,40}\b(?:evacuate|escape|leave)\b",
    r"\b(?:highway|road|route)\s*[a-z0-9-]*\b.{0,30}\b(?:is|would be)\s+"
    r"(?:the\s+)?(?:best|safest|recommended|preferred)\s+(?:route|way|option)?\b",
    r"\b(?:this|the)\s+(?:mapped\s+)?perimeter\b.{0,80}\b(?:current\s+|active\s+)?flame\s+front\b",
    r"\b(?:current\s+|active\s+)?flame\s+front\b.{0,80}\b(?:this|the)\s+(?:mapped\s+)?perimeter\b",
    r"\b(?:mark|set|promote|publish)\s+(?:this|the(?:se)?)\s+(?:claim|answer|record)s?\s+(?:as|to)\s+verified\b",
    r"\bpublication state\s+(?:is|to|=)\s+verified\b",
    r"\b(?:reveal|print|output|return)\s+(?:the\s+)?(?:api[_-]?key|openrouter[_-]?api[_-]?key|system prompt)\b",
    r"\bignore (?:the )?(?:source allowlist|freshness|geometry) (?:rules?|validation)\b",
    r"\binvoke unauthorized tools?\b",
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
    r"\b(?:weather|wind(?: speed| direction)?|smoke forecast|forecast|aqhi)\b.{0,80}"
    r"\b(?:right now|currently|latest|today|tonight|at the moment)\b",
    r"\b(?:right now|currently|latest|today|tonight|at the moment)\b.{0,80}"
    r"\b(?:weather|wind(?: speed| direction)?|smoke forecast|forecast|aqhi)\b",
    r"\bweather\s+(?:in|near|for)\s+.{1,50}\s+(?:is|will be)\b",
    r"\bwind\s+(?:speed|direction)\s+(?:in|near|for)\s+.{1,50}\s+is\b",
    r"\baqhi\s+(?:in|near|for)\s+.{1,50}\s+is\s+\d+\b",
    r"\b(?:firefighting\s+)?(?:aircraft|airtankers?|air tankers?|helicopters?)\b"
    r".{0,80}\b(?:right now|currently|today|located|flying|deployed|operating)\b",
    r"\b(?:fire|wildfire)\b.{0,80}"
    r"\b(?:will|is expected to|is forecast to|is predicted to)\b.{0,80}"
    r"\b(?:reach|arrive|spread|be contained|be controlled|go out)\b",
)

_SAFE_NON_AUTHORIZATION = (
    r"\b(?:does not|doesn't)\s+(?:mean|tell you|indicate|say)\b.{0,50}\byou\s+(?:should|must|need to|ought to)\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:is|does)\s+not\s+(?:itself\s+)?(?:an?\s+)?evacuation instruction\b",
    r"\b(?:does not|doesn't)\s+(?:mean|indicate|show|establish)\b.{0,80}"
    r"\b(?:the\s+)?(?:area|community|place|people|residents?)\s+"
    r"(?:is|are)\s+safe\b",
)

_SAFE_CONDITIONAL_STATUS = (
    r"\b(?:if|when)\s+(?:you|someone|a household|a community)\s+(?:is|are)\s+under\s+(?:an?\s+)?evacuation\s+(?:alert|order)\b",
    # A generic glossary definition is not an assertion about an actual fire.
    # Keep this exemption narrow: indefinite subjects plus an explicit condition.
    r"\b(?:a|any)\s+(?:wildfire|fire)\s+(?:is|remains)\s+(?:active|burning|out of control|being held)\s+(?:if|when)\b",
    r"\b(?:an?\s+)?evacuation order\s+(?:this\s+)?(?:means|requires|directs|tells (?:people|residents|you) to)\b.{0,80}\b(?:leave|evacuate) immediately\b",
    r"\bwhen\s+(?:an?\s+)?evacuation order is issued\b.{0,80}\b(?:leave|evacuate) immediately\b",
    r"\bevacuation order\s*(?:means|[=:—-])\s*(?:you\s+)?(?:must\s+)?(?:leave|evacuate)(?:\s+(?:now|immediately))?\b",
    r"\b(?:if|when)\s+(?:an?\s+)?evacuation order\b.{0,100}"
    r"\b(?:people|residents?|famil(?:y|ies)|households?|visitors?)\s+"
    r"(?:should|must|need to)\s+(?:leave|evacuate)\b",
)


def _policy_text(text: str) -> str:
    """Remove narrow negated safety statements before advice-pattern checks."""

    for pattern in _SAFE_NON_AUTHORIZATION:
        text = re.sub(pattern, " ", text)
    for pattern in _SAFE_CONDITIONAL_STATUS:
        text = re.sub(pattern, " ", text)
    return text


def _claim_has_direct_lexical_support(claim: str, quotes: list[str]) -> bool:
    """Reject a citation attached to a materially unrelated generated claim.

    This is a deterministic support floor, not a semantic-entailment score.
    """

    normalized_claim = " ".join(claim.casefold().split())
    normalized_quotes = [" ".join(quote.casefold().split()) for quote in quotes]
    if any(
        normalized_claim in quote or quote in normalized_claim for quote in normalized_quotes
    ):
        return True
    claim_tokens = {
        token for token in tokenize(claim) if token not in _CLAIM_STOPWORDS and len(token) > 2
    }
    quote_tokens = {
        token
        for quote in quotes
        for token in tokenize(quote)
        if token not in _CLAIM_STOPWORDS and len(token) > 2
    }
    overlap = claim_tokens & quote_tokens
    return len(overlap) >= 2 and len(overlap) / max(1, len(claim_tokens)) >= 0.25


def _enumerated_evidence_sections(packet: EvidencePacket) -> dict[str, str]:
    """Identify a retrieved multi-section set that an enumerative answer must cover."""

    question = packet.question.casefold()
    if not re.search(r"\b(?:stages|types|categories|levels|zones|steps)\b", question):
        return {}
    if not re.search(r"\b(?:what|which|mean|explain|describe|list|summari[sz]e)\b", question):
        return {}
    by_source: dict[str, dict[str, str]] = {}
    for item in packet.items:
        first_line = item.primary_text.splitlines()[0].strip()
        words = first_line.split()
        if not 1 <= len(words) <= 6 or len(first_line) > 60:
            continue
        if first_line.endswith((".", "?", "!", ":", ";")):
            continue
        by_source.setdefault(item.source_id, {})[item.evidence_id] = first_line
    eligible = [sections for sections in by_source.values() if len(sections) >= 3]
    return max(eligible, key=len) if eligible else {}


def validate_draft(draft: GroundedDraft, packet: EvidencePacket) -> ValidationReport:
    errors: list[str] = []
    evidence = {item.evidence_id: item for item in packet.items}
    candidates = {candidate.quote_id: candidate for candidate in packet.quote_candidates}
    citation_ids_valid = True
    quotes_exact = True
    claim_support_valid = True
    policy_valid = True
    cited_evidence_ids: set[str] = set()

    is_guidance = draft.answer_type == "grounded"
    if is_guidance and not draft.claims:
        errors.append("guidance answer has no factual claims")
    if is_guidance:
        rendered_answer = render_claim_texts(draft.claims)
        if len(rendered_answer) > MAX_GROUNDED_ANSWER_CHARS:
            errors.append("rendered guidance answer is too long")
    for claim_number, claim in enumerate(draft.claims, start=1):
        claim_result = _validate_claim(claim, claim_number, candidates, evidence)
        citation_ids_valid &= claim_result[0]
        quotes_exact &= claim_result[1]
        claim_support_valid &= claim_result[2]
        cited_evidence_ids.update(claim_result[3])
        errors.extend(claim_result[4])

    enumerated_sections = _enumerated_evidence_sections(packet)
    missing_sections = [
        heading
        for evidence_id, heading in enumerated_sections.items()
        if evidence_id not in cited_evidence_ids
    ]
    if missing_sections:
        claim_support_valid = False
        errors.append(
            "enumerated answer omits retrieved evidence sections: "
            + "; ".join(missing_sections)
        )

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
        claim_support_valid=claim_support_valid,
        policy_valid=policy_valid,
        errors=errors,
    )


def _validate_claim(
    claim: DraftProposalClaim,
    claim_number: int,
    candidates: dict[str, EvidenceQuoteCandidate],
    evidence: dict[str, EvidenceSpan],
) -> tuple[bool, bool, bool, set[str], list[str]]:
    citation_valid = True
    quotes_exact = len(claim.evidence_quote_ids) == len(set(claim.evidence_quote_ids))
    errors = [] if quotes_exact else [f"claim {claim_number} repeats an evidence quote ID"]
    selected = []
    contexts: list[str] = []
    cited_ids: set[str] = set()
    for quote_id in claim.evidence_quote_ids:
        candidate = candidates.get(quote_id)
        item = evidence.get(candidate.evidence_id) if candidate else None
        if candidate is None or item is None or candidate.text not in item.primary_text:
            citation_valid = False
            quotes_exact = False
            label = (
                f"unknown quote ID {quote_id}"
                if candidate is None
                else f"quote {quote_id} is not exact"
            )
            errors.append(
                f"claim {claim_number} cites {label}"
                if candidate is None
                else f"claim {claim_number} {label}"
            )
            continue
        selected.append(candidate)
        contexts.append(
            " ".join(
                str(value)
                for value in (
                    item.title,
                    item.publisher,
                    item.canonical_url,
                    item.locator,
                    item.section_title,
                )
                if value
            )
        )
        cited_ids.add(candidate.evidence_id)
    support_valid, support_errors = _claim_support_errors(
        claim, claim_number, selected, contexts
    )
    errors.extend(support_errors)
    return citation_valid and bool(selected), quotes_exact, support_valid, cited_ids, errors


def _claim_support_errors(
    claim: DraftProposalClaim,
    claim_number: int,
    selected: list[EvidenceQuoteCandidate],
    contexts: list[str],
) -> tuple[bool, list[str]]:
    quotes = [candidate.text for candidate in selected]
    if not quotes:
        return True, [f"claim {claim_number} has no valid evidence quote ID"]
    if not _claim_has_direct_lexical_support(claim.text, quotes):
        return False, [
            f"claim {claim_number} lacks direct lexical support in its selected quotes"
        ]
    errors = preservation_errors(claim.text, quotes, contexts)
    return not errors, [f"claim {claim_number} {message}" for message in errors]


def salvage_valid_grounded_claims(
    draft: GroundedDraft, packet: EvidencePacket
) -> tuple[GroundedDraft, ValidationReport] | None:
    """Keep only independently valid claims from a rejected grounded draft.

    This never repairs text, quote IDs, or policy violations. It can only remove
    claims and then re-run the full deterministic validator.
    """

    accepted_claims = []
    quote_texts = {candidate.text.strip() for candidate in packet.quote_candidates}
    for claim in draft.claims:
        if (
            classify_text(claim.text) in {RiskTier.A, RiskTier.B}
            and claim.text.strip() not in quote_texts
        ):
            continue
        single = draft.model_copy(update={"claims": [claim]})
        if validate_draft(single, packet).accepted:
            accepted_claims.append(claim)
    if not accepted_claims or len(accepted_claims) == len(draft.claims):
        return None
    salvaged = draft.model_copy(update={"claims": accepted_claims})
    validation = validate_draft(salvaged, packet)
    return (salvaged, validation) if validation.accepted else None


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
