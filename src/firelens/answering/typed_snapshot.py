"""Open-lexicon typed snapshots of source and answer text.

Extraction is structural: organizations, action frames, time roles, range
bounds, conditions, and predicates. It is not a closed phrase list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from firelens.answering.critical_fields import (
    Comparator,
    NormalizedQuantity,
    extract_quantities,
)
from firelens.answering.risk_policy import RiskTier

_STOP = frozenset(
    "a an the of to for in on at by with from into onto over under and or".split()
)
_ORG_ALIASES = {
    "bcws": "bc wildfire service",
    "bc wildfire service": "bc wildfire service",
    "prepared bc": "preparedbc",
    "preparedbc": "preparedbc",
    "firesmart": "firesmart bc",
    "firesmart bc": "firesmart bc",
    "bccdc": "bc centre for disease control",
    "bc centre for disease control": "bc centre for disease control",
    "interior health authority": "interior health",
    "interior health": "interior health",
    "northern health authority": "northern health",
    "northern health": "northern health",
}
_ATTRIBUTION = (
    r"publishes?|published|recommends?|recommended|requires?|required|"
    r"issues?|issued|provides?|provided|advises?|advised|reports?|reported|"
    r"says|said"
)
_TITLE = r"[A-Z][A-Za-z]+(?:[-'][A-Za-z]+)*"
_ORG_NAME = rf"{_TITLE}(?:\s+(?:of\s+(?:the\s+)?)?{_TITLE}){{0,6}}"
_SUBJECT_ORG = re.compile(rf"\b(?:the\s+)?(?P<org>{_ORG_NAME})\s+(?:{_ATTRIBUTION})\b")
_BY_ORG = re.compile(rf"\bby\s+(?:the\s+)?(?P<org>{_ORG_NAME})\b")
_ONLY_ORG = re.compile(rf"(?i:only)\s+(?:(?i:the)\s+)?(?P<org>{_ORG_NAME})\b")
_GENERIC_ACTOR = re.compile(
    r"\bany\s+(?:nearby\s+)?(?:responding\s+)?(?:agency|jurisdiction|authority)\b",
    re.IGNORECASE,
)
_POSSESSIVE_JURISDICTION = re.compile(
    r"\b(?P<place>British Columbia|Alberta|Saskatchewan|Ontario|Manitoba|"
    r"Washington)\s*'s\s+provincial\b"
)
_MUNICIPAL = re.compile(
    r"\b(?:City|District|Village|Town|Municipality|Township)\s+of\s+"
    r"(?P<place>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b"
)
_FIRE_CENTRE = re.compile(
    r"\b(?:in\s+the\s+)?(?P<place>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
    r"Fire Centre(?:\s+region)?)\b"
)
_PROVINCE_WIDE = re.compile(
    r"\b(?:across|throughout|all of|province of)\s+British Columbia\b",
    re.IGNORECASE,
)
_AVOID = re.compile(
    r"\b(?:avoid(?:ing)?|do not|don't|never|keep off|stay out of|stay out)\s+"
    r"(?P<body>[^.!?;]+)",
    re.IGNORECASE,
)
_PERFORM = re.compile(
    r"\b(?P<verb>drive|walk|use|close|leave|remain|stay|wait|go|shut|"
    r"evacuate|act|move|relocate|enter)\b(?P<body>[^.!?;]*)",
    re.IGNORECASE,
)
_LEMMA = {
    "driving": "drive",
    "drive": "drive",
    "walking": "walk",
    "walk": "walk",
    "using": "use",
    "use": "use",
    "closing": "close",
    "close": "close",
    "leaving": "leave",
    "leave": "leave",
    "evacuating": "leave",
    "evacuate": "leave",
    "remaining": "stay",
    "remain": "stay",
    "stay": "stay",
    "waiting": "wait",
    "wait": "wait",
    "go": "enter",
    "enter": "enter",
    "shut": "shut",
    "act": "act",
    "move": "move",
    "relocating": "move",
    "relocate": "move",
}
_IMMEDIATE = re.compile(
    r"\b(?:immediately|at once|right away|without delay|act now)\b",
    re.IGNORECASE,
)
_DELAYED = re.compile(
    r"\b(?:when convenient|at your leisure|when you can spare(?:\s+a\s+moment)?|"
    r"later(?:\s+today)?|delay(?:ed)?|wait to)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
_DATE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?:19|20)\d{2}\b|"
    r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_RETRIEVED_HINT = re.compile(r"\b(?:firelens|fetched|retrieved|retrieval)\b", re.IGNORECASE)
_SOURCE_HINT = re.compile(
    r"\b(?:official source updated|source (?:last )?updated|agency (?:officially )?"
    r"updated|last updated by the source|source last updated)\b",
    re.IGNORECASE,
)
_UNKNOWN_UPDATE = re.compile(
    r"\b(?:has not (?:reported|supplied) an?(?: official)? update time|"
    r"update time (?:for this .{0,20} )?is unknown|timestamp .{0,20} unknown)\b",
    re.IGNORECASE,
)
_BETWEEN = re.compile(
    r"\bbetween\s+(?P<a>\d+(?:\.\d+)?)\s+and\s+(?P<b>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_INCLUSIVE_UPPER = re.compile(
    r"\bup to and including\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<u>[A-Za-z]+)?\b",
    re.IGNORECASE,
)
_EXCLUSIVE_UPPER = re.compile(
    r"\b(?:strictly less than|below)\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<u>[A-Za-z]+)?\b"
    r"(?:.{0,60}\bexclud(?:e|ing|es)\b)?",
    re.IGNORECASE,
)
_MEANS = re.compile(
    r"\b(?:an?\s+)?evacuation\s+(?P<term>alert|order)\s+means\s+(?P<body>[^.;]+)",
    re.IGNORECASE,
)
_DOWNGRADE = re.compile(
    r"\b(?:downgraded|reduced)\b.{0,40}\balert\b",
    re.IGNORECASE,
)
_UPGRADE = re.compile(
    r"\b(?:upgraded|raised)\b.{0,40}\border\b",
    re.IGNORECASE,
)
_NOT_ALL_CLEAR = re.compile(r"\bis not an all-clear\b", re.IGNORECASE)
_IS_ALL_CLEAR = re.compile(r"\bis an all-clear\b", re.IGNORECASE)
_MUST_NOT_RETURN = re.compile(r"\bmust not return\b", re.IGNORECASE)
_MUST_NOW_RETURN = re.compile(r"\bmust now return\b", re.IGNORECASE)
_IF = re.compile(
    r"\b(?:if|when|until|only after|only when|on an?)\s+(?P<body>[^,.;]+)",
    re.I,
)
_EXCEPT = re.compile(r"\b(?:except|unless)\b.{0,80}", re.IGNORECASE)
_NO_EXCEPTION = re.compile(
    r"\b(?:without exception|in all circumstances|generally (?:allowed|permitted))\b",
    re.IGNORECASE,
)
_RESTRICTED_GROUP = re.compile(
    r"\b(?:residents|people|persons)\s+with\s+[^,.;]+",
    re.IGNORECASE,
)
_UNIVERSAL_GROUP = re.compile(r"\b(?:all residents|everyone|every resident)\b", re.I)
_FRESH_LIVE = re.compile(
    r"\b(?:current|currently|latest|up(?:\s+|-)to(?:\s+|-)(?:the\s+)?(?:date|minute)|"
    r"fresh|recent|fully current)\b",
    re.IGNORECASE,
)
_FRESH_STALE = re.compile(
    r"\b(?:stale|cached|outdated|failed refresh|refresh (?:did not complete|failed)|"
    r"unknown)\b",
    re.IGNORECASE,
)
_CURRENT_DENIED = re.compile(
    r"\bnot(?:\s+\w+){0,4}\s+(?:a\s+)?(?:current|currently|latest|live)\b|"
    r"\bare not the latest\b|\bnot a current\b",
    re.IGNORECASE,
)
_LIVE_REFRESH = re.compile(r"\blive refresh\b", re.IGNORECASE)
_LIVE_CLAIM = re.compile(r"\blive\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")
_UNIT_TAIL = re.compile(
    r"^\s*(?:m|cm|mm|km|ft|in|mi|l|ml|mg|kg|psi|metres?|meters?|feet|foot|"
    r"inches|miles?|litres?|liters?|kilograms?|hours?|days?|minutes?)\b",
    re.IGNORECASE,
)
_EVAC_TERMS = re.compile(
    r"\b(?:evacuat(?:e|ion)|all-clear|leave|stay|remain|alert|order)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActionFrame:
    lemma: str
    polarity: str
    object_tokens: frozenset[str]


@dataclass(frozen=True)
class OrgMention:
    name: str
    exclusive: bool
    generic: bool = False


@dataclass(frozen=True)
class TimeMention:
    token: str
    role: str


@dataclass(frozen=True)
class OrderedRange:
    first: Decimal
    second: Decimal
    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class BoundMark:
    value: Decimal
    inclusive: bool


@dataclass(frozen=True)
class ConditionClause:
    body: str
    negated: bool


@dataclass(frozen=True)
class TypedSnapshot:
    quantities: tuple[NormalizedQuantity, ...]
    bare_numbers: tuple[str, ...]
    comparators: frozenset[str]
    ranges: tuple[OrderedRange, ...]
    inclusive_upper: tuple[BoundMark, ...]
    exclusive_upper: tuple[BoundMark, ...]
    orgs: tuple[OrgMention, ...]
    jurisdictions: frozenset[str]
    municipalities: frozenset[str]
    regions: frozenset[str]
    province_wide: bool
    freshness_live: bool
    freshness_stale: bool
    unknown_update: bool
    times: tuple[TimeMention, ...]
    urgency_immediate: bool
    urgency_delayed: bool
    actions: tuple[ActionFrame, ...]
    conditions: tuple[ConditionClause, ...]
    has_condition_marker: bool
    exceptions: tuple[str, ...]
    exception_stripped: bool
    restricted_group: bool
    universal_group: bool
    dates: frozenset[str]
    definitions: tuple[tuple[str, str], ...]
    downgrade: bool
    upgrade: bool
    all_clear: str | None
    must_not_return: bool
    must_now_return: bool
    risk_tier: RiskTier


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in _STOP and len(token) > 1
    )


def _norm_org(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip().casefold()
    cleaned = re.sub(r"^the\s+", "", cleaned)
    return _ORG_ALIASES.get(cleaned, cleaned)


def _lemma(verb: str, body: str) -> str:
    word = verb.casefold()
    lowered = body.casefold()
    if word in {"keep"} or lowered.startswith("off "):
        return "use"
    if "stay out" in word or lowered.startswith("in on") or word == "go":
        return "enter"
    return _LEMMA.get(word, word)


def _avoid_lemma(trigger: str, body: str) -> str:
    lowered = trigger.casefold()
    if lowered.startswith("keep off") or "keep off" in lowered[:24]:
        return "use"
    if "stay out" in lowered[:24]:
        return "enter"
    head = body.split()[0] if body.split() else ""
    return _lemma(head, body)


def extract_snapshot(text: str) -> TypedSnapshot:
    screened = _LIVE_REFRESH.sub(" refresh ", text)
    screened = _CURRENT_DENIED.sub(" ", screened)
    quantities = tuple(extract_quantities(text))
    bare: list[str] = []
    for match in _NUMBER.finditer(text):
        if _UNIT_TAIL.match(text[match.end() :]):
            continue
        bare.append(match.group(1))
    orgs: list[OrgMention] = []
    for match in _SUBJECT_ORG.finditer(text):
        name = _norm_org(match.group("org"))
        if name in {"firelens", "official source", "source"}:
            continue
        orgs.append(OrgMention(name=name, exclusive=False))
    for match in _BY_ORG.finditer(text):
        name = _norm_org(match.group("org"))
        if name in {"firelens"}:
            continue
        orgs.append(OrgMention(name=name, exclusive=False))
    for match in _ONLY_ORG.finditer(text):
        orgs.append(OrgMention(name=_norm_org(match.group("org")), exclusive=True))
    if _GENERIC_ACTOR.search(text):
        orgs.append(OrgMention(name="generic_actor", exclusive=False, generic=True))
    jurisdictions = {
        match.group("place").casefold() for match in _POSSESSIVE_JURISDICTION.finditer(text)
    }
    municipalities = {
        f"of {match.group('place')}".casefold() for match in _MUNICIPAL.finditer(text)
    }
    regions = {match.group("place").casefold() for match in _FIRE_CENTRE.finditer(text)}
    actions: list[ActionFrame] = []
    for match in _AVOID.finditer(text):
        body = match.group("body")
        actions.append(
            ActionFrame(
                lemma=_avoid_lemma(match.group(0), body),
                polarity="avoid",
                object_tokens=_tokens(body),
            )
        )
    avoided_spans = [match.span() for match in _AVOID.finditer(text)]
    for match in _PERFORM.finditer(text):
        if any(start <= match.start() < end for start, end in avoided_spans):
            continue
        verb = match.group("verb")
        body = match.group("body")
        actions.append(
            ActionFrame(
                lemma=_lemma(verb, body),
                polarity="perform",
                object_tokens=_tokens(f"{verb} {body}"),
            )
        )
    times: list[TimeMention] = []
    for match in list(_CLOCK.finditer(text)) + list(_DATE.finditer(text)):
        window = text[max(0, match.start() - 90) : match.end() + 40]
        if _RETRIEVED_HINT.search(window):
            role = "retrieved"
        elif _SOURCE_HINT.search(window) or re.search(
            r"\b(?:source|agency)\b.{0,40}\bupdated\b", window, re.I
        ):
            role = "source_updated"
        else:
            role = "unspecified"
        times.append(TimeMention(token=match.group().casefold(), role=role))
    ranges = []
    for match in _BETWEEN.finditer(text):
        first = Decimal(match.group("a"))
        second = Decimal(match.group("b"))
        ranges.append(
            OrderedRange(
                first=first,
                second=second,
                low=min(first, second),
                high=max(first, second),
            )
        )
    inclusive = tuple(
        BoundMark(value=Decimal(match.group("n")), inclusive=True)
        for match in _INCLUSIVE_UPPER.finditer(text)
    )
    exclusive = tuple(
        BoundMark(value=Decimal(match.group("n")), inclusive=False)
        for match in _EXCLUSIVE_UPPER.finditer(text)
    )
    conditions = []
    for match in _IF.finditer(text):
        body = " ".join(match.group("body").casefold().split())
        negated = bool(re.search(r"\b(?:no|not)\b", body))
        conditions.append(
            ConditionClause(body=re.sub(r"\b(?:no|not)\b", "", body), negated=negated)
        )
    definitions = tuple(
        (match.group("term").casefold(), " ".join(match.group("body").casefold().split()))
        for match in _MEANS.finditer(text)
    )
    if _NOT_ALL_CLEAR.search(text):
        all_clear: str | None = "negated"
    elif _IS_ALL_CLEAR.search(text):
        all_clear = "asserted"
    else:
        all_clear = None
    live = bool(_FRESH_LIVE.search(screened) or _LIVE_CLAIM.search(screened))
    stale = bool(_FRESH_STALE.search(text))
    actions_t = tuple(actions)
    orgs_t = tuple(orgs)
    if actions_t or _EVAC_TERMS.search(text) or all_clear or _MUST_NOW_RETURN.search(text):
        tier = RiskTier.A
    elif quantities or orgs_t or live or stale or times or ranges:
        tier = RiskTier.B
    else:
        tier = RiskTier.C
    comparators: set[str] = set()
    lowered = re.sub(r"\bno fewer than\b", " at least ", text.casefold())
    lowered = re.sub(r"\bno less than\b", " at least ", lowered)
    if re.search(r"\bat least\b|\ba minimum of\b|\bminimum of\b", lowered):
        comparators.add(Comparator.AT_LEAST.value)
    if re.search(r"\bat most\b|\bno more than\b|\ba maximum of\b", lowered):
        comparators.add(Comparator.AT_MOST.value)
    if re.search(r"\bmore than\b|\bgreater than\b", lowered):
        comparators.add(Comparator.MORE_THAN.value)
    if re.search(r"\bless than\b|\bfewer than\b", lowered):
        comparators.add(Comparator.LESS_THAN.value)
    if re.search(r"\bwithin\b|\binside\b", lowered):
        comparators.add(Comparator.WITHIN.value)
    if re.search(r"\bbeyond\b", lowered):
        comparators.add(Comparator.BEYOND.value)
    if re.search(r"\bbetween\b", lowered):
        comparators.add(Comparator.BETWEEN.value)
    if re.search(r"\boutside\b", lowered):
        comparators.add(Comparator.OUTSIDE.value)
    return TypedSnapshot(
        quantities=quantities,
        bare_numbers=tuple(bare),
        comparators=frozenset(comparators),
        ranges=tuple(ranges),
        inclusive_upper=inclusive,
        exclusive_upper=exclusive,
        orgs=orgs_t,
        jurisdictions=frozenset(jurisdictions),
        municipalities=frozenset(municipalities),
        regions=frozenset(regions),
        province_wide=bool(_PROVINCE_WIDE.search(text)),
        freshness_live=live,
        freshness_stale=stale,
        unknown_update=bool(_UNKNOWN_UPDATE.search(text)),
        times=tuple(times),
        urgency_immediate=bool(_IMMEDIATE.search(text)),
        urgency_delayed=bool(_DELAYED.search(text)),
        actions=actions_t,
        conditions=tuple(conditions),
        has_condition_marker=bool(_IF.search(text)),
        exceptions=tuple(match.group().casefold() for match in _EXCEPT.finditer(text)),
        exception_stripped=bool(_NO_EXCEPTION.search(text)),
        restricted_group=bool(_RESTRICTED_GROUP.search(text)),
        universal_group=bool(_UNIVERSAL_GROUP.search(text)),
        dates=frozenset(match.group().casefold() for match in _DATE.finditer(text)),
        definitions=definitions,
        downgrade=bool(_DOWNGRADE.search(text)),
        upgrade=bool(_UPGRADE.search(text)),
        all_clear=all_clear,
        must_not_return=bool(_MUST_NOT_RETURN.search(text)),
        must_now_return=bool(_MUST_NOW_RETURN.search(text)),
        risk_tier=tier,
    )


def classify_text(text: str) -> RiskTier:
    return extract_snapshot(text).risk_tier


def _supported_quantity(
    claim: NormalizedQuantity, quotes: tuple[NormalizedQuantity, ...]
) -> bool:
    for quote in quotes:
        if claim.dimension != quote.dimension:
            continue
        if claim.unit == quote.unit and claim.value == quote.value:
            return True
        delta = abs(claim.si_value - quote.si_value)
        baseline = max(abs(quote.si_value), Decimal("0.0001"))
        if (delta / baseline) <= Decimal("0.08"):
            return True
    return False


def quantity_supported(
    claim: NormalizedQuantity, quotes: tuple[NormalizedQuantity, ...]
) -> bool:
    return _supported_quantity(claim, quotes)


def objects_overlap(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False
    if left & right:
        return True
    return False
