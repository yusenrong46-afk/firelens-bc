"""Typed critical-field extraction for quantities, comparators, and assertions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

_WORD_NUMBERS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}
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
    "mm": "millimetre",
    "millimeter": "millimetre",
    "millimetres": "millimetre",
    "millimetre": "millimetre",
    "km": "kilometre",
    "kilometer": "kilometre",
    "kilometers": "kilometre",
    "kilometre": "kilometre",
    "kilometres": "kilometre",
    "ft": "foot",
    "foot": "foot",
    "feet": "foot",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "mi": "mile",
    "mile": "mile",
    "miles": "mile",
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
    "kg": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "%": "percent",
    "percent": "percent",
}
_SI_FACTOR = {
    "metre": (Decimal("1"), "length"),
    "centimetre": (Decimal("0.01"), "length"),
    "millimetre": (Decimal("0.001"), "length"),
    "kilometre": (Decimal("1000"), "length"),
    "foot": (Decimal("0.3048"), "length"),
    "inch": (Decimal("0.0254"), "length"),
    "mile": (Decimal("1609.344"), "length"),
    "minute": (Decimal("60"), "time"),
    "hour": (Decimal("3600"), "time"),
    "day": (Decimal("86400"), "time"),
    "litre": (Decimal("1"), "volume"),
    "millilitre": (Decimal("0.001"), "volume"),
    "milligram": (Decimal("1"), "mass"),
    "kilogram": (Decimal("1000000"), "mass"),
    "percent": (Decimal("1"), "percent"),
}
_REL_TOLERANCE = Decimal("0.08")
_NUMBER = r"(?:(?:\d+(?:[,.]\d+)*)|" + "|".join(_WORD_NUMBERS) + r")"
_UNIT = (
    r"%|m|cm|mm|km|ml|mg|kg|l|ft|in|mi|"
    r"met(?:er|re)s?|centimet(?:er|re)s?|millimet(?:er|re)s?|"
    r"kilomet(?:er|re)s?|feet|foot|inches|inch|miles?|"
    r"minutes?|hours?|days?|lit(?:er|re)s?|millilitres?|milligrams?|kilograms?|kg|percent"
)
_QUANTITY = re.compile(
    rf"(?<![\w.])(?P<number>{_NUMBER})(?:\s*-?\s*)(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)
_AUTHORITY_ALIASES = {
    "bc centre for disease control": ("bc centre for disease control", "bccdc"),
    "bc wildfire service": ("bc wildfire service", "bcws"),
    "emergencyinfobc": ("emergencyinfobc",),
    "environment canada": (
        "environment canada",
        "environment and climate change canada",
    ),
    "firesmart bc": ("firesmart bc",),
    "firesmart canada": ("firesmart canada",),
    "government of british columbia": (
        "government of british columbia",
        "province of british columbia",
    ),
    "preparedbc": ("preparedbc", "prepared bc"),
    "canadian red cross": ("canadian red cross",),
    "municipal fire hall": ("municipal fire hall",),
    "local government": ("local government",),
    "local authority": ("local authority",),
    "health authority": ("health authority",),
    "alberta wildfire": ("alberta wildfire",),
    "national weather service": (
        "national weather service",
        "recognized national weather service",
    ),
    "unnamed provincial office": ("unnamed provincial office",),
}
_JURISDICTION_PATTERNS = {
    "british columbia": (
        r"\bin british columbia\b",
        r"\bin bc\b",
        r"\bapplies in british columbia\b",
        r"\bapplies in bc\b",
    ),
    "alberta": (r"\bin alberta\b", r"\bapplies in alberta\b"),
    "ontario": (r"\bin ontario\b", r"\bapplies in ontario\b"),
    "washington": (r"\bin washington(?: state)?\b", r"\bapplies in washington\b"),
    "other_province": (
        r"\bneighbouring province\b",
        r"\banother province\b",
        r"\ba neighbouring province\b",
    ),
}
_LOCATION_ALIASES = {
    "bc": "british columbia",
    "british columbia": "british columbia",
}
_MUST = re.compile(r"\b(?:must|required|mandatory|have to)\b", re.IGNORECASE)
_MAY = re.compile(r"\b(?:may|optional|if you want)\b", re.IGNORECASE)
_SHOULD = re.compile(r"\b(?:should|recommended)\b", re.IGNORECASE)
_UNLESS = re.compile(r"\bunless\b", re.IGNORECASE)
_EXCEPT = re.compile(r"\bexcept(?:\s+when)?\b", re.IGNORECASE)
_REVERSED_EXCEPTION = re.compile(
    r"\bespecially when\b|\beven if\b|\bnever help unless\b", re.IGNORECASE
)
_CURRENT = re.compile(
    r"\b(?:current|currently|latest|live|up(?:\s+|-)to(?:\s+|-)date)\b",
    re.IGNORECASE,
)
_CURRENT_DENIED = re.compile(
    r"\bnot(?:\s+\w+){0,4}\s+(?:a\s+)?(?:current|currently|latest|live)\b|"
    r"\bare not the latest\b|\bnot a current\b",
    re.IGNORECASE,
)
_STALE_MARK = re.compile(
    r"\b(?:19|20)\d{2}\s+plan\b|\bstale\b|\bcached\b|\brefresh failure\b|"
    r"\bfailed refresh\b|\boutdated\b|\bmixed freshness\b|\bnot the latest\b",
    re.IGNORECASE,
)
_IMMEDIATE = re.compile(r"\b(?:immediately|now)\b", re.IGNORECASE)
_DELAYED = re.compile(
    r"\blater(?:\s+today)?\b|\bdelay(?:ed)?\b|\bcan leave\b|\bwait to pack\b",
    re.IGNORECASE,
)
_AVOID = re.compile(r"\bavoid(?:ing)?\b", re.IGNORECASE)
_PERFORM = re.compile(r"\b(?:use|using|perform|run)\b", re.IGNORECASE)
_INCLUDE = re.compile(r"\binclude\b", re.IGNORECASE)
_EXCLUDE = re.compile(r"\bexclude\b", re.IGNORECASE)
_DOES_NOT_MEAN = re.compile(r"\bdoes not mean\b", re.IGNORECASE)
_DOES_MEAN = re.compile(r"\bdoes mean\b", re.IGNORECASE)
_STAY = re.compile(
    r"\b(?:stay|remain)(?:ing|s|ed)?(?:\s+(?:at|in))?(?:\s+the)?\s+"
    r"(?:area|home|inside|place|in place)\b",
    re.IGNORECASE,
)
_LEAVE_VERB = re.compile(r"\b(?:leave|evacuate)\b", re.IGNORECASE)
_LEAVE = _LEAVE_VERB
_DO_NOT_USE = re.compile(r"\b(?:do not|don't|never)\s+use\b", re.IGNORECASE)
_READY_STAY = re.compile(r"\bready to stay\b", re.IGNORECASE)
_READY_LEAVE = re.compile(r"\bready to leave\b", re.IGNORECASE)
_WAIT_ALL_CLEAR = re.compile(
    r"\bwait for an official all-clear before returning\b|"
    r"\ball-clear before returning\b",
    re.IGNORECASE,
)
_DEFERRED_RETURN = re.compile(
    r"\bwait(?:ing)? to return\b|\breturn only (?:after|when)\b",
    re.IGNORECASE,
)
_ALL_CLEAR = re.compile(r"\ball-clear\b|\bofficials say it is safe\b", re.IGNORECASE)


class Comparator(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    MORE_THAN = "more_than"
    LESS_THAN = "less_than"
    WITHIN = "within"
    BEYOND = "beyond"
    BETWEEN = "between"
    OUTSIDE = "outside"


_OPPOSITE = {
    Comparator.AT_LEAST: {Comparator.AT_MOST, Comparator.LESS_THAN},
    Comparator.AT_MOST: {Comparator.AT_LEAST, Comparator.MORE_THAN},
    Comparator.MORE_THAN: {Comparator.LESS_THAN, Comparator.AT_MOST, Comparator.WITHIN},
    Comparator.LESS_THAN: {Comparator.MORE_THAN, Comparator.AT_LEAST},
    Comparator.WITHIN: {Comparator.BEYOND, Comparator.OUTSIDE, Comparator.MORE_THAN},
    Comparator.BETWEEN: {Comparator.OUTSIDE, Comparator.BEYOND},
    Comparator.BEYOND: {Comparator.WITHIN, Comparator.AT_MOST, Comparator.BETWEEN},
    Comparator.OUTSIDE: {Comparator.BETWEEN, Comparator.WITHIN},
}
_COMPARATOR_PATTERNS = (
    (Comparator.AT_LEAST, r"at least|no less than|a minimum of|minimum of|no shorter than"),
    (Comparator.AT_MOST, r"at most|no more than|a maximum of|maximum of|no taller than"),
    (Comparator.MORE_THAN, r"(?<!no )more than|greater than"),
    (Comparator.LESS_THAN, r"(?<!no )less than|fewer than|(?<!no )under|below"),
    (Comparator.WITHIN, r"within|inside"),
    (Comparator.BEYOND, r"beyond"),
    (Comparator.BETWEEN, r"between"),
    (Comparator.OUTSIDE, r"outside"),
)


@dataclass(frozen=True)
class NormalizedQuantity:
    value: Decimal
    unit: str
    dimension: str
    si_value: Decimal


def extract_quantities(text: str) -> list[NormalizedQuantity]:
    found: list[NormalizedQuantity] = []
    for match in _QUANTITY.finditer(text):
        raw = match.group("number").casefold().replace(",", "")
        raw = _WORD_NUMBERS.get(raw, raw)
        try:
            number = Decimal(raw)
        except InvalidOperation:
            continue
        unit = _UNIT_ALIASES[match.group("unit").casefold()]
        factor, dimension = _SI_FACTOR[unit]
        found.append(
            NormalizedQuantity(
                value=number,
                unit=unit,
                dimension=dimension,
                si_value=number * factor,
            )
        )
    return found


def _supported_quantity(claim: NormalizedQuantity, quotes: list[NormalizedQuantity]) -> bool:
    for quote in quotes:
        if claim.dimension != quote.dimension:
            continue
        if claim.unit == quote.unit:
            if claim.value == quote.value:
                return True
            continue
        delta = abs(claim.si_value - quote.si_value)
        baseline = max(abs(quote.si_value), Decimal("0.0001"))
        if (delta / baseline) <= _REL_TOLERANCE:
            return True
    return False


def quantity_errors(claim: str, quotes: str) -> list[str]:
    claim_quantities = extract_quantities(claim)
    quote_quantities = extract_quantities(quotes)
    if not claim_quantities:
        return []
    unsupported = [
        item for item in claim_quantities if not _supported_quantity(item, quote_quantities)
    ]
    if not unsupported:
        return []
    rendered = ", ".join(f"{item.value.normalize()} {item.unit}" for item in unsupported)
    return [f"introduces an unsupported quantity or unit: {rendered}"]


def extract_comparators(text: str) -> set[Comparator]:
    lowered = text.casefold()
    lowered = re.sub(r"\bno fewer than\b", " at least ", lowered)
    lowered = re.sub(r"\bno less than\b", " at least ", lowered)
    found: set[Comparator] = set()
    for comparator, pattern in _COMPARATOR_PATTERNS:
        if re.search(rf"\b(?:{pattern})\b", lowered):
            found.add(comparator)
    if re.search(r"\bno shorter than\b", lowered):
        found.add(Comparator.AT_LEAST)
    return found


def comparator_errors(claim: str, quotes: str) -> list[str]:
    claim_set = extract_comparators(claim)
    quote_set = extract_comparators(quotes)
    if not claim_set or not quote_set:
        return []
    if any(item in _OPPOSITE.get(quote, set()) for quote in quote_set for item in claim_set):
        return ["reverses a comparator"]
    return []


def _mentioned(text: str, aliases: dict[str, tuple[str, ...]]) -> set[str]:
    lowered = text.casefold()
    return {
        name
        for name, options in aliases.items()
        if any(re.search(rf"(?<!\w){re.escape(option)}(?!\w)", lowered) for option in options)
    }


def authority_errors(claim: str, allowed: str) -> list[str]:
    claimed = _mentioned(claim, _AUTHORITY_ALIASES)
    allowed_set = _mentioned(allowed, _AUTHORITY_ALIASES)
    introduced = sorted(claimed - allowed_set)
    if introduced:
        return ["introduces or substitutes an unsupported authority: " + ", ".join(introduced)]
    return []


def jurisdiction_errors(claim: str, quotes: str) -> list[str]:
    claimed = {
        name
        for name, patterns in _JURISDICTION_PATTERNS.items()
        if any(re.search(pattern, claim, re.IGNORECASE) for pattern in patterns)
    }
    quoted = {
        name
        for name, patterns in _JURISDICTION_PATTERNS.items()
        if any(re.search(pattern, quotes, re.IGNORECASE) for pattern in patterns)
    }
    introduced = sorted(claimed - quoted)
    if introduced:
        return [
            "introduces or substitutes an unsupported jurisdiction: " + ", ".join(introduced)
        ]
    if quoted and not claimed:
        return ["removes a location or jurisdiction qualifier"]
    return []


def normalize_location_name(name: str) -> str:
    return _LOCATION_ALIASES.get(name.casefold(), name.casefold())


_LIVE_REFRESH = re.compile(r"\blive refresh\b", re.IGNORECASE)


def freshness_errors(claim: str, quotes: str) -> list[str]:
    screened_claim = _LIVE_REFRESH.sub(" refresh ", claim)
    screened_quotes = _LIVE_REFRESH.sub(" refresh ", quotes)
    if _CURRENT_DENIED.search(screened_claim):
        return []
    if not _CURRENT.search(screened_claim):
        return []
    if _STALE_MARK.search(screened_quotes) or _CURRENT_DENIED.search(screened_quotes):
        return ["describes stale or dated guidance as current"]
    return []


def modality_errors(claim: str, quotes: str) -> list[str]:
    quote_must = bool(_MUST.search(quotes))
    quote_may = bool(_MAY.search(quotes))
    claim_must = bool(_MUST.search(claim))
    claim_may = bool(_MAY.search(claim))
    if quote_must and claim_may and not _MUST.search(claim):
        return ["weakens a requirement into an option"]
    if quote_may and claim_must and not _MAY.search(claim):
        return ["strengthens optional guidance into a requirement"]
    if _SHOULD.search(quotes) and claim_must and not _MUST.search(quotes):
        return ["strengthens optional guidance into a requirement"]
    return []


def exception_errors(claim: str, quotes: str) -> list[str]:
    if not _UNLESS.search(quotes) and not _EXCEPT.search(quotes):
        return []
    if _REVERSED_EXCEPTION.search(claim):
        return ["reverses a material exception"]
    if not (_UNLESS.search(claim) or _EXCEPT.search(claim)):
        if re.search(r"\bwhen\b", claim, re.IGNORECASE) and _UNLESS.search(quotes):
            return ["reverses a material exception"]
        return ["removes a material exception"]
    return []


def action_assertion_errors(claim: str, quotes: str) -> list[str]:
    errors: list[str] = []
    if _LEAVE_VERB.search(quotes) and _STAY.search(claim) and not _STAY.search(quotes):
        errors.append("changes a required safety action")
    if _READY_LEAVE.search(quotes) and _READY_STAY.search(claim):
        errors.append("changes a required safety action")
    if _IMMEDIATE.search(quotes) and _DELAYED.search(claim) and not _IMMEDIATE.search(claim):
        errors.append("weakens immediate action into delay")
    if (
        _AVOID.search(quotes)
        and _PERFORM.search(claim)
        and not (_AVOID.search(claim) or _DO_NOT_USE.search(claim))
    ):
        errors.append("reverses an avoidance instruction")
    if _INCLUDE.search(quotes) and _EXCLUDE.search(claim):
        errors.append("changes the polarity of a safety action")
    if _DOES_NOT_MEAN.search(quotes) and (
        _DOES_MEAN.search(claim)
        or (_LEAVE_VERB.search(claim) and not re.search(r"\bdoes not\b", claim, re.I))
    ):
        errors.append("changes the polarity of a safety action")
    if _WAIT_ALL_CLEAR.search(quotes) and re.search(
        r"\breturn(?:ing)?\b", claim, re.IGNORECASE
    ):
        if re.search(r"return before an official all-clear", claim, re.IGNORECASE):
            errors.append("changes the polarity of a safety action")
        elif re.search(r"without an official all-clear", claim, re.IGNORECASE):
            errors.append("changes the polarity of a safety action")
        elif re.search(
            r"wait before returning", claim, re.IGNORECASE
        ) and not _ALL_CLEAR.search(claim):
            errors.append("removes a material condition from its quotes")
        elif not _ALL_CLEAR.search(claim) and not _DEFERRED_RETURN.search(claim):
            errors.append("changes the polarity of a safety action")
    if _DEFERRED_RETURN.search(quotes) and re.search(r"\breturn\b", claim, re.IGNORECASE):
        if not (
            _DEFERRED_RETURN.search(claim)
            or _ALL_CLEAR.search(claim)
            or re.search(r"\bdo not return\b", claim, re.IGNORECASE)
        ):
            errors.append("changes the polarity of a safety action")
    if _ALL_CLEAR.search(quotes) and re.search(r"\breturn\b", claim, re.IGNORECASE):
        if not _ALL_CLEAR.search(claim) and not _DEFERRED_RETURN.search(claim):
            if re.search(r"\bbefore returning\b", quotes, re.IGNORECASE) and not re.search(
                r"\bbefore returning\b", claim, re.IGNORECASE
            ):
                errors.append("removes a material condition from its quotes")
    if _LEAVE.search(quotes) and re.search(r"\bbefore leaving\b", claim, re.IGNORECASE):
        if re.search(r"\bbefore returning\b", quotes, re.IGNORECASE):
            errors.append("changes a required safety action")
    if re.search(r"\bbefore returning\b", quotes, re.IGNORECASE) and re.search(
        r"\bbefore leaving\b", claim, re.IGNORECASE
    ):
        errors.append("changes a required safety action")
    return errors


def condition_trigger_errors(claim: str, quotes: str) -> list[str]:
    if re.search(r"\bafter evacuating\b", quotes, re.IGNORECASE) and not re.search(
        r"\bafter evacuating\b", claim, re.IGNORECASE
    ):
        return ["removes a material condition from its quotes"]
    if re.search(r"\bthis community\b", quotes, re.IGNORECASE) and not re.search(
        r"\b(?:this community|local)\b", claim, re.IGNORECASE
    ):
        return ["removes a location or jurisdiction qualifier"]
    if re.search(r"\bon an evacuation alert\b", quotes, re.IGNORECASE) and not re.search(
        r"\b(?:if|when|on)\b", claim, re.IGNORECASE
    ):
        return ["removes a material condition from its quotes"]
    return []


def critical_field_errors(claim: str, quotes: str, allowed_context: str) -> list[str]:
    errors: list[str] = []
    errors.extend(quantity_errors(claim, quotes))
    errors.extend(comparator_errors(claim, quotes))
    errors.extend(authority_errors(claim, allowed_context))
    errors.extend(jurisdiction_errors(claim, quotes))
    errors.extend(freshness_errors(claim, quotes))
    errors.extend(modality_errors(claim, quotes))
    errors.extend(exception_errors(claim, quotes))
    errors.extend(action_assertion_errors(claim, quotes))
    errors.extend(condition_trigger_errors(claim, quotes))
    return list(dict.fromkeys(errors))
