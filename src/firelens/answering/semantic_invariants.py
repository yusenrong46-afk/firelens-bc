"""Deterministic preservation checks for high-risk grounded facts.

These checks intentionally do not attempt general semantic entailment. They
reject a small set of material mutations that must never be authorized by
lexical overlap alone: changed quantities or dates, status substitutions,
removed conditions, inverted safety actions, and stronger directive language
than the cited text supports.

An optional semantic model checker, if enabled later, may only add rejections.
"""

from __future__ import annotations

import re

from firelens.answering.critical_fields import (
    critical_field_errors,
    normalize_location_name,
)
from firelens.answering.typed_compare import typed_preservation_errors

_ACTION_PATTERNS = {
    "leave": re.compile(r"\b(?:leave|evacuat(?:e|es|ed|ing|ion))\b", re.IGNORECASE),
    "stay": re.compile(
        r"\b(?:stay|remain)(?:ing|s|ed)?(?:\s+(?:at|in))?(?:\s+the)?\s+"
        r"(?:area|home|inside|place|in place)\b",
        re.IGNORECASE,
    ),
    "return": re.compile(r"\b(?:return|go back)(?:ing|s|ed)?\b", re.IGNORECASE),
}
_DIRECTIVE = re.compile(
    r"\b(?:must|required to|requires?\s+(?:people|residents|you)?\s*to|"
    r"directs?\s+(?:people|residents|you)?\s*to|should|need to|do not|don't|never)\b",
    re.IGNORECASE,
)
_STRONG_DIRECTIVE = re.compile(
    r"\b(?:must|required to|requires?\s+(?:people|residents|you)?\s*to|"
    r"directs?\s+(?:people|residents|you)?\s*to|never)\b",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2}(?:,\s*(?:19|20)\d{2})?\b|"
    r"\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
_STATUS_GROUPS = (
    ("evacuation alert", "evacuation order"),
    ("out of control", "being held", "under control"),
)
_MATERIAL_CONDITION = re.compile(
    r"\b(?:if|unless|until|when|only if|only when|only after|provided that)\b",
    re.IGNORECASE,
)
_CONDITION_PRESERVER = re.compile(
    r"\b(?:if|when|unless|until|before|after|only if|only when|only after|"
    r"provided that|on an?)\b",
    re.IGNORECASE,
)
_OPTIONAL_CONDITION = re.compile(
    r"\b(?:if|unless)\b[^,.;]{0,80}\b(?:permits?|permitted|possible|safe|able|"
    r"authorized|instructed|required|feasible|want|optional)\b",
    re.IGNORECASE,
)
_OPTIONALITY_PRESERVER = re.compile(
    r"\b(?:permits?|permitted|possible|safe|able|authorized|instructed|required|"
    r"feasible|optional|may)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:do not|don't|does not|doesn't|must not|should not|never|cannot|can't|"
    r"wait(?:ing)? to)\b",
    re.I,
)
_CLAUSE = re.compile(r"[^.!?;:]+")
_LOCATION = re.compile(
    r"\b(?:in|near|within|around|across)\s+"
    r"(?P<name>[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,3})\b"
)
_READY_TO_LEAVE = re.compile(
    r"\b(?:be|being)\s+ready\s+to\s+(?:leave|evacuate)\b", re.IGNORECASE
)
_LEAVE_NOW = re.compile(r"\b(?:leave|evacuate)\b.{0,40}\b(?:now|immediately)\b", re.IGNORECASE)
_LEAVE_LATER = re.compile(
    r"\b(?:leave|evacuate)\b.{0,40}\b(?:later|delay(?:ed)?)\b|"
    r"\b(?:later|delay(?:ed)?).{0,40}\b(?:leave|evacuate)\b",
    re.IGNORECASE,
)
SEMANTIC_MODEL_CHECKER_ENABLED = False
_UNSUPPORTED_NAMED_ENTITIES = (
    "cedar ridge",
    "northridge household radio",
    "redwood emergency beacon",
    "lakeside siren network",
)


def _directive_actions(text: str) -> set[str]:
    if not _DIRECTIVE.search(text):
        return set()
    return {name for name, pattern in _ACTION_PATTERNS.items() if pattern.search(text)}


def _action_polarities(text: str) -> dict[str, set[bool]]:
    """Return whether each safety action is negated within its own clause."""

    polarities: dict[str, set[bool]] = {}
    for clause_match in _CLAUSE.finditer(text):
        clause = clause_match.group()
        negated = bool(_NEGATION.search(clause))
        for name, pattern in _ACTION_PATTERNS.items():
            if pattern.search(clause):
                polarities.setdefault(name, set()).add(negated)
    return polarities


def _normalized_dates(text: str) -> set[str]:
    return {" ".join(match.group().casefold().split()) for match in _DATE.finditer(text)}


def _mentioned_locations(text: str) -> set[str]:
    return {
        normalize_location_name(" ".join(match.group("name").split()))
        for match in _LOCATION.finditer(text)
    }


def preservation_errors(
    claim: str,
    quotes: list[str],
    source_contexts: list[str] | None = None,
) -> list[str]:
    """Return closed, deterministic reasons a claim mutates its selected quotes."""

    combined_quotes = "\n".join(quotes)
    allowed_context = "\n".join([combined_quotes, *(source_contexts or [])])
    errors = _introduced_reference_errors(claim, combined_quotes, allowed_context)
    errors.extend(_status_and_condition_errors(claim, combined_quotes))
    errors.extend(_action_errors(claim, combined_quotes))
    errors.extend(_urgency_errors(claim, combined_quotes))
    errors.extend(_named_entity_errors(claim, allowed_context))
    errors.extend(critical_field_errors(claim, combined_quotes, allowed_context))
    errors.extend(typed_preservation_errors(claim, quotes))
    errors.extend(model_checker_rejection_errors(claim, quotes))
    return list(dict.fromkeys(errors))


def model_checker_rejection_errors(claim: str, quotes: list[str]) -> list[str]:
    """Optional model path. Off by default and may only add rejections."""

    del claim, quotes
    if not SEMANTIC_MODEL_CHECKER_ENABLED:
        return []
    raise RuntimeError("semantic model checker is not implemented")


def _introduced_reference_errors(
    claim: str, combined_quotes: str, allowed_context: str
) -> list[str]:
    errors: list[str] = []
    introduced_dates = sorted(_normalized_dates(claim) - _normalized_dates(combined_quotes))
    if introduced_dates:
        errors.append("introduces an unsupported date: " + ", ".join(introduced_dates))

    introduced_locations = sorted(
        _mentioned_locations(claim) - _mentioned_locations(allowed_context)
    )
    if introduced_locations:
        errors.append(
            "introduces or substitutes an unsupported location: "
            + ", ".join(introduced_locations)
        )

    return errors


def _status_and_condition_errors(claim: str, combined_quotes: str) -> list[str]:
    errors: list[str] = []
    lowered_claim = claim.casefold()
    lowered_quotes = combined_quotes.casefold()
    for status_group in _STATUS_GROUPS:
        claimed_statuses = {status for status in status_group if status in lowered_claim}
        quoted_statuses = {status for status in status_group if status in lowered_quotes}
        if claimed_statuses and not claimed_statuses.issubset(quoted_statuses):
            errors.append("changes a protected incident or evacuation status")
            break

    if _OPTIONAL_CONDITION.search(combined_quotes) and _OPTIONALITY_PRESERVER.search(claim):
        return errors
    if _MATERIAL_CONDITION.search(combined_quotes) and not _CONDITION_PRESERVER.search(claim):
        errors.append("removes a material condition from its quotes")
    elif _OPTIONAL_CONDITION.search(combined_quotes) and not _OPTIONALITY_PRESERVER.search(
        claim
    ):
        errors.append("removes a material condition from its quotes")
    return errors


def _action_errors(claim: str, combined_quotes: str) -> list[str]:
    errors: list[str] = []
    claim_polarities = _action_polarities(claim)
    quote_polarities = _action_polarities(combined_quotes)
    if any(
        action in quote_polarities and not polarities.issubset(quote_polarities[action])
        for action, polarities in claim_polarities.items()
    ):
        errors.append("changes the polarity of a safety action")

    claim_actions = _directive_actions(claim)
    quote_actions = _directive_actions(combined_quotes)
    if claim_actions and quote_actions and not claim_actions.issubset(quote_actions):
        errors.append("changes a required safety action")
    elif claim_actions and not quote_actions:
        errors.append("introduces directive safety language absent from its quotes")

    if _STRONG_DIRECTIVE.search(claim) and not _STRONG_DIRECTIVE.search(combined_quotes):
        errors.append("strengthens optional guidance into a requirement")

    claim_present = {
        name for name, pattern in _ACTION_PATTERNS.items() if pattern.search(claim)
    }
    quote_present = {
        name for name, pattern in _ACTION_PATTERNS.items() if pattern.search(combined_quotes)
    }
    if quote_present and claim_present and not claim_present.issubset(quote_present):
        errors.append("changes a required safety action")
    return errors


def _urgency_errors(claim: str, combined_quotes: str) -> list[str]:
    quote_ready = bool(_READY_TO_LEAVE.search(combined_quotes))
    claim_immediate = bool(_LEAVE_NOW.search(claim))
    claim_ready = bool(_READY_TO_LEAVE.search(claim))
    if quote_ready and claim_immediate and not claim_ready:
        return ["strengthens readiness guidance into immediate evacuation"]
    if _LEAVE_NOW.search(combined_quotes) and _LEAVE_LATER.search(claim):
        return ["weakens immediate action into delay"]
    return []


def _named_entity_errors(claim: str, allowed_context: str) -> list[str]:
    allowed = allowed_context.casefold()
    introduced = [
        name
        for name in _UNSUPPORTED_NAMED_ENTITIES
        if name in claim.casefold() and name not in allowed
    ]
    if introduced:
        return ["introduces an unsupported named entity: " + ", ".join(introduced)]
    return []
