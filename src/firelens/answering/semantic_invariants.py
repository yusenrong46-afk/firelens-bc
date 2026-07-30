"""Deterministic preservation checks for high-risk grounded facts.

These checks intentionally do not attempt general semantic entailment. They
reject a small set of material mutations that must never be authorized by
lexical overlap alone: changed quantities, inverted evacuation actions, and
stronger directive language than the cited text supports.
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


def preservation_errors(claim: str, quotes: list[str]) -> list[str]:
    """Return closed, deterministic reasons a claim mutates its selected quotes."""

    combined_quotes = "\n".join(quotes)
    errors: list[str] = []

    claim_quantities = _normalized_quantities(claim)
    quote_quantities = _normalized_quantities(combined_quotes)
    introduced_quantities = sorted(claim_quantities - quote_quantities)
    if introduced_quantities:
        rendered = ", ".join(f"{number} {unit}" for number, unit in introduced_quantities)
        errors.append(f"introduces an unsupported quantity or unit: {rendered}")

    claim_actions = _directive_actions(claim)
    quote_actions = _directive_actions(combined_quotes)
    if claim_actions and quote_actions and not claim_actions.issubset(quote_actions):
        errors.append("changes a required safety action")
    elif claim_actions and not quote_actions:
        errors.append("introduces directive safety language absent from its quotes")

    if _STRONG_DIRECTIVE.search(claim) and not _STRONG_DIRECTIVE.search(combined_quotes):
        errors.append("strengthens optional guidance into a requirement")

    return errors
