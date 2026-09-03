"""UNDERSTAND: which specific fire a question names.

A fire is named by its BC Wildfire Service incident number ("K51402") or by a
name span ending in a singular fire noun ("the Bald Range fire", "McDougall
Creek wildfire", "Grouse Complex"). The span is read structurally, right to
left from the fire noun, stopping at the closed classes (function words,
request verbs, domain nouns, descriptive adjectives), so "Is the Bald Range
fire out of control?", "Bald Range fire update?" and "tell me about the Bald
Range fire" all name the same fire.

Communities and fire names share the "<Name> fire" shape ("Kelowna fire
now?" asks about fires around Kelowna; "Salmon Arm fire update" too). The span
counts as a fire name when the person marks one fire: a determiner with no
report noun after it ("the Bald Range fire", "is the Kelowna fire out?"), a
proper-name styling ("Mountain Fire"), a naming verb ("a fire called Phantom
Ridge"), or a bare geographic-feature name standing alone ("bald range fire").
Anything else is left to place understanding, which owns communities.

"wildfire smoke", "fire season" and "wildfire history" are compounds, not
names: the fire noun is followed by another open-class word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import firelens.answering.intent_lexicon as lex
from firelens.understanding.place_vocabulary import (
    DIRECTION_WORDS,
    DOMAIN_NOUNS,
    FUNCTION_WORDS,
    OUT_OF_PROVINCE_PLACES,
    PROVINCE_LABELS,
    WHOLE_COUNTRY_LABELS,
)

INCIDENT_NUMBER = re.compile(r"(?<![A-Za-z0-9])(?P<number>[A-Za-z]\d{4,6})(?![A-Za-z0-9])")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*")
# Singular heads only: "fires near Kelowna" names no fire.
_HEADS = frozenset({"fire", "wildfire", "blaze"})
# A head that is part of the official name ("Grouse Complex").
_NAMED_HEADS = frozenset({"complex"})
_MAX_NAME_TOKENS = 5
_DETERMINERS = frozenset({"the", "this"})
# Geographic features that end BC fire names ("Bald Range", "McDougall Creek").
_FEATURES = frozenset(
    {"creek", "ck", "lake", "river", "mountain", "mtn", "mount", "range", "ridge", "hill",
     "hills", "valley", "canyon", "point", "island", "bay", "road", "rd", "fsr", "peak", "bluff",
     "bluffs", "falls", "pass", "flats", "flat", "meadows", "meadow", "butte", "glacier",
     "trail", "landing", "park", "plateau", "summit", "gulch", "slough", "marsh", "bench",
     "spur", "junction", "crossing", "arm", "inlet", "sound", "cove", "rapids", "springs",
     "prairie", "bar", "lookout", "forks", "narrows"}
)  # fmt: skip
# Nouns that turn "<Place> fire ..." into a report about the place, not a name.
_REPORT_NOUNS = frozenset(
    {"update", "updates", "status", "situation", "report", "reports", "summary", "overview",
     "news", "info", "information", "map", "conditions", "outlook", "activity", "season",
     "danger", "risk", "risks", "ban", "bans", "smoke", "weather", "forecast", "count",
     "counts", "picture", "roster", "records", "list", "history", "size", "zone", "area"}
)  # fmt: skip
# "Salmon Arm fire now?": a time word after the fire noun asks about the place.
_TIME_ADVERBS = frozenset(
    {"now", "today", "tonight", "tonite", "currently", "rn", "latest", "please", "right",
     "yesterday", "tomorrow", "this", "at", "as", "so", "for"}
)  # fmt: skip
_NAMING_VERB = re.compile(r"\b(?:called|named|known\s+as)\s+", re.IGNORECASE)
# "Kelowna Fire Centre", "Vernon fire department": organizations, not fires.
_ORGANIZATION_TAILS = frozenset(
    {"centre", "center", "department", "dept", "hall", "chief", "crews", "crew", "service",
     "services", "rescue", "brigade", "station", "district", "protection", "ban", "bans"}
)  # fmt: skip
_NOT_NAMES = PROVINCE_LABELS | OUT_OF_PROVINCE_PLACES | WHOLE_COUNTRY_LABELS
# Words that end a name span when read leftwards from the fire noun.
_STOPS = (
    FUNCTION_WORDS
    | DOMAIN_NOUNS
    | lex.RECORD_COMMANDS
    | lex.REQUEST_STARTERS
    | frozenset(
        {"big", "bigger", "biggest", "largest", "larger", "smallest", "major", "main", "new",
         "newest", "recent", "old", "oldest", "second", "third", "fourth", "fifth", "local",
         "same", "another", "other", "possible", "potential", "huge", "massive", "small",
         "large", "nearby", "yesterday's", "today's", "tonight's"}
    )
)  # fmt: skip
# After the fire noun the sentence may end or continue with a predicate or a
# locative; another open-class word makes the noun a modifier ("fire season").
_AFTER_HEAD = (FUNCTION_WORDS - DOMAIN_NOUNS) | frozenset(
    {"growing", "grown", "spreading", "spread", "contained", "controlled", "held", "burning",
     "started", "start", "moving", "heading", "threatening", "doing", "going", "located",
     "situated", "grow", "close", "closer", "far", "big", "bigger", "active", "safe",
     "dangerous", "compared", "vs", "versus", "update", "updates", "status", "size",
     "distance", "history", "smoke"}
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class FireNameMention:
    """A specific fire the question names, as the person wrote it."""

    label: str
    span: tuple[int, int]
    incident_number: bool = False


def _key(token: str) -> str:
    return token.casefold().strip(".'’")


def extract_fire_name(text: str) -> FireNameMention | None:
    """The specific fire a question names, or None when it names no single fire."""

    number = INCIDENT_NUMBER.search(text)
    if number is not None:
        return FireNameMention(
            label=number.group("number").upper(),
            span=number.span("number"),
            incident_number=True,
        )
    named = _named_by_verb(text)
    if named is not None:
        return named
    tokens = list(_TOKEN.finditer(text))
    for index, head in enumerate(tokens):
        head_key = _key(head.group(0))
        if head_key not in _HEADS and head_key not in _NAMED_HEADS:
            continue
        following = _following(text, tokens, index)
        if following is not None and following not in _AFTER_HEAD:
            continue
        span_start = _name_start(text, tokens, index)
        if span_start is None:
            continue
        if " ".join(_key(match.group(0)) for match in tokens[span_start:index]) in _NOT_NAMES:
            continue
        if not _looks_like_a_fire_name(text, tokens, span_start, index, following):
            continue
        end = head.end() if head_key in _NAMED_HEADS else tokens[index - 1].end()
        label = " ".join(text[tokens[span_start].start() : end].split())
        return FireNameMention(label=label, span=(tokens[span_start].start(), end))
    return None


def _following(text: str, tokens: list[re.Match[str]], index: int) -> str | None:
    """The word after the fire noun, or None at a sentence or clause boundary."""

    if index + 1 >= len(tokens):
        return None
    between = text[tokens[index].end() : tokens[index + 1].start()]
    if any(mark in between for mark in ",.;:?!-—–("):
        return None
    return _key(tokens[index + 1].group(0))


def _name_start(text: str, tokens: list[re.Match[str]], head_index: int) -> int | None:
    start = head_index
    while start > 0 and head_index - start < _MAX_NAME_TOKENS:
        candidate = tokens[start - 1].group(0)
        gap = text[tokens[start - 1].end() : tokens[start].start()]
        if any(mark in gap for mark in ',.;:?!()"“”') or candidate.isdigit():
            break
        # "Bush Creek East": a capitalized domain noun can be part of a name.
        if _key(candidate) in _STOPS and not (
            candidate[0].isupper() and _key(candidate) in DOMAIN_NOUNS
        ):
            break
        start -= 1
    # "caused Mountain Fire": a styled name does not begin with a lowercase verb.
    if any(tokens[i].group(0)[0].isupper() for i in range(start, head_index)):
        while start < head_index and tokens[start].group(0)[0].islower():
            start += 1
    return None if start == head_index else start


def _looks_like_a_fire_name(
    text: str,
    tokens: list[re.Match[str]],
    start: int,
    head_index: int,
    following: str | None,
) -> bool:
    head = tokens[head_index].group(0)
    if _key(head) in _NAMED_HEADS:
        return True
    if following in _ORGANIZATION_TAILS:
        return False
    words = [match.group(0) for match in tokens[start:head_index]]
    keys = [_key(word) for word in words]
    if any(key in _NOT_NAMES for key in keys):
        return False  # "BC mountain fire", "the Alberta wildfire"
    if start > 0 and _key(tokens[start - 1].group(0)) in _DETERMINERS:
        if len(keys) == 1 and keys[0] in _FEATURES and words[0][0].islower():
            return False  # "the mountain fire", "the creek fire": generic, not a name
        return following not in _REPORT_NOUNS  # "the Vernon wildfire update" is a place
    if head[0].isupper() and words[0][0].isupper():
        return True  # "Bald Range Fire", "Mountain Fire": styled as a proper name
    last = keys[-2] if len(keys) > 1 and keys[-1] in DIRECTION_WORDS else keys[-1]
    consistent_case = len({word[0].isupper() for word in words}) == 1
    return (
        len(keys) > 1
        and last in _FEATURES
        and consistent_case
        and following not in _REPORT_NOUNS | _TIME_ADVERBS
    )  # "whts status bald range fire", but not "Salmon Arm fire now?"


def _named_by_verb(text: str) -> FireNameMention | None:
    """'a fire called Phantom Ridge': the name follows a naming verb."""

    match = _NAMING_VERB.search(text)
    if match is None:
        return None
    tokens = list(_TOKEN.finditer(text, match.end()))
    end_index = 0
    for end_index, token in enumerate(tokens):
        gap = text[tokens[end_index - 1].end() : token.start()] if end_index else ""
        if (
            end_index == _MAX_NAME_TOKENS + 1
            or any(mark in gap for mark in ',.;:?!()"“”')
            or (_key(token.group(0)) in _STOPS and _key(token.group(0)) not in _HEADS)
        ):
            break
    else:
        end_index = len(tokens)
    name = tokens[:end_index]
    while name and _key(name[-1].group(0)) in _HEADS:
        name.pop()
    if not name:
        return None
    label = " ".join(text[name[0].start() : name[-1].end()].split()).strip("\"'’")
    return FireNameMention(label=label, span=(name[0].start(), name[-1].end()))
