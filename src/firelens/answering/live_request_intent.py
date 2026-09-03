"""Requests about one live record, expressed over the shared focus reading.

`firelens.understanding.focus` reads whether a turn is about the record in
focus and which attribute it asks. This module binds that reading to the
request (is a record selected? is a place stated?) for the planner, the agent
loop and the composers, and keeps the one safety distinction that is not an
attribute: a universal evacuation-distance rule is guidance, not geometry.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from firelens.answering.intent import continues_prior_live_place
from firelens.answering.live_analysis import is_record_count_question, official_display_name
from firelens.answering.live_focus import focused_record_answer
from firelens.answering.live_named_fire import requested_fire_identity
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import AggregateFreshness, LiveResult, LiveResultKind, QueryRequest
from firelens.freshness_language import official_information_prefix
from firelens.understanding.focus import FocusAttribute, focus_reference

_DISTANCE_PATTERN = re.compile(
    r"\b(?:how far|how close|distance|kilomet(?:er|re)s?|miles?)\b", re.IGNORECASE
)
_EXPLICIT_FIRE_PATTERN = re.compile(r"\b(?:fire|wildfire|incident|perimeter)\b", re.IGNORECASE)
_EXPLICIT_EVACUATION_DISTANCE_PATTERN = re.compile(
    r"\bevacuation\s+(?:distance|radius)\b", re.IGNORECASE
)
_UNIVERSAL_DISTANCE_SCOPE = re.compile(
    r"\b(?:everyone|everybody|every\s+resident|all\s+(?:people|residents?|"
    r"famil(?:y|ies)|households?|communities))\b|"
    r"\b(?:universal|fixed|single|same)\s+(?:evacuation\s+)?(?:distance|radius)\b|"
    r"\bevery\s+(?:fire|wildfire)\b",
    re.IGNORECASE,
)
_PRESCRIPTIVE_EVACUATION_ACTION = re.compile(
    r"\b(?:should|must|need(?:s)?\s+to|ought\s+to)\s+"
    r"(?:evacuat(?:e|ing)|leave)\b",
    re.IGNORECASE,
)
_PRESCRIPTIVE_STANDOFF_ACTION = re.compile(
    r"\b(?:should|must|need(?:s)?\s+to|ought\s+to)\b"
    r"(?:\s+(?!(?:not|never)\b)[a-z][a-z'-]*){0,5}\s+"
    r"(?:live|stay|remain|keep)\b",
    re.IGNORECASE,
)
_PRESCRIPTIVE_DISTANCE_RULE = re.compile(
    r"\b(?:should|must|need(?:s)?\s+to|ought\s+to)\b"
    r"(?:\s+(?!(?:not|never)\b)[a-z][a-z'-]*){0,5}\s+"
    r"(?:follow|keep|maintain|obey|use)\b",
    re.IGNORECASE,
)
_EXACT_UNIVERSAL_DISTANCE_REQUEST = re.compile(
    r"^\s*(?:give|provide)(?:\s+me)?\s+(?:one|a|the)\s+(?:single\s+)?exact\s+"
    r"evacuation\s+(?:distance|radius)\b",
    re.IGNORECASE,
)
_SELECTED_LOCATION_PATTERN = re.compile(
    r"^\s*where(?:\s+is|['’]s)\s+(?:the\s+)?(?P<identity>[A-Za-z0-9'’.-]+"
    r"(?:\s+[A-Za-z0-9'’.-]+){0,8})[?.!]*\s*$",
    re.IGNORECASE,
)
_CLOSEST_RATIONALE = re.compile(
    r"\bwhy\b.{0,80}\b(?:this|that|selected)\s+"
    r"(?:fire|wildfire|incident|record)\b.{0,80}\b(?:closest|nearest)\b",
    re.IGNORECASE,
)


def _normalized_record_identity(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def is_prescriptive_evacuation_distance_request(request: QueryRequest) -> bool:
    """Separate a universal evacuation threshold from live geometry measurement."""

    question = request.question
    return bool(
        _DISTANCE_PATTERN.search(question)
        and _UNIVERSAL_DISTANCE_SCOPE.search(question)
        and (
            (
                _EXPLICIT_FIRE_PATTERN.search(question)
                and _PRESCRIPTIVE_EVACUATION_ACTION.search(question)
            )
            or (
                _EXPLICIT_FIRE_PATTERN.search(question)
                and _PRESCRIPTIVE_STANDOFF_ACTION.search(question)
            )
            or (
                _EXPLICIT_EVACUATION_DISTANCE_PATTERN.search(question)
                and (
                    _PRESCRIPTIVE_DISTANCE_RULE.search(question)
                    or _EXACT_UNIVERSAL_DISTANCE_REQUEST.search(question)
                )
            )
        )
    )


def _focus_asks(request: QueryRequest, attribute: FocusAttribute) -> bool:
    """Whether a record is selected and the turn asks this attribute about it."""

    if not request.context.selected_live_result_id:
        return False
    focus = focus_reference(request.question)
    return focus is not None and attribute in focus.attributes


def is_unbound_distance_request(request: QueryRequest) -> bool:
    """Deictic distance without a selected record. Named-place how-close proceeds."""

    if is_prescriptive_evacuation_distance_request(request):
        return False
    if request.context.selected_live_result_id:
        return False
    if requested_fire_identity(request) or continues_prior_live_place(request):
        return False
    focus = focus_reference(request.question)
    if focus is not None and focus.anaphoric and FocusAttribute.DISTANCE in focus.attributes:
        return True
    if not is_distance_request(request):
        return False
    if request.location is not None:
        return False
    if coarse_location_from_question(request.question) is not None:
        return False
    if re.search(r"\b(?:nearest|closest|how close)\b", request.question, re.IGNORECASE):
        return False
    return True


def is_distance_request(request: QueryRequest) -> bool:
    """Recognize distance requests with an explicit or selected wildfire target."""

    if is_prescriptive_evacuation_distance_request(request):
        return False
    if _focus_asks(request, FocusAttribute.DISTANCE):
        return True
    return bool(
        _DISTANCE_PATTERN.search(request.question)
        and _EXPLICIT_FIRE_PATTERN.search(request.question)
    )


def is_selected_live_request(request: QueryRequest) -> bool:
    """Recognize supported attribute questions about the selected live record."""

    if not request.context.selected_live_result_id:
        return False
    # "Why is this fire the closest?" explains the lookup's ranking; it is
    # answered from the lookup, not from a record field.
    if selected_location_identity(request) is not None or _CLOSEST_RATIONALE.search(
        request.question
    ):
        return True
    focus = focus_reference(request.question)
    return focus is not None and focus.attribute != FocusAttribute.UNSUPPORTED


def selected_location_identity(request: QueryRequest) -> str | None:
    """Return a named location bound to the most recent visible live roster."""

    named_location = _SELECTED_LOCATION_PATTERN.fullmatch(request.question)
    if named_location is None:
        return None
    identity = _normalized_record_identity(named_location.group("identity"))
    identity_tokens = identity.split()
    latest_assistant = next(
        (turn for turn in reversed(request.history) if turn.role == "assistant"),
        None,
    )
    if latest_assistant is None:
        return None
    prior_tokens = _normalized_record_identity(latest_assistant.content).split()
    if any(
        prior_tokens[index : index + len(identity_tokens)] == identity_tokens
        for index in range(len(prior_tokens) - len(identity_tokens) + 1)
    ):
        return identity
    return None


def selected_location_matches_record(
    request: QueryRequest, records: Sequence[LiveResult]
) -> bool:
    """Verify a bound named location against the exact selected live record."""

    identity = selected_location_identity(request)
    selected_id = request.context.selected_live_result_id
    if identity is None or not selected_id:
        return True
    selected = next((item for item in records if item.result_id == selected_id), None)
    if selected is None:
        return False
    identities = {
        _normalized_record_identity(value)
        for value in (selected.name, selected.incident_number)
        if value
    }
    return identity in identities


def is_unsupported_selected_request(request: QueryRequest) -> bool:
    """Recognize selected-record asks unavailable official fields cannot answer."""

    if _CLOSEST_RATIONALE.search(request.question):
        return False
    if not request.context.selected_live_result_id:
        return False
    focus = focus_reference(request.question)
    return focus is not None and focus.attribute == FocusAttribute.UNSUPPORTED


def uses_selected_live_binding(request: QueryRequest) -> bool:
    """Whether the turn is about the selected record rather than a subject of its own.

    Positions in the shown list ("the second one") are resolved by the planner
    against that list before this rule applies. A turn that names its own
    subject (a place roster, a fire by name, "which is closest") is about that
    subject even while a record stays selected.
    """

    return is_selected_live_request(request) or is_unsupported_selected_request(request)


def requires_selected_live_record(request: QueryRequest) -> bool:
    """Do not infer which record a singular size or status question names."""

    if request.context.selected_live_result_id or requested_fire_identity(request) is not None:
        return False
    focus = focus_reference(request.question)
    return bool(
        focus is not None
        and focus.anaphoric
        and focus.attributes
        and set(focus.attributes) <= {FocusAttribute.STATUS, FocusAttribute.SIZE}
    )


def render_live_record_answer(
    request: QueryRequest,
    shown: Sequence[LiveResult],
    aggregate_freshness: AggregateFreshness,
) -> str:
    """Render the same bounded summary or selected-record attribute deterministically."""

    if is_selected_live_request(request) and shown:
        return focused_record_answer(request, shown[0])
    if is_record_count_question(request.question):
        incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in shown)
        perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in shown)
        return (
            f"Official layers return {incident_count} incident records "
            f"and {perimeter_count} perimeter records. This is a record count, not a "
            "distinct-fire count or a safety determination."
        )
    summary = "; ".join(f"{official_display_name(item)}: {item.status}" for item in shown[:5])
    return official_information_prefix(aggregate_freshness) + summary
