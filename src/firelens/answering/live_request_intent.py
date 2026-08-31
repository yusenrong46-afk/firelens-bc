"""Deterministic recognition and rendering for live-record follow-up requests."""

from __future__ import annotations

import re
from collections.abc import Sequence

from firelens.answering.intent import continues_prior_live_place
from firelens.answering.live_analysis import official_display_name
from firelens.answering.live_named_fire import requested_fire_identity
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import AggregateFreshness, LiveResult, LiveResultKind, QueryRequest
from firelens.freshness_language import official_information_prefix

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
_SELECTED_ENTITY_PATTERN = re.compile(
    r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|perimeter|record)\b",
    re.IGNORECASE,
)
_SELECTED_LOCATION_PATTERN = re.compile(
    r"^\s*where(?:\s+is|['’]s)\s+(?:the\s+)?(?P<identity>[A-Za-z0-9'’.-]+"
    r"(?:\s+[A-Za-z0-9'’.-]+){0,8})[?.!]*\s*$",
    re.IGNORECASE,
)


def _normalized_record_identity(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


_SELECTED_ATTRIBUTE_PATTERN = re.compile(
    r"\b(?:status|happening|details?|size|large|big|hectares?|source|publisher|dataset|"
    r"updated|updates?|update time|update timestamp|perimeter|map|location|position)\b",
    re.IGNORECASE,
)
_SELECTED_UNSUPPORTED_PATTERN = re.compile(
    r"\b(?:why|cause|caused|start(?:ed)?|ignition|will|predict(?:ed|ion)?|forecast|"
    r"reach|arrive|spread to|contained?|controlled?|go out)\b",
    re.IGNORECASE,
)
_SELECTED_PRONOUN_UNSUPPORTED_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:when|why)\s+did\s+it\s+start|"
    r"what\s+caused\s+it|"
    r"when\s+will\s+it\s+(?:reach|arrive|spread|be\s+contained|"
    r"be\s+controlled|go\s+out)\b.*|"
    r"will\s+it\s+(?:reach|arrive|spread|be\s+contained|be\s+controlled|"
    r"go\s+out)\b.*|"
    r"is\s+it\s+going\s+to\s+(?:reach|arrive|spread)\b.*"
    r")[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_LIVE_ELLIPTICAL = re.compile(
    r"^\s*(?:"
    r"(?:what|which)\s+(?:source|publisher|dataset)\s+(?:reported|published)\s+it|"
    r"who\s+(?:reported|published)\s+it|"
    r"what(?:'s|\s+is)\s+its\s+"
    r"(?:(?:present|current|latest)\s+)?(?:status|size|source|perimeter|location)"
    r"(?:\s+and\s+(?:(?:present|current|latest)\s+)?"
    r"(?:status|size|source|perimeter|location))?|"
    r"how\s+(?:large|big)\s+is\s+it|"
    r"when\s+was\s+(?:it|that\s+information)(?:\s+last)?\s+updated|"
    r"(?:what|any)\s+updates?(?:\s+on\s+it)?|"
    r"(?:and\s+)?(?:the\s+)?(?:perimeter|map|location)"
    r")[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_DEICTIC_STATUS = re.compile(
    r"^\s*is\s+it\s+(?:still\s+)?(?:burning|active)[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_DEICTIC_OFFICIAL_DETAILS = re.compile(
    r"^\s*what\s+official\s+(?:details?|information)\s+(?:are|is)\s+"
    r"(?:on|for)\s+it[?!.]*\s*$",
    re.IGNORECASE,
)
_SELECTED_DISTANCE_ELLIPTICAL = re.compile(
    r"^\s*(?:how\s+(?:far|close)(?:\s+away)?\s+is\s+it"
    r"(?:\s+(?:from|to)\s+[a-z][a-z .'-]{1,80})?|"
    r"(?:what(?:'s|\s+is)\s+(?:the\s+)?)?distance\s+from\s+"
    r"[a-z][a-z .'-]{1,80}?\s+to\s+it)[?!.]*\s*$",
    re.IGNORECASE,
)
_SOURCE_PATTERN = re.compile(
    r"\b(?:what|which|who|where).{0,30}\b(?:source|reported|published|dataset)\b|"
    r"\b(?:source|publisher|dataset)\b",
    re.IGNORECASE,
)
_UPDATED_PATTERN = re.compile(
    r"\b(?:when\s+(?:was|is)\b.{0,100}\bupdated|"
    r"last updated|source updated|record updated|update time|update timestamp)\b",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(r"\b(?:how (?:large|big)|size|hectares?|ha)\b", re.I)
_COUNT_PATTERN = re.compile(
    r"\bhow many\b.{0,60}\b(?:fires?|wildfires?)(?:\s+records?)?\b",
    re.IGNORECASE,
)
_ORDINAL_RECORD_PATTERN = re.compile(
    r"\b(?:the\s+)?(?:first|second|third|1st|2nd|3rd)\s+"
    r"(?:one|fire|wildfire|incident|record)\b",
    re.IGNORECASE,
)
_CLOSEST_RECORD_PATTERN = re.compile(r"\b(?:closest|nearest)\b", re.IGNORECASE)
_SELECTED_CLOSEST_RATIONALE = re.compile(
    r"\bwhy\b.{0,80}\b(?:this|that|selected)\s+"
    r"(?:fire|wildfire|incident|record)\b.{0,80}\b(?:closest|nearest)\b",
    re.IGNORECASE,
)
_SELECTED_UNKNOWN = re.compile(
    r"\b(?:what|which)\b.{0,80}\b(?:this|that|selected)\s+"
    r"(?:fire|wildfire|incident|record)\b.{0,80}"
    r"\b(?:uncertain|not\s+certain|unknown|not\s+known)\b",
    re.IGNORECASE,
)
_SELECTED_REFORMAT = re.compile(
    r"^\s*(?:please\s+)?(?:give|show|put)\s+(?:me\s+)?(?:the\s+)?"
    r"answer\s+first(?:,?\s+then\s+(?:the\s+)?evidence)?[.!?]*\s*$",
    re.IGNORECASE,
)
_SINGULAR_STATUS_PATTERN = re.compile(
    r"\b(?:what(?:'s|\s+is)|is)\s+(?:the\s+)?status\s+(?:of\s+)?"
    r"(?:this|that|the|a|an|it|its)\s+(?:fire|wildfire|incident|record)\b|"
    r"\b(?:this|that|the|a|an)\s+(?:fire|wildfire|incident|record)\s+status\b|"
    r"\bwhat(?:'s|\s+is)\s+its\s+status\b",
    re.IGNORECASE,
)
_SINGULAR_SIZE_PATTERN = re.compile(
    r"\b(?:how\s+(?:large|big)\s+is|what(?:'s|\s+is)\s+(?:the\s+)?size\s+of)\s+"
    r"(?:this|that|the|a|an|it|its)\s+(?:fire|wildfire|incident|record)\b|"
    r"\bhow\s+(?:large|big)\s+is\s+it\b|"
    r"\bwhat(?:'s|\s+is)\s+its\s+size\b",
    re.IGNORECASE,
)


_DEICTIC_DISTANCE = re.compile(
    r"\b(?:how\s+(?:far|close).{0,40}\b(?:this|that|it)\b|"
    r"how\s+(?:far|close)\s+is\s+it\b|"
    r"distance\s+(?:from|to)\s+.+\s+to\s+it\b)",
    re.IGNORECASE,
)


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


def is_unbound_distance_request(request: QueryRequest) -> bool:
    """Deictic distance without a selected record. Named-place how-close proceeds."""

    if is_prescriptive_evacuation_distance_request(request):
        return False
    if request.context.selected_live_result_id:
        return False
    if requested_fire_identity(request) or continues_prior_live_place(request):
        return False
    if _DEICTIC_DISTANCE.search(request.question):
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
    if not _DISTANCE_PATTERN.search(request.question):
        return False
    return bool(
        _EXPLICIT_FIRE_PATTERN.search(request.question)
        or (
            request.context.selected_live_result_id
            and _SELECTED_DISTANCE_ELLIPTICAL.match(request.question)
        )
    )


def is_selected_live_request(request: QueryRequest) -> bool:
    """Recognize supported attribute questions about the selected live record."""

    named_location_bound = selected_location_identity(request) is not None

    return bool(
        request.context.selected_live_result_id
        and (
            (
                _SELECTED_ENTITY_PATTERN.search(request.question)
                and _SELECTED_ATTRIBUTE_PATTERN.search(request.question)
                and not _SELECTED_UNSUPPORTED_PATTERN.search(request.question)
            )
            or named_location_bound
            or _SELECTED_LIVE_ELLIPTICAL.match(request.question)
            or _SELECTED_DEICTIC_STATUS.match(request.question)
            or _SELECTED_DEICTIC_OFFICIAL_DETAILS.match(request.question)
            or _SELECTED_CLOSEST_RATIONALE.search(request.question)
            or _SELECTED_UNKNOWN.search(request.question)
            or _SELECTED_REFORMAT.match(request.question)
        )
    )


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

    if _SELECTED_CLOSEST_RATIONALE.search(request.question):
        return False
    return bool(
        request.context.selected_live_result_id
        and (
            (
                _SELECTED_ENTITY_PATTERN.search(request.question)
                and _SELECTED_UNSUPPORTED_PATTERN.search(request.question)
            )
            or _SELECTED_PRONOUN_UNSUPPORTED_PATTERN.match(request.question)
        )
    )


def uses_selected_live_binding(request: QueryRequest) -> bool:
    """Keep an existing map selection authoritative for explicit record asks."""

    if not request.context.selected_live_result_id:
        return False
    return bool(
        is_selected_live_request(request)
        or is_unsupported_selected_request(request)
        or is_distance_request(request)
        or requested_fire_identity(request)
        or _CLOSEST_RECORD_PATTERN.search(request.question)
        or _ORDINAL_RECORD_PATTERN.search(request.question)
    )


def requires_selected_live_record(request: QueryRequest) -> bool:
    """Do not infer which record a singular size or status question names."""

    return bool(
        not request.context.selected_live_result_id
        and requested_fire_identity(request) is None
        and (
            _SINGULAR_STATUS_PATTERN.search(request.question)
            or _SINGULAR_SIZE_PATTERN.search(request.question)
        )
    )


def render_live_record_answer(
    request: QueryRequest,
    shown: Sequence[LiveResult],
    aggregate_freshness: AggregateFreshness,
) -> str:
    """Render the same bounded summary or selected-record attribute deterministically."""

    selected_request = is_selected_live_request(request)
    summary = "; ".join(f"{official_display_name(item)}: {item.status}" for item in shown[:5])
    if selected_request and _UPDATED_PATTERN.search(request.question):
        selected = shown[0]
        display_name = official_display_name(selected)
        return (
            f"The official source record for {display_name} was updated at "
            f"{selected.source_updated_at.isoformat()}."
            if selected.source_updated_at is not None
            else f"The official source record for {display_name} does not provide an update timestamp."
        )
    if selected_request and _SOURCE_PATTERN.search(request.question):
        selected = shown[0]
        display_name = official_display_name(selected)
        return (
            f"Official source for {display_name}: {selected.authority}. "
            "Open the linked official record for its source data and source timestamp."
        )
    if selected_request and _SIZE_PATTERN.search(request.question):
        selected = shown[0]
        display_name = official_display_name(selected)
        status = (
            f" Its official status is {selected.status}."
            if re.search(r"\bstatus\b", request.question, re.IGNORECASE)
            else ""
        )
        return (
            f"The official record reports {display_name} at "
            f"{selected.size_hectares:g} hectares.{status}"
            if selected.size_hectares is not None
            else (
                f"The official record for {display_name} does not provide a size value.{status}"
            )
        )
    if _COUNT_PATTERN.search(request.question):
        incident_count = sum(item.kind == LiveResultKind.INCIDENT for item in shown)
        perimeter_count = sum(item.kind == LiveResultKind.PERIMETER for item in shown)
        return (
            f"Official layers return {incident_count} incident records "
            f"and {perimeter_count} perimeter records. This is a record count, not a "
            "distinct-fire count or a safety determination."
        )
    return official_information_prefix(aggregate_freshness) + summary
