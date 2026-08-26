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
    r"(?:what(?:['’]s|\s+is)?|where|when|why|how|which|who|"
    r"is|are|was|were|do|does|did|can|could|may|might|should|would|will|"
    r"has|have|had|there\s+(?:is|are|was|were)|"
    r"give|show|display|list|map|tell|explain|define|describe|summari[sz]e|"
    r"outline|compare|"
    r"check|find|put|move|focus|centre|center|zoom|help|catch|bring)\b"
)
_GUIDANCE_NOUN_MODIFIERS = (
    r"(?:(?:an?|the)\s+)?"
    r"(?:(?:basic|simple|plain(?:-|\s+)(?:english|language))\s+)?"
)
_TERSE_GUIDANCE_START = (
    r"(?:(?:advice|tips|guidance|contents?|checklist)\s+"
    r"(?:for|about|on|of)\s+)?"
    r"(?:(?:an?|the)\s+)?(?:emergency[-\s]+kit|"
    r"grab[-\s]+and[-\s]+go[-\s]+bag|go[-\s]+bag|"
    r"(?:wildfire\s+)?smoke[-\s]+(?:readiness|health|preparedness)|"
    r"(?:structure[- ]protection\s+)?sprinklers?(?:\s+guidance)?|"
    r"evacuation[-\s]+(?:alert|order)\s+"
    r"(?:definitions?|meaning|guidance|basics?|summar(?:y|ies)|overview)|"
    rf"{_GUIDANCE_NOUN_MODIFIERS}(?:difference|comparison|distinction)\s+"
    r"(?:between|of)\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)|"
    rf"{_GUIDANCE_NOUN_MODIFIERS}(?:(?:evacuation|emergency|travel)[-\s]+)*"
    r"packing[-\s]+(?:checklist|list)|"
    r"(?:emergency[-\s]+kit|grab[-\s]+and[-\s]+go[-\s]+bag|"
    r"go[-\s]+bag|smoke[-\s]+(?:readiness|preparedness))\s+"
    r"(?:advice|tips|guidance|contents?|checklist))\b"
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
    r"\b(?:across|throughout)\s+(?:the\s+)?nation\b|"
    r"\b(?:national|nation[- ]?wide)\s+(?:wildfire|fire)\s+"
    r"(?:situation|status|updates?|reports?|summar(?:y|ies)|map|records?|"
    r"picture|overview|snapshot|counts?)\b|"
    r"\bcanada['’]s\s+(?:current\s+|latest\s+)?(?:wildfire|fire)\s+"
    r"(?:situation|status|updates?|reports?|summar(?:y|ies)|map|records?|"
    r"picture|overview|snapshot|counts?)\b",
    re.IGNORECASE,
)

_FIRE_WORD = re.compile(
    r"\b(?:(?:wildfires?|fires?)(?!\s+smoke\b)|[a-z]{2,20}fires?|burning)\b",
    re.IGNORECASE,
)
_FIRE_AS_CONTEXT = re.compile(
    r"\b(?:air quality|aqhi|smoke|wind|weather|roads?|highways?)\b"
    r".{0,80}\b(?:wildfires?|fires?)\b|"
    r"\b(?:wildfires?|fires?)\b.{0,80}"
    r"\b(?:air quality|aqhi|smoke|wind|weather|roads?|highways?)\b",
    re.IGNORECASE,
)
_PRESENT_TIME_TEXT = (
    r"(?:right\s+now|currently|today|tonight|now|at\s+the\s+moment|"
    r"at\s+present|this\s+(?:morning|afternoon|evening|week))"
)
_FIRE_SUMMARY_TEXT = (
    r"(?:situation|status|updates?|reports?|summar(?:y|ies)|map|records?|"
    r"picture|overview|snapshot|counts?)"
)
_FIRE_SCOPE_TEXT = r"(?:near|around|round|within|in|across|throughout|by|close\s+to)"
_FIRE_SUMMARY_TERMINUS_TEXT = (
    rf"(?=\s*(?:$|[?.,;:]|and\b|plus\b|for\b|from\b|of\b|"
    rf"{_FIRE_SCOPE_TEXT}\b|{_PRESENT_TIME_TEXT}\b|listed\b|reported\b))"
)
_CURRENT_INCIDENT_RECORD = re.compile(
    rf"\b(?:active|current|latest|official|reported)\s+"
    rf"(?:wildfire\s+)?incidents?\b|"
    rf"\b(?:wildfire\s+)?incidents?\s+"
    rf"(?:are\s+)?(?:active|current|latest|official|reported|{_PRESENT_TIME_TEXT})\b",
    re.IGNORECASE,
)
_OFFICIAL_FIRE_SERVICE_RECORD = re.compile(
    rf"\b(?:bcws|bc\s+wildfire\s+service)\b.{{0,50}}"
    rf"\b(?:posts?|posted|new|updates?|latest|{_PRESENT_TIME_TEXT})\b|"
    rf"\b(?:what|which)\b.{{0,50}}\b(?:posts?|updates?|records?)\b.{{0,50}}"
    rf"\b(?:bcws|bc\s+wildfire\s+service)\b",
    re.IGNORECASE,
)
_OFFICIAL_RECORD_COMMAND = re.compile(
    r"(?:^|[:;])\s*(?:what|which|show|display|list|check|find)\b.{0,40}"
    r"\bofficial\s+(?:live\s+)?records?\b",
    re.IGNORECASE,
)
_INCIDENT_MAP_COMMAND = re.compile(
    r"^\s*(?:please\s+)?(?:put|move|focus|centre|center)\s+"
    r"(?:the\s+)?map\s+(?:on|at|around|near|where)\b|"
    r"^\s*(?:please\s+)?map\s+(?!of\b)[a-z][a-z .'-]{1,80}?\s*[?!.]*$",
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
    r"previous(?:ly)?|formerly|past)\b",
    re.IGNORECASE,
)
_CURRENT_FIRE_PREDICTION_HANDOFF = re.compile(
    r"\b(?:will|could|might|can)\s+(?:the|this|that)\s+"
    r"(?:(?:[a-z0-9.'-]+\s+){0,3})?(?:wildfire|fire)\s+"
    r"(?:reach|arrive\s+at|threaten|affect|spread\s+to)\b.{0,100}"
    rf"\b(?:me|us|my|our|home|house|property|neighbou?rhood|community|"
    rf"{_PRESENT_TIME_TEXT})\b",
    re.IGNORECASE,
)
_EXPOSITORY = re.compile(
    r"^\s*(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:explain|define|describe|summari[sz]e)\b|"
    r"\bwhat\s+(?:does|do)\b.{0,80}\bmean\b|"
    r"\bwhat\s+is\s+an?\s+(?:wildfire|fire)\b|"
    r"^\s*(?:is|are)\s+there\s+(?:an?\s+)?"
    r"(?:difference|distinction|comparison)\b|"
    r"^\s*how\s+(?:do|does|can)\b.{0,100}"
    r"\b(?:affect|behave|change|form|happen|influence|shape|spread|start|work)\b|"
    r"\b(?:wildfire|fire)\s+(?:ecology|behaviou?r|causes?|science)\b",
    re.IGNORECASE,
)
_RECORD_COMMAND = re.compile(
    rf"(?:^|[:;])\s*(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?(?:"
    # A record-list command owns a plural fire object directly.  Descriptive
    # topic nouns cannot sit between the command and that object.
    rf"(?:give|show|display|list|map|check|find|compare)\s+"
    rf"(?:(?:me|us)\s+)?(?:(?:the|all|any)\s+)?"
    rf"(?:(?:active|current|latest|official|reported|today['’]s)\s+)*"
    rf"(?:(?:bc|b\.c\.|british\s+columbia|provincial)\s+)?"
    rf"(?:wildfires|fires)\b|"
    # Singular fire nouns are live only when they own an adjacent record-view
    # noun.  Up to three non-preposition tokens allow a fronted place or
    # current/official modifier without accepting "policy about wildfire".
    rf"(?:give|show|display|list|map|check|find|tell)\s+"
    rf"(?:(?:me|us)\s+)?(?:(?:the|a|an)\s+)?"
    rf"(?:(?!about\b|of\b|for\b|on\b|regarding\b)[a-z0-9.'-]+\s+){{0,3}}"
    rf"(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b"
    rf"{_FIRE_SUMMARY_TERMINUS_TEXT}|"
    rf"(?:catch\s+(?:me|us)\s+up|bring\s+(?:me|us)\s+up\s+to\s+date)"
    rf"(?:\s+on)?\s+(?:(?:the|a|an)\s+)?"
    rf"(?:(?!about\b|of\b|for\b|on\b|regarding\b)[a-z0-9.'-]+\s+){{0,3}}"
    rf"(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b"
    rf"{_FIRE_SUMMARY_TERMINUS_TEXT})"
    rf"|^\s*(?:please\s+)?(?:map|show|find|check)\s+what(?:'s|\s+is)\s+burning\b|"
    rf"^\s*(?:please\s+)?(?:show|display)\s+(?:me\s+)?"
    rf"[a-z][a-z .'-]{{1,60}}?\s+(?:wildfire|fire)\s+"
    rf"(?:stuff|details?|information)\s+on\s+(?:the\s+)?map\b|"
    rf"^\s*(?:please\s+)?(?:check|show|find)\s+"
    rf"(?:my|our)\s+(?:area|place|location|neighbou?rhood)\s+for\s+"
    rf"(?:(?:any|active|current|official|reported)\s+)*(?:wildfires|fires)\b|"
    rf"^\s*(?:i|we)\s+(?:need|want)\s+(?:(?:the|all)\s+)?"
    rf"(?:(?:active|current|latest|official|reported)\s+)*(?:wildfires|fires)\b",
    re.IGNORECASE,
)
_PRESENT_FIRE_QUESTION = re.compile(
    r"\bwhat(?:['’]s|\s+is)\s+burning\b|"
    r"\bwhat(?:['’]s|\s+is)\s+on\s+fire\b|"
    rf"\bwhether\s+anything\s+is\s+burning\s+{_FIRE_SCOPE_TEXT}\b|"
    rf"\b(?:is|are)\s+anything\s+burning\s+{_FIRE_SCOPE_TEXT}\b|"
    rf"\b(?:is|are)\s+there\s+(?:any\s+)?"
    rf"(?:(?:current|present)\s+)?(?:wildfire|fire)\s+"
    rf"(?:activity|occurrences?)\b(?=.{{0,100}}\b(?:{_FIRE_SCOPE_TEXT}|"
    rf"{_PRESENT_TIME_TEXT})\b)|"
    rf"(?:^|:)\s*(?:wildfires|fires)\s+{_FIRE_SCOPE_TEXT}\b|"
    # Wh-questions own a fire record set directly; they cannot reach forward
    # through an arbitrary topic phrase to find the word "wildfire".
    r"\b(?:what|which)\s+"
    r"(?:(?:active|current|latest|official|reported)\s+)*"
    rf"(?:wildfires|fires)\s+(?:burning|listed|reported|{_FIRE_SCOPE_TEXT}|"
    rf"(?:is|are|remain)\s+(?:active|burning|current|listed|reported|"
    rf"{_FIRE_SCOPE_TEXT}|{_PRESENT_TIME_TEXT}))\b|"
    r"\bhow\s+many\s+(?:(?:active|current|official|reported)\s+)*"
    r"(?:wildfires?|fires?)\b|"
    r"\bwhere\s+are\s+(?:(?:the|any)\s+)?"
    r"(?:(?:active|current|latest|official|reported)\s+)*"
    r"(?:wildfires?|fires?)\b|"
    # A singular where-question must point to the fire itself: either the
    # noun is followed immediately by a scope/time cue, or it is a named fire
    # whose final noun is Fire/Wildfire.  "Where is wildfire prevention..."
    # therefore cannot become a record lookup.
    rf"\bwhere(?:'s|s|\s+is)\s+(?:(?:the|a|an)\s+)?"
    rf"(?:[a-z0-9.'-]+\s+){{0,3}}(?:wildfire|fire)\s*"
    rf"(?=$|[?.,;]|\b(?:{_FIRE_SCOPE_TEXT}|{_PRESENT_TIME_TEXT}|located)\b)|"
    rf"\bwhere(?:'s|s|\s+is)\s+(?:wildfire|fire)\s+"
    rf"[a-z]*\d[a-z0-9-]*\b|"
    rf"\bwhere(?:'s|s|\s+is)\s+(?:the\s+)?(?:nearest|closest)\s+"
    rf"(?:wildfire|fire|[a-z]{{2,20}}fires?)\s+{_FIRE_SCOPE_TEXT}\b|"
    # Existential syntax is bounded to the immediate noun phrase.  This is
    # the key distinction between "Are there active fires near X?" and "Is
    # there a safe distance from a wildfire?".
    rf"\b(?:is|are)\s+there\s+"
    rf"(?:(?:any|more|active|current|latest|official|reported|nearby)\s+)*"
    rf"(?:wildfires|fires)\b(?=\s*(?:$|[?.,;]|and\b|plus\b|"
    rf"{_FIRE_SCOPE_TEXT}\b|{_PRESENT_TIME_TEXT}\b|active\b|burning\b|"
    rf"listed\b|reported\b|called\b|named\b))|"
    rf"\b(?:is|are)\s+there\s+(?:an?\s+)?"
    rf"(?:(?!about\b|between\b|for\b|from\b|of\b)[a-z0-9.'-]+\s+){{0,3}}"
    rf"(?:wildfire|fire)\b(?=\s*(?:$|[?.,;]|and\b|plus\b|"
    rf"{_FIRE_SCOPE_TEXT}\b|{_PRESENT_TIME_TEXT}\b|active\b|burning\b|"
    rf"called\b|named\b))|"
    rf"\b(?:is|are)\s+(?:an?\s+)?(?:wildfire|fire)\s+"
    rf"(?:active|burning|current|{_FIRE_SCOPE_TEXT})\b|"
    rf"\b(?:is|are)\s+(?:(?:the|a|an)\s+)?"
    rf"(?:[a-z0-9.'-]+\s+){{1,4}}(?:wildfire|fire)\s+"
    rf"(?:active|burning|current|listed|reported|{_PRESENT_TIME_TEXT})\b|"
    rf"\b(?:is|are)\s+there\s+(?:an?\s+)?[a-z]{{2,20}}fires?\s+"
    rf"{_FIRE_SCOPE_TEXT}\b|"
    rf"\b(?:are|were)\s+(?:(?:active|current|official|reported)\s+)*"
    rf"(?:wildfires|fires)\s+(?:active|burning|current|listed|reported|"
    rf"{_FIRE_SCOPE_TEXT})\b|"
    rf"\b(?:do|does)\s+(?:we|you|they|[a-z][a-z'-]+)\s+have\s+"
    rf"(?:(?:any|active|current|official|reported)\s+)*(?:wildfires|fires)\b|"
    rf"\b(?:do|does)\s+(?:we|you|they|[a-z][a-z'-]+)\s+have\s+"
    rf"(?:an?\s+)?(?:(?!about\b|between\b|for\b|from\b|of\b)"
    rf"[a-z0-9.'-]+\s+){{0,3}}(?:wildfire|fire)\b"
    rf"(?=\s*(?:$|[?.,;]|{_FIRE_SCOPE_TEXT}\b|{_PRESENT_TIME_TEXT}\b|"
    rf"active\b|burning\b|called\b|named\b))|"
    rf"\bany\s+(?:(?:active|current|official|reported)\s+)*"
    rf"(?:wildfires|fires)\b|"
    rf"\bwhat\s+(?:is|'s)\s+(?:the\s+)?(?:current\s+|latest\s+)?"
    rf"(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b"
    rf"{_FIRE_SUMMARY_TERMINUS_TEXT}|"
    rf"\b(?:what|which)\s+(?:wildfire|fire|[a-z]{{2,20}}fires?)\s+(?:is\s+)?"
    rf"(?:nearest|closest)\s+to\b|"
    rf"\bwhich\s+(?:wildfires|fires)\s+(?:are\s+)?"
    rf"(?:nearest|closest)\s+to\b|"
    rf"\b(?:what|which)\s+is\s+(?:the\s+)?(?:nearest|closest)\s+"
    rf"(?:wildfire|fire)\b|"
    rf"\bhow\s+(?:far|close)(?:\s+away)?\s+is\s+"
    rf"(?:(?:this|that|the\s+selected)\s+)?(?:wildfire|fire)\b|"
    rf"\bdistance\s+from\b.{{1,80}}\b(?:this|that|selected)\s+"
    rf"(?:wildfire|fire)\b|"
    rf"\bhow\s+(?:large|big)\s+is\s+(?:(?:this|that|the\s+selected)\s+)?"
    rf"(?:wildfire|fire)\b",
    re.IGNORECASE,
)
_FIRE_RECORD_ANALYSIS = re.compile(
    r"\b(?:wildfires?|fires?)\b.{0,80}"
    r"\b(?:distribution|distributed|geograph(?:y|ic|ically)|"
    r"concentrat(?:e|ed|ion)|density|each\s+(?:fire[- ]?)?centre|"
    r"by\s+(?:fire[- ]?)?centre|most|fewest)\b|"
    r"\b(?:distribution|distributed|geograph(?:y|ic|ically)|"
    r"concentrat(?:e|ed|ion)|density|most|fewest|how\s+many|counts?)\b"
    r".{0,80}\b(?:wildfires?|fires?)\b|"
    r"\b(?:largest|oldest|nearest|closest)\b.{0,80}"
    r"\b(?:wildfires?|fires?)\b|"
    r"\b(?:wildfires?|fires?)\b.{0,80}\b(?:largest|oldest|hectares?)\b|"
    r"\b(?:wildfire|fire)\s+counts?\b|"
    r"\b(?:break\s+down|group|compare)\b.{0,80}"
    r"\b(?:current\s+)?(?:wildfires?|fires?)\b.{0,80}"
    r"\b(?:regions?|areas?|status|fire[- ]?centres?)\b",
    re.IGNORECASE,
)
_TERSE_PLACE_FIRE_RECORD = re.compile(
    rf"^\s*(?!(?:i\s+heard|tell\s+me|explain|describe|define|summari[sz]e|"
    rf"is|are|was|were|can|could|would|will|do|does|did|what|where|when|"
    rf"why|how|which|who)\b)"
    rf"[a-z][a-z .'-]{{1,60}}?\s+(?:wildfire|fire)\s*"
    rf"(?:{_PRESENT_TIME_TEXT})?[?!.]*\s*$",
    re.IGNORECASE,
)
_CURRENT_FIRE_STATUS = re.compile(
    rf"(?:^|[:,\N{{EM DASH}}\N{{EN DASH}}])\s*"
    rf"(?:active|current|latest|official|reported)\s+"
    rf"(?:(?:bc|b\.c\.|british\s+columbia|provincial)\s+)?"
    rf"(?:(?:wildfires|fires)\b|(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b)|"
    rf"(?:^|[:,\N{{EM DASH}}\N{{EN DASH}}])\s*"
    rf"(?:(?:bc|b\.c\.|british\s+columbia|provincial)\s+)"
    rf"(?:active|current|latest|official|reported)\s+(?:wildfires|fires)\b|"
    rf"^\s*(?:[a-z][a-z .'-]{{1,80}}?\s+)?(?:wildfires|fires)\s+(?:are\s+)?"
    rf"(?:active|burning|current|listed|reported|{_PRESENT_TIME_TEXT})\b|"
    rf"\b(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}"
    rf"(?:\s+{_FIRE_SUMMARY_TEXT})?\b"
    rf"{_FIRE_SUMMARY_TERMINUS_TEXT}|"
    rf"\b(?:wildfire|fire)\s+(?:perimeters?|incidents?)\b|"
    rf"\b(?:wildfire|fire)\s+{_PRESENT_TIME_TEXT}\b|"
    rf"\btoday['’]s\s+(?:wildfires?|fires?)\b",
    re.IGNORECASE,
)

_FRONTED_LOCATION = re.compile(
    r"^\s*(?:please\s+)?(?:give|show|display|tell)\s+(?:me\s+)?(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,80}?)\s+"
    rf"(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b",
    re.IGNORECASE,
)
_FRONTED_TIME_LOCATION = re.compile(
    rf"^\s*(?:{_PRESENT_TIME_TEXT}|latest)\s+in\s+(?:the\s+)?"
    rf"(?P<place>[a-z][a-z .'-]{{1,80}}?)\s*[,;:]\s*",
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
    rf"(?:wildfire|fire)\s+{_FIRE_SUMMARY_TEXT}\b",
    re.IGNORECASE,
)
_FRONTED_SCOPE = re.compile(
    r"^\s*(?P<place>[a-z][a-z .'-]{1,80}?)\s*"
    r"(?P<separator>,|:|\N{EM DASH}|\N{EN DASH}|\s+plus\s+)\s*"
    r"(?P<request>.+)$",
    re.IGNORECASE,
)
_TRAILING_LOCATION = re.compile(
    r"\b(?:near|around|round|within|in|across|close(?:st)?\s+to)\s+(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,100})",
    re.IGNORECASE,
)
_TRAILING_RECORD_LOCATION = re.compile(
    rf"\b(?:wildfire|fire|incident|perimeter)\s+{_FIRE_SUMMARY_TEXT}\s+for\s+"
    r"(?:the\s+)?"
    r"(?P<place>[a-z][a-z .'-]{1,100})",
    re.IGNORECASE,
)
_LOCATION_END = re.compile(
    r"\s+(?:right\s+now|currently|current|latest|today|tonight|now|"
    r"at\s+the\s+moment|at\s+present|this\s+(?:morning|afternoon|evening|week))\b.*$",
    re.IGNORECASE,
)

_MAP_PIN_UI_OPERATION = re.compile(
    r"\b(?:how\s+(?:do|can|would|should)\s+(?:i|we|you)\s+|"
    r"(?:please\s+)?(?:add|create|drop|place|remove|delete|move)\s+)"
    r"(?:an?\s+|the\s+)?(?:map\s+)?(?:pins?|markers?)\b|"
    r"\b(?:add|create|drop|place|remove|delete|move)\s+"
    r"(?:an?\s+|the\s+)?(?:pins?|markers?)\s+(?:to|from|on)\s+"
    r"(?:the\s+)?(?:wildfire|fire|incident)?\s*map\b",
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
    if _MAP_PIN_UI_OPERATION.search(text):
        return False
    fire_word = bool(_FIRE_WORD.search(text))
    incident_record = bool(_CURRENT_INCIDENT_RECORD.search(text))
    official_record = bool(_OFFICIAL_FIRE_SERVICE_RECORD.search(text))
    official_record = official_record or bool(_OFFICIAL_RECORD_COMMAND.search(text))
    incident_map = bool(_INCIDENT_MAP_COMMAND.search(text))
    if not fire_word and not incident_record and not official_record and not incident_map:
        return False
    prediction_handoff = bool(_CURRENT_FIRE_PREDICTION_HANDOFF.search(text))
    if _FUTURE_OR_HISTORICAL.search(text) and not prediction_handoff:
        return False
    record_command = bool(_RECORD_COMMAND.search(text))
    present_question = bool(_PRESENT_FIRE_QUESTION.search(text))
    # Expository ownership remains static even when the topic happens to use
    # the word "current".  An explicit live question nested in conversational
    # wording (for example, "Can you tell me which fires are active?") still
    # qualifies through the positive present-question form.
    if _EXPOSITORY.search(text) and not present_question:
        return False
    return bool(
        record_command
        or present_question
        or _CURRENT_FIRE_STATUS.search(text)
        or (_FIRE_RECORD_ANALYSIS.search(text) and not _FIRE_AS_CONTEXT.search(text))
        or _TERSE_PLACE_FIRE_RECORD.search(text)
        or incident_record
        or official_record
        or incident_map
        or prediction_handoff
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
    time_fronted = _FRONTED_TIME_LOCATION.search(text)
    if time_fronted is not None:
        return time_fronted.group("place").strip()
    scoped = _fronted_live_scope(text)
    if scoped is not None:
        return scoped
    # ``for`` usually introduces an audience or purpose, not geography.  It
    # is accepted as a location preposition only after an explicit record or
    # fire-summary noun (for example, ``wildfire update for <place>``).  This
    # keeps established scoped queries while preventing phrases such as
    # ``for students`` from silently becoming a community lookup.
    matches = tuple(
        (*_TRAILING_LOCATION.finditer(text), *_TRAILING_RECORD_LOCATION.finditer(text))
    )
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
            non_current_fire=not is_live and _is_non_current_fire(text),
            live_location_candidate=_live_location_candidate(text) if is_live else None,
        )
        for text in _request_clauses(question)
    )
    return RequestFacets(original_question=question, clauses=clauses)


def requests_non_bc_national_scope(question: str) -> bool:
    """Return explicit national spans that cannot mean a province-wide BC ask."""

    return bool(_NON_BC_NATIONAL_SCOPE.search(question))
