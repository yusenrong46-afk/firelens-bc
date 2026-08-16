"""Input, execution, and output rails. Luna never has the last word on these."""

from __future__ import annotations

import re

from firelens.agent.packet import AgentPacket
from firelens.agent.tools import AgentTool
from firelens.answering.intent import plan_query
from firelens.answering.validate import _FORBIDDEN, _policy_text
from firelens.contracts import QueryRequest, QueryRoute, ReasonCode

_ALLOWED_TOOLS = {
    AgentTool.LIST_OFFICIAL_FIRES.value,
    AgentTool.GET_OFFICIAL_FIRE.value,
    AgentTool.LIST_OFFICIAL_EVACUATIONS.value,
    AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
}
_FIRE_NAME = re.compile(
    r"\b([A-Z][A-Za-z0-9'’-]{2,}(?:\s+[A-Z][A-Za-z0-9'’-]{2,}){0,4})\s+Fire\b"
)
_CIVIC_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z].{0,40}\b(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b",
    re.IGNORECASE,
)
_FAKE_FEED = re.compile(
    r"\b(?:aqhi|air quality index|highway\s+\d+\s+is\s+(?:open|closed))\b",
    re.IGNORECASE,
)
_CAPABILITY_REFUSAL = re.compile(
    r"\b(?:i (?:don't|do not) have (?:that )?(?:capability|capabilities)|"
    r"we (?:don't|do not) support that (?:question )?type|"
    r"i (?:wasn't|was not) trained (?:for|on) that)\b",
    re.IGNORECASE,
)
_KILOMETRE = re.compile(r"\b(\d+(?:\.\d+)?)\s*km\b", re.IGNORECASE)
_RADIUS_KM = re.compile(
    r"\b\d+(?:\.\d+)?\s*km\s+radius\b|\bradius(?:_km)?(?:\s+(?:of|is|=|:))?\s*\d+(?:\.\d+)?\s*km\b",
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
    if _CIVIC_ADDRESS.search(answer):
        errors.append("civic_address")
    if _FAKE_FEED.search(answer) and not _OFFICIAL_HANDOFF.search(answer):
        errors.append("unfetched_live_feed")
    if _CAPABILITY_REFUSAL.search(answer):
        errors.append("capability_refusal")
    allowed_km = {
        round(item.distance_km, 1)
        for item in packet.live_results
        if item.distance_km is not None
    }
    screened_km = _RADIUS_KM.sub(" ", answer)
    for match in _KILOMETRE.finditer(screened_km):
        value = round(float(match.group(1)), 1)
        if not any(abs(value - allowed) <= 0.1 for allowed in allowed_km):
            errors.append("invented_kilometre")
            break
    allowed_names = packet.allowed_names()
    if allowed_names and "no fetched official record is named" not in answer.casefold():
        for match in _FIRE_NAME.finditer(answer):
            candidate = f"{match.group(1)} fire".casefold()
            if (
                candidate not in allowed_names
                and match.group(0).casefold() not in allowed_names
            ):
                packet_hit = any(
                    name in candidate or candidate in name for name in allowed_names
                )
                if not packet_hit:
                    errors.append("unfetched_fire_name")
                    break
    return errors
