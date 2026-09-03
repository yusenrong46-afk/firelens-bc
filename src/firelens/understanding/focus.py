"""UNDERSTAND: a turn about the record already in focus.

A record comes into focus when the person selects it on the map or narrows the
conversation to it ("the second one", "tell me about Bald Range"). Later turns
refer to it with an anaphor ("it", "its", "that one", "this fire") or leave the
subject out ("status?", "how big?", "distance from Kelowna?"). Such a turn is
about the focused record unless it names a subject of its own: a roster of
records ("fires near Kamloops", "evacuation orders"), a comparison across the
roster ("which is closest"), a specific fire by name, or the whole province.
Personal decisions ("is it safe to go home?") are never record attributes;
they stay with the safety boundary.

This module only reads the question. The planner decides whether a focus
exists and fetches exactly that record; the presenter answers the attribute
asked, or says which attributes the official record cannot answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from firelens.understanding.place import PlaceKind, extract_place, is_province_scope


class FocusAttribute(StrEnum):
    """What the person wants to know about the focused record."""

    UNSUPPORTED = "unsupported"  # cause, forecast, spread: not in the official record
    DISTANCE = "distance"
    SIZE = "size"
    UPDATED = "updated"
    SOURCE = "source"
    LOCATION = "location"
    STATUS = "status"
    DETAILS = "details"


@dataclass(frozen=True, slots=True)
class FocusReference:
    attributes: tuple[FocusAttribute, ...]
    # A community the distance is measured from ("how far is it from Kelowna").
    reference_place: str | None = None
    # True for "it" / "that one" / "this fire"; False for a bare "status?".
    anaphoric: bool = True

    @property
    def attribute(self) -> FocusAttribute:
        return self.attributes[0]


_RECORD_NOUN = r"(?:one|fire|wildfire|incident|perimeter|record|blaze|evacuation|order|alert)"
# "the fire near Kelowna" and "the wildfire perimeter" describe a record; "the
# fire" alone points at the focus.
_DESCRIBED = (
    r"(?!\s+(?:near|around|in|at|by|outside|close|nearest|closest|north|south|east|west|"
    rf"{_RECORD_NOUN}s?)\b)"
)
# "perimeter near Vernon": a roster described by a place, not a distance origin.
_ROSTER_ANCHOR_BEFORE = re.compile(
    rf"{_RECORD_NOUN}s?\s+(?:near|around|in|at|by|outside|nearest|closest)\s*$", re.IGNORECASE
)
# Pointing words that can carry the turn on their own.
_POINTING = re.compile(
    rf"\b(?:this|that|selected)\s+{_RECORD_NOUN}\b|\bthe\s+{_RECORD_NOUN}\b{_DESCRIBED}|"
    r"\b(?:this|that)\s+one\b|\bthe\s+selected\b|\btell\s+me\s+(?:more\s+)?about\s+(?:it|this|that)\b|"
    r"\bmore\s+about\s+(?:it|this|that)\b|\btell\s+me\s+more\b|\bwhat\s+about\s+(?:it|this|that)\b",
    re.IGNORECASE,
)
# A bare pronoun needs an attribute to be about the record ("what is it?" is not).
_PRONOUN = re.compile(r"\b(?:it|its|itself)\b", re.IGNORECASE)
# The turn brings its own subject, so the focus is not what it is about.
_OWN_SUBJECT = re.compile(
    r"\b(?:fires|wildfires|incidents|perimeters|evacuations|orders|alerts|records|"
    r"closest|nearest|biggest|largest|smallest|newest|oldest|latest|how\s+many|"
    r"which\s+(?:one|fire|wildfire|record|incident|perimeter)\b(?!\s+cent)|"
    r"other|others|another|else|each|every|all\s+the)\b",
    re.IGNORECASE,
)
# A person's decision or exposure, not a field of the record.
_PERSONAL_DECISION = re.compile(
    r"\b(?:safe|safety|should\s+(?:i|we)|evacuate|leave|stay|return|go\s+(?:back|home)|"
    r"drive|travel|risk|danger(?:ous)?|worr(?:y|ied)|okay\s+to|ok\s+to)\b",
    re.IGNORECASE,
)
# Asking what a term means is a guidance question, not a field of the record.
_DEFINITION = re.compile(
    r"\b(?:means?|meaning|definitions?|defined?|stages?\s+of\s+(?:wildfire\s+|fire\s+)?control)\b",
    re.IGNORECASE,
)
# A capitalized "<Name> Fire" names a different record than the focus.
_NAMED_FIRE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9'’.-]*\s+){1,4}(?:Fire|Wildfire|Complex)\b(?!\s+Cent(?:re|er))"
)
_DISTANCE_REFERENCE_BEFORE = re.compile(r"\b(?:from|to)\s*$", re.IGNORECASE)

# What the official record cannot say: how the fire began or how it will behave.
_UNSUPPORTED_TOPIC = re.compile(
    r"\b(?:cause[ds]?|why|start(?:ed)?|began|begin|ignit\w*|origin|discover\w*|detected|"
    r"reach|arrive|spread\w*|threaten\w*|grow(?:n|ing|th)?|predict\w*|forecast\w*|"
    r"expect\w*|likely|chances?|get\s+(?:worse|bigger|closer)|jump|cross)\b",
    re.IGNORECASE,
)
_FUTURE_FIRE_STATE = re.compile(
    r"\b(?:will|going\s+to|gonna|when)\b.{0,40}\b(?:be\s+)?(?:contained|controlled|"
    r"held|out|extinguished|over|done)\b",
    re.IGNORECASE,
)
_ATTRIBUTE_CUES: tuple[tuple[FocusAttribute, re.Pattern[str]], ...] = (
    (
        FocusAttribute.DISTANCE,
        re.compile(
            r"\b(?:how\s+(?:far|close)|distance|kilomet\w*|km|miles?|near(?:by)?|"
            r"close\s+to|far\s+from|away)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FocusAttribute.SIZE,
        re.compile(r"\b(?:how\s+(?:big|large)|size|hectares?|ha|area|acres?)\b", re.IGNORECASE),
    ),
    (
        FocusAttribute.UPDATED,
        re.compile(
            r"\b(?:updated?|updates|last\s+(?:checked|refreshed|changed)|"
            r"how\s+(?:old|recent|fresh|current)|timestamp|as\s+of\s+when|when\s+was)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FocusAttribute.SOURCE,
        re.compile(
            r"\b(?:source|publisher|published|reported|reports|dataset|authority|"
            r"who\s+(?:says|reports|reported))\b",
            re.IGNORECASE,
        ),
    ),
    (
        FocusAttribute.LOCATION,
        re.compile(
            r"\b(?:where|location|located|coordinates|position|map|perimeter|"
            r"fire\s+cent(?:re|er)|what\s+area|region|zone)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FocusAttribute.STATUS,
        re.compile(
            r"\b(?:status|under\s+control|being\s+held|out\s+of\s+control|contained|"
            r"controlled|active|burning|still\s+(?:going|burning|active|there)|extinguished|"
            r"out|holding|stage|condition|state|situation|what(?:'s|\s+is)\s+"
            r"(?:happening|going\s+on)|doing|fire\s+of\s+note)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FocusAttribute.DETAILS,
        re.compile(
            r"\b(?:tell\s+me\s+(?:more\s+)?about|more\s+(?:about|on|info|information|details?)|"
            r"details?|information|info|what\s+about|know\s+about|everything|summar\w+|"
            r"describe|elaborate|overview|facts?)\b",
            re.IGNORECASE,
        ),
    ),
)
# Words an elliptical turn may contain besides its attribute cue and place.
_ELLIPTICAL_FILLER = frozenset(
    {"the", "a", "an", "is", "are", "was", "were", "it", "its", "of", "from", "to", "and",
     "or", "in", "on", "at", "what", "what's", "whats", "how", "when", "where", "who",
     "which", "this", "that", "please", "exactly", "now", "currently", "right", "today",
     "still", "again", "roughly", "approximately", "about", "there", "here", "far", "big",
     "large", "close", "away", "does", "do", "did", "has", "have", "been", "one", "any",
     "current", "official", "record", "fire", "wildfire", "incident", "perimeter", "last",
     "time", "information", "info", "for"}
)  # fmt: skip
_ELLIPTICAL_MAX_TOKENS = 6


def _attributes(text: str) -> tuple[FocusAttribute, ...]:
    found: list[FocusAttribute] = []
    if _UNSUPPORTED_TOPIC.search(text) or _FUTURE_FIRE_STATE.search(text):
        found.append(FocusAttribute.UNSUPPORTED)
    found.extend(attribute for attribute, cue in _ATTRIBUTE_CUES if cue.search(text))
    return tuple(found)


def _reference_place(text: str, pointing: bool) -> tuple[str | None, bool]:
    """(distance reference place, whether the place is the turn's own subject)."""

    mention = extract_place(text, live=True)
    if mention is None or mention.kind == PlaceKind.PERSONAL:
        return None, False
    if mention.kind != PlaceKind.COMMUNITY or mention.label is None or mention.span is None:
        return None, True
    before = text[: mention.span[0]]
    if _ROSTER_ANCHOR_BEFORE.search(before):
        return None, True
    # With a pointer to the record present, a place is where the distance is
    # measured from; without one, a place is a subject unless it follows from/to.
    if pointing or _DISTANCE_REFERENCE_BEFORE.search(before):
        return mention.label, False
    return None, True


def _is_elliptical(
    text: str, attributes: tuple[FocusAttribute, ...], place: str | None
) -> bool:
    """ "status?", "how big?", "distance from Kelowna?": nothing but the ask."""

    if not attributes or len(text.split()) > _ELLIPTICAL_MAX_TOKENS:
        return False
    rest = text
    if place:
        rest = rest.replace(place, " ")
    for _attribute, cue in _ATTRIBUTE_CUES:
        rest = cue.sub(" ", rest)
    leftover = [token for token in re.findall(r"[a-z0-9']+", rest.casefold())]
    return all(token in _ELLIPTICAL_FILLER for token in leftover)


def attributes_asked(question: str) -> tuple[FocusAttribute, ...]:
    """The record attributes a turn asks, whatever record it is about.

    Used once the subject is already settled (a fire named in the turn), where
    only the attribute matters: "Where is wildfire K51402?" asks its location.
    """

    return _attributes(_POINTING.sub(" ", " ".join(question.split())))


def focus_reference(question: str) -> FocusReference | None:
    """Return what the turn asks about the focused record, or None if it is not about it."""

    text = " ".join(question.split())
    if not text or _PERSONAL_DECISION.search(text) or is_province_scope(text):
        return None
    if _OWN_SUBJECT.search(text) or _NAMED_FIRE.search(text) or _DEFINITION.search(text):
        return None
    pointing = _POINTING.search(text) is not None
    pronoun = _PRONOUN.search(text) is not None
    reference_place, own_place = _reference_place(text, pointing or pronoun)
    if own_place:
        return None
    rest = _POINTING.sub(" ", text)
    attributes = _attributes(rest)
    if pointing:
        return FocusReference(attributes or (FocusAttribute.DETAILS,), reference_place)
    if pronoun:
        return FocusReference(attributes, reference_place) if attributes else None
    if _is_elliptical(text, attributes, reference_place):
        return FocusReference(attributes, reference_place, anaphoric=False)
    return None
