"""Structural grammar shared by deterministic request-routing consumers.

This module identifies request clauses and the narrow shape of a current fire
request.  It deliberately does not know BC place names, choose live layers, or
make policy decisions.  Those remain the responsibility of the existing
intent and location modules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

_CLAUSE_START = (
    r"(?:what(?:'s|\s+is)?|where|when|why|how|which|who|"
    r"is|are|was|were|do|does|did|can|could|may|might|should|would|will|"
    r"has|have|had|there\s+(?:is|are|was|were)|"
    r"give|show|display|list|map|tell|explain|define|describe|compare|"
    r"check|find|put|move|focus|centre|center|zoom|help|catch|bring)\b"
)
_GUIDANCE_NOUN_MODIFIERS = (
    r"(?:(?:an?|the)\s+)?"
    r"(?:(?:basic|simple|plain(?:-|\s+)(?:english|language))\s+)?"
)
_TERSE_GUIDANCE_START = (
    r"(?:emergency\s+kit|grab-and-go\s+bag|go\s+bag|"
    r"(?:wildfire\s+)?smoke\s+(?:readiness|health|preparedness)|"
    r"evacuation\s+(?:alert|order)\s+(?:definitions?|meaning|guidance)|"
    rf"{_GUIDANCE_NOUN_MODIFIERS}(?:difference|comparison|distinction)\s+"
    r"(?:between|of)\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)|"
    rf"{_GUIDANCE_NOUN_MODIFIERS}(?:(?:evacuation|emergency|travel)\s+)*"
    r"packing\s+(?:checklist|list))\b"
)
_CLAUSE_BOUNDARY = re.compile(
    rf"(?:(?:[?;.+]\s*|,\s*|\s+(?:and|also|plus|but|then)\s+)"
    rf"(?={_CLAUSE_START})|"
    rf"(?:[?;.+]\s*|,\s*(?:(?:and|also|plus|but|then|with)\s+)?|"
    rf"\s+(?:and|also|plus|with)\s+)"
    rf"(?={_TERSE_GUIDANCE_START}))",
    re.IGNORECASE,
)

_NON_BC_NATIONAL_SCOPE = re.compile(
    r"\bfrom\s+(?:the\s+)?atlantic\s+to\s+(?:the\s+)?pacific\b|"
    r"\b(?:across|throughout)\s+(?:the\s+)?nation\b",
    re.IGNORECASE,
)

_FIRE_WORD = re.compile(
    r"\b(?:(?:wildfires?|fires?)(?!\s+smoke\b)|burning)\b",
    re.IGNORECASE,
)
_FIRE_AS_CONTEXT = re.compile(
    r"\b(?:air quality|aqhi|smoke|wind|weather|roads?|highways?)\b"
    r".{0,80}\b(?:wildfires?|fires?)\b|"
    r"\b(?:wildfires?|fires?)\b.{0,80}"
    r"\b(?:air quality|aqhi|smoke|wind|weather|roads?|highways?)\b",
    re.IGNORECASE,
)
_CURRENT_INCIDENT_RECORD = re.compile(
    r"\b(?:active|current|latest|official)\s+(?:wildfire\s+)?incidents?\b|"
    r"\bincidents?\b.{0,60}\b(?:active|current|latest|today|now)\b",
    re.IGNORECASE,
)
_CURRENT_TIME = re.compile(
    r"\b(?:right\s+now|currently|current|latest|today|tonight|now|"
    r"at\s+the\s+moment|at\s+present|this\s+(?:morning|afternoon|evening|week))\b",
    re.IGNORECASE,
)
_FUTURE_OR_HISTORICAL = re.compile(
    r"\b(?:will|forecast|tomorrow|next\s+(?:day|week|month|year)|"
    r"yesterday|last\s+(?:night|week|month|year|season)|histor(?:y|ic|ical)|"
    r"previous(?:ly)?|formerly|past|burned|burnt)\b",
    re.IGNORECASE,
)
_EXPOSITORY = re.compile(
    r"^\s*(?:explain|define|describe)\b|"
    r"\bwhat\s+(?:does|do)\b.{0,80}\bmean\b|"
    r"\bwhat\s+is\s+an?\s+(?:wildfire|fire)\b|"
    r"^\s*how\s+(?:do|does|can)\b.{0,100}"
    r"\b(?:affect|behave|form|happen|spread|start|work)\b|"
    r"\b(?:wildfire|fire)\s+(?:ecology|behaviou?r|causes?|science)\b",
    re.IGNORECASE,
)
_RECORD_COMMAND = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"(?:give|show|display|list|map|check|find)\b|"
    r"(?:catch\s+(?:me|us)\s+up|bring\s+(?:me|us)\s+up\s+to\s+date)"
    r"(?:\s+on)?\b)"
    r".{0,120}\b(?:wildfires?|fires?|burning|"
    r"(?:wildfire|fire)\s+(?:situation|status|updates?|map|records?|"
    r"picture|overview|snapshot))\b",
    re.IGNORECASE,
)
_PRESENT_FIRE_QUESTION = re.compile(
    r"\bwhat(?:'s|\s+is)\s+burning\b|"
    r"\b(?:what|which)\s+(?:wildfires?|fires?)\s+(?:is|are)\b|"
    r"\bwhere\s+(?:is|are)\b.{0,50}\b(?:wildfires?|fires?)\b|"
    r"\b(?:is|are)\s+there\b.{0,60}\b(?:wildfires?|fires?)\b|"
    r"\b(?:wildfires?|fires?)\s+(?:is|are)\b.{0,60}"
    r"\b(?:active|burning|current|near|around|within|in|across)\b|"
    r"\bwhat\s+(?:is|'s)\s+(?:the\s+)?(?:current\s+|latest\s+)?"
    r"(?:wildfire|fire)\s+(?:situation|status|update|map)\b",
    re.IGNORECASE,
)
_CURRENT_FIRE_STATUS = re.compile(
    r"\b(?:active|burning|current|latest)\b.{0,80}\b(?:wildfires?|fires?)\b|"
    r"\b(?:wildfires?|fires?)\b.{0,80}\b(?:active|burning|current|latest)\b|"
    r"\b(?:wildfire|fire)\s+(?:situation|status|updates?|map|records?|"
    r"picture|overview|snapshot)\b",
    re.IGNORECASE,
)

_FRONTED_LOCATION = re.compile(
    r"^\s*(?:please\s+)?(?:give|show|display|tell)\s+(?:me\s+)?(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)\s+"
    r"(?:wildfire|fire)\s+(?:situation|status|updates?|map|records?|"
    r"picture|overview|snapshot)\b",
    re.IGNORECASE,
)
_PLACE_OWNED_FIRE_SUMMARY = re.compile(
    r"^\s*(?:please\s+)?"
    r"(?:(?:catch\s+(?:me|us)\s+up|bring\s+(?:me|us)\s+up\s+to\s+date)"
    r"(?:\s+on)?\s+)?"
    r"(?!(?:give|show|display|list|map|check|find|tell)\b)"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)(?:"
    r"(?:['\N{RIGHT SINGLE QUOTATION MARK}]s|"
    r"(?<=s)['\N{RIGHT SINGLE QUOTATION MARK}])\s+|\s+)"
    r"(?:wildfire|fire)\s+(?:situation|status|updates?|map|records?|"
    r"picture|overview|snapshot)\b",
    re.IGNORECASE,
)
_FRONTED_SCOPE = re.compile(
    r"^\s*(?P<place>[a-z][a-z .'-]{1,80}?)\s*"
    r"(?P<separator>,|:|\N{EM DASH}|\N{EN DASH}|\s+plus\s+)\s*"
    r"(?P<request>.+)$",
    re.IGNORECASE,
)
_TRAILING_LOCATION = re.compile(
    r"\b(?:near|around|round|within|in|across|for)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,100})",
    re.IGNORECASE,
)
_LOCATION_END = re.compile(
    r"\s+(?:right\s+now|currently|current|latest|today|tonight|now|"
    r"at\s+the\s+moment|at\s+present|this\s+(?:morning|afternoon|evening|week))\b.*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RequestClause:
    """One top-level request clause and its structural live-fire facets."""

    text: str
    current_live_fire: bool
    non_current_fire: bool
    live_location_candidate: str | None = None


@dataclass(frozen=True, slots=True)
class RequestFacets:
    """A question's shared structural representation."""

    original_question: str
    clauses: tuple[RequestClause, ...]

    @property
    def clause_texts(self) -> tuple[str, ...]:
        return tuple(clause.text for clause in self.clauses)

    @property
    def live_clauses(self) -> tuple[RequestClause, ...]:
        return tuple(clause for clause in self.clauses if clause.current_live_fire)

    @property
    def non_live_clauses(self) -> tuple[RequestClause, ...]:
        return tuple(clause for clause in self.clauses if not clause.current_live_fire)

    @property
    def has_current_live_fire(self) -> bool:
        return bool(self.live_clauses)

    @property
    def only_non_current_fire(self) -> bool:
        return not self.has_current_live_fire and any(
            clause.non_current_fire for clause in self.clauses
        )

    @property
    def live_location_candidates(self) -> tuple[str, ...]:
        return tuple(
            candidate
            for clause in self.live_clauses
            if (candidate := clause.live_location_candidate) is not None
        )


def _request_clauses(question: str) -> tuple[str, ...]:
    # A leading ``Place: current fire request`` belongs to the first live
    # clause, not to every subsequent request.  Split inside the request tail
    # so ``Place: what's burning today, and what belongs in a kit?`` keeps the
    # first scope while retaining the independent guidance request.  Splitting
    # the whole string would turn ``Place plus what's burning`` into ``Place``
    # and an unscoped live clause.
    # A literal ``+`` is an unambiguous top-level request separator in terse
    # user input. Its right-hand side is often a noun phrase rather than a
    # grammatical question, so it cannot rely on ``_CLAUSE_START`` like prose
    # conjunctions do. Split it first, then parse each part normally.
    plus_parts = tuple(
        part for raw in re.split(r"\s*\+\s*", question) if (part := raw.strip(" ,.?;+"))
    )
    if len(plus_parts) > 1:
        clauses = tuple(
            clause for part in plus_parts for clause in _request_clauses(part) if clause
        )
        return clauses or ((question.strip(" ,.?;+") or question),)

    fronted = _FRONTED_SCOPE.search(question)
    if fronted is not None and _is_current_live_fire(fronted.group("request")):
        request_start = fronted.start("request")
        boundaries = tuple(_CLAUSE_BOUNDARY.finditer(fronted.group("request")))
        if boundaries:
            first_boundary = boundaries[0]
            first = question[: request_start + first_boundary.start()].strip(" ,.?;+")
            remainder = fronted.group("request")[first_boundary.end() :]
            tail = tuple(
                text
                for part in _CLAUSE_BOUNDARY.split(remainder)
                if (text := part.strip(" ,.?;+"))
            )
            if first and tail:
                return (first, *tail)
        return ((question.strip(" ,.?;+") or question),)
    clauses = tuple(
        text for part in _CLAUSE_BOUNDARY.split(question) if (text := part.strip(" ,.?;+"))
    )
    return clauses or ((question.strip(" ,.?;+") or question),)


def _fronted_live_scope(text: str) -> str | None:
    match = _FRONTED_SCOPE.search(text)
    if match is None or not _is_current_live_fire(match.group("request")):
        return None
    return match.group("place").strip()


def _is_current_live_fire(text: str) -> bool:
    fire_word = bool(_FIRE_WORD.search(text))
    incident_record = bool(_CURRENT_INCIDENT_RECORD.search(text))
    if not fire_word and not incident_record:
        return False
    if _FUTURE_OR_HISTORICAL.search(text):
        return False
    if _EXPOSITORY.search(text) and not _CURRENT_TIME.search(text):
        return False
    return bool(
        _RECORD_COMMAND.search(text)
        or _PRESENT_FIRE_QUESTION.search(text)
        or _CURRENT_FIRE_STATUS.search(text)
        or incident_record
        or (_CURRENT_TIME.search(text) and fire_word)
    )


def _is_non_current_fire(text: str) -> bool:
    return bool(
        _FIRE_WORD.search(text)
        and not _FIRE_AS_CONTEXT.search(text)
        and (
            _FUTURE_OR_HISTORICAL.search(text)
            or (_EXPOSITORY.search(text) and not _CURRENT_TIME.search(text))
        )
    )


def _live_location_candidate(text: str) -> str | None:
    scoped = _fronted_live_scope(text)
    if scoped is not None:
        return scoped
    matches = tuple(_TRAILING_LOCATION.finditer(text))
    if matches:
        candidate = matches[-1].group("place")
        candidate = _LOCATION_END.sub("", candidate)
        if cleaned := candidate.strip(" ,.?;+"):
            return cleaned
    # Prefer an explicit trailing scope ("records for the Okanagan") over a
    # command's descriptive words ("show current official fire records").
    # If there is no tail scope, retain the established fronted form such as
    # "Show me the Vernon wildfire update".
    fronted = _FRONTED_LOCATION.search(text)
    if fronted is not None:
        return fronted.group("place").strip()
    owned_summary = _PLACE_OWNED_FIRE_SUMMARY.search(text)
    if owned_summary is not None:
        return owned_summary.group("place").strip()
    return None


@lru_cache(maxsize=512)
def parse_request_facets(question: str) -> RequestFacets:
    """Parse a question once into clauses used by every routing consumer."""

    clauses = tuple(
        RequestClause(
            text=text,
            current_live_fire=(is_live := _is_current_live_fire(text)),
            non_current_fire=_is_non_current_fire(text),
            live_location_candidate=_live_location_candidate(text) if is_live else None,
        )
        for text in _request_clauses(question)
    )
    return RequestFacets(original_question=question, clauses=clauses)


def requests_non_bc_national_scope(question: str) -> bool:
    """Return explicit national spans that cannot mean a province-wide BC ask."""

    return bool(_NON_BC_NATIONAL_SCOPE.search(question))
