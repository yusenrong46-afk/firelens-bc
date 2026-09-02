"""Input, execution, and output rails. Luna never has the last word on these."""

from __future__ import annotations

import re

from firelens.agent.packet import AgentPacket
from firelens.agent.tools import AgentTool
from firelens.answering.intent import plan_query
from firelens.answering.typed_compare import typed_preservation_errors
from firelens.answering.validate import _FORBIDDEN, _policy_text
from firelens.contracts import QueryRequest, QueryRoute, ReasonCode
from firelens.freshness_language import (
    aggregate_freshness_from_records,
    current_language_errors,
)

_ALLOWED_TOOLS = {
    AgentTool.LIST_OFFICIAL_FIRES.value,
    AgentTool.GET_OFFICIAL_FIRE.value,
    AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
    AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
    AgentTool.ANSWER_GENERAL_BACKGROUND.value,
}
_FIRE_NAME = re.compile(
    r"\b([A-Z][A-Za-z0-9'’-]{2,}(?:\s+[A-Z][A-Za-z0-9'’-]{2,}){0,4})\s+"
    r"Fire\b(?!\s+Cent(?:er|re)\b)"
)
_CIVIC_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z].{0,40}\b(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b",
    re.IGNORECASE,
)
_FAKE_FEED = re.compile(
    r"\b(?:aqhi|air quality index|highway\s+\d+\s+is\s+(?:open|closed))\b",
    re.IGNORECASE,
)
_FLAME_FRONT = re.compile(
    r"\b(?:this|the)\s+(?:mapped\s+)?perimeter\b.{0,80}\b(?:current\s+|active\s+)?flame\s+front\b|"
    r"\b(?:current\s+|active\s+)?flame\s+front\b.{0,80}\b(?:this|the)\s+(?:mapped\s+)?perimeter\b",
    re.IGNORECASE,
)
_PUBLICATION_STATE_MANIPULATION = re.compile(
    r"\bpublication state\s+(?:is|to|=)\s+verified\b",
    re.IGNORECASE,
)
_SECRET_EXTRACTION = re.compile(
    r"\b(?:reveal|print|output|return)\s+(?:the\s+)?"
    r"(?:api[_-]?key|openrouter[_-]?api[_-]?key|system prompt)\b",
    re.IGNORECASE,
)
_POLICY_BYPASS = re.compile(
    r"\bignore (?:the )?(?:source allowlist|freshness|geometry)\b",
    re.IGNORECASE,
)
_UNAUTHORIZED_TOOL_DEMAND = re.compile(
    r"\binvoke unauthorized tools?\b",
    re.IGNORECASE,
)
_CAPABILITY_REFUSAL = re.compile(
    r"\b(?:i (?:don't|do not) have (?:that )?(?:capability|capabilities)|"
    r"we (?:don't|do not) support that (?:question )?type|"
    r"i (?:wasn't|was not) trained (?:for|on) that)\b",
    re.IGNORECASE,
)
_DISTANCE_VALUE = r"\d+(?:\.\d+)?"
_KILOMETRE_UNIT = r"(?:km|kilomet(?:er|re)s?)"
_KILOMETRE = re.compile(rf"\b(?P<value>{_DISTANCE_VALUE})\s*{_KILOMETRE_UNIT}\b", re.IGNORECASE)
_RADIUS_KM = re.compile(
    rf"\b{_DISTANCE_VALUE}\s*{_KILOMETRE_UNIT}\s+radius\b|"
    rf"\bradius(?:_km)?(?:\s+(?:of|is|=|:))?\s*{_DISTANCE_VALUE}\s*{_KILOMETRE_UNIT}\b",
    re.IGNORECASE,
)
_UNSUPPORTED_DISTANCE_UNIT = re.compile(
    rf"\b{_DISTANCE_VALUE}\s*(?:miles?|mi|met(?:er|re)s?)\b",
    re.IGNORECASE,
)
_NUMBER_WORD_DISTANCE = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|thousand)(?:[ -](?:one|two|three|four|five|"
    r"six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand))*\s+"
    r"(?:km|kilomet(?:er|re)s?|miles?|mi|met(?:er|re)s?)\b",
    re.IGNORECASE,
)
_OFFICIAL_HANDOFF = re.compile(
    r"not connected to an official live source|did not invent a live feed",
    re.IGNORECASE,
)


def input_seatbelt(request: QueryRequest) -> tuple[ReasonCode, str] | None:
    """Cheap pre-call block Luna cannot disable."""

    plan = plan_query(request)
    if plan.route != QueryRoute.PROHIBITED:
        return None
    reason = plan.boundary_reason or ReasonCode.PERSONALIZED_SAFETY_DECISION
    answer = (
        plan.limitations[0]
        if plan.limitations
        else ("FireLens cannot provide this personalized safety decision.")
    )
    return reason, answer


def execution_allowed(tool_name: str) -> bool:
    return tool_name in _ALLOWED_TOOLS


def output_rail_errors(answer: str, packet: AgentPacket) -> list[str]:
    """Return veto reasons. Empty means the draft may be published."""

    errors: list[str] = []
    screened = _policy_text(answer)
    if any(re.search(pattern, screened, re.IGNORECASE) for pattern in _FORBIDDEN):
        errors.append("safety_or_medical_language")
    if _PUBLICATION_STATE_MANIPULATION.search(screened):
        errors.append("publication_state_manipulation")
    if _SECRET_EXTRACTION.search(screened):
        errors.append("secret_extraction")
    if _POLICY_BYPASS.search(screened):
        errors.append("allowlist_freshness_geometry_bypass")
    if _UNAUTHORIZED_TOOL_DEMAND.search(screened):
        errors.append("unauthorized_tool_demand")
    if _CIVIC_ADDRESS.search(answer):
        errors.append("civic_address")
    if _FAKE_FEED.search(answer) and not _OFFICIAL_HANDOFF.search(answer):
        errors.append("unfetched_live_feed")
    if _FLAME_FRONT.search(answer):
        errors.append("perimeter_as_flame_front")
    if _CAPABILITY_REFUSAL.search(answer):
        errors.append("capability_refusal")
    screened_km = _RADIUS_KM.sub(" ", answer)
    if _NUMBER_WORD_DISTANCE.search(screened_km):
        errors.append("number_word_distance")
    if _UNSUPPORTED_DISTANCE_UNIT.search(screened_km):
        errors.append("unsupported_distance_unit")
    allowed_km = tuple(
        item.distance_km for item in packet.live_results if item.distance_km is not None
    )
    for match in _KILOMETRE.finditer(screened_km):
        value = float(match.group("value"))
        if not any(abs(value - allowed) <= 0.1 for allowed in allowed_km):
            errors.append("invented_kilometre")
            break
    allowed_names = packet.allowed_names()
    for match in _FIRE_NAME.finditer(answer):
        candidate = f"{match.group(1)} fire".casefold()
        if candidate not in allowed_names and match.group(0).casefold() not in allowed_names:
            packet_hit = any(name in candidate or candidate in name for name in allowed_names)
            if not packet_hit:
                errors.append("unfetched_fire_name")
                break
    errors.extend(
        current_language_errors(
            answer, aggregate_freshness_from_records(list(packet.live_results))
        )
    )
    static = packet.static_response
    if static is not None:
        quotes = [
            support.quote
            for claim in static.claims
            for support in claim.supports
            if support.quote
        ]
        if quotes and typed_preservation_errors(answer, quotes):
            errors.append("typed_claim_mutation")
    return errors
