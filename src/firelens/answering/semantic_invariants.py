"""Deterministic preservation checks for high-risk grounded facts.

These checks intentionally do not attempt general semantic entailment. They
reject a small set of material mutations that must never be authorized by
lexical overlap alone: changed quantities or dates, status substitutions,
removed conditions, inverted safety actions, and stronger directive language
than the cited text supports.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_UNIT_ALIASES = {
    "m": "metre",
    "meter": "metre",
    "meters": "metre",
    "metre": "metre",
    "metres": "metre",
    "cm": "centimetre",
    "centimeter": "centimetre",
    "centimeters": "centimetre",
    "centimetre": "centimetre",
    "centimetres": "centimetre",
    "km": "kilometre",
    "kilometer": "kilometre",
    "kilometers": "kilometre",
    "kilometre": "kilometre",
    "kilometres": "kilometre",
    "minute": "minute",
    "minutes": "minute",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "days": "day",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "l": "litre",
    "ml": "millilitre",
    "millilitre": "millilitre",
    "millilitres": "millilitre",
    "mg": "milligram",
    "milligram": "milligram",
    "milligrams": "milligram",
    "%": "percent",
    "percent": "percent",
}
_QUANTITY = re.compile(
    r"(?<![\w.])(?P<number>\d+(?:[,.]\d+)*)\s*"
    r"(?P<unit>%|m|cm|km|ml|mg|l|met(?:er|re)s?|centimet(?:er|re)s?|"
    r"kilomet(?:er|re)s?|minutes?|hours?|days?|lit(?:er|re)s?|"
    r"millilitres?|milligrams?|percent)\b",
    re.IGNORECASE,
)

_ACTION_PATTERNS = {
    "leave": re.compile(r"\b(?:leave|evacuat(?:e|es|ed|ing|ion))\b", re.IGNORECASE),
    "stay": re.compile(
        r"\b(?:stay|remain)(?:ing|s|ed)?(?:\s+(?:at|in))?\s+(?:home|inside|in place)\b",
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
    r"\b(?:if|unless|until|only if|only when|only after|provided that)\b",
    re.IGNORECASE,
)
_CONDITION_PRESERVER = re.compile(
    r"\b(?:if|when|unless|until|before|after|only if|only when|only after|"
    r"provided that)\b",
    re.IGNORECASE,
)
_OPTIONAL_CONDITION = re.compile(
    r"\b(?:if|unless)\b[^,.;]{0,80}\b(?:permits?|permitted|possible|safe|able|"
    r"authorized|instructed|required|feasible)\b",
    re.IGNORECASE,
)
_OPTIONALITY_PRESERVER = re.compile(
    r"\b(?:permits?|permitted|possible|safe|able|authorized|instructed|required|"
    r"feasible)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(?:do not|don't|must not|should not|never|cannot|can't)\b", re.I)
_CLAUSE = re.compile(r"[^.!?;:]+")
_AUTHORITY_ALIASES = {
    "bc centre for disease control": ("bc centre for disease control", "bccdc"),
    "bc wildfire service": ("bc wildfire service", "bcws"),
    "emergencyinfobc": ("emergencyinfobc",),
    "firesmart bc": ("firesmart bc",),
    "firesmart canada": ("firesmart canada",),
    "government of british columbia": (
        "government of british columbia",
        "province of british columbia",
    ),
    "preparedbc": ("preparedbc",),
}
_LOCATION = re.compile(
    r"\b(?:in|near|within|around|across)\s+"
    r"(?P<name>[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,3})\b"
)


def _normalized_quantities(text: str) -> set[tuple[str, str]]:
    quantities: set[tuple[str, str]] = set()
    for match in _QUANTITY.finditer(text):
        raw_number = match.group("number").replace(",", "")
        try:
            number = format(Decimal(raw_number).normalize(), "f")
        except InvalidOperation:
            continue
        quantities.add((number, _UNIT_ALIASES[match.group("unit").casefold()]))
    return quantities


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


def _mentioned_authorities(text: str) -> set[str]:
    lowered = text.casefold()
    return {
        authority
        for authority, aliases in _AUTHORITY_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered) for alias in aliases)
    }


def _mentioned_locations(text: str) -> set[str]:
    return {
        " ".join(match.group("name").casefold().split()) for match in _LOCATION.finditer(text)
    }


def preservation_errors(
    claim: str,
    quotes: list[str],
    source_contexts: list[str] | None = None,
) -> list[str]:
    """Return closed, deterministic reasons a claim mutates its selected quotes."""

    combined_quotes = "\n".join(quotes)
    allowed_context = "\n".join([combined_quotes, *(source_contexts or [])])
    errors: list[str] = []

    claim_quantities = _normalized_quantities(claim)
    quote_quantities = _normalized_quantities(combined_quotes)
    introduced_quantities = sorted(claim_quantities - quote_quantities)
    if introduced_quantities:
        rendered = ", ".join(f"{number} {unit}" for number, unit in introduced_quantities)
        errors.append(f"introduces an unsupported quantity or unit: {rendered}")

    introduced_dates = sorted(_normalized_dates(claim) - _normalized_dates(combined_quotes))
    if introduced_dates:
        errors.append("introduces an unsupported date: " + ", ".join(introduced_dates))

    introduced_authorities = sorted(
        _mentioned_authorities(claim) - _mentioned_authorities(allowed_context)
    )
    if introduced_authorities:
        errors.append(
            "introduces or substitutes an unsupported authority: "
            + ", ".join(introduced_authorities)
        )

    introduced_locations = sorted(
        _mentioned_locations(claim) - _mentioned_locations(allowed_context)
    )
    if introduced_locations:
        errors.append(
            "introduces or substitutes an unsupported location: "
            + ", ".join(introduced_locations)
        )

    lowered_claim = claim.casefold()
    lowered_quotes = combined_quotes.casefold()
    for status_group in _STATUS_GROUPS:
        claimed_statuses = {status for status in status_group if status in lowered_claim}
        quoted_statuses = {status for status in status_group if status in lowered_quotes}
        if claimed_statuses and not claimed_statuses.issubset(quoted_statuses):
            errors.append("changes a protected incident or evacuation status")
            break

    if _MATERIAL_CONDITION.search(combined_quotes) and not _CONDITION_PRESERVER.search(claim):
        errors.append("removes a material condition from its quotes")
    elif _OPTIONAL_CONDITION.search(combined_quotes) and not _OPTIONALITY_PRESERVER.search(
        claim
    ):
        errors.append("removes a material condition from its quotes")

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

    return errors
