"""Content-free golden-trace records for the five V1.6 Ask paths.

These traces are replayed offline with test doubles. They never store the
question text inside RequestExecutionPolicy; the case id is the join key.
"""

from __future__ import annotations

from dataclasses import dataclass

from firelens.agent.coordinator import AgentExecution
from firelens.contracts import QueryRoute, ResponseMode

GOLDEN_TRACE_QUESTIONS: tuple[str, ...] = (
    "What belongs in a grab-and-go bag?",
    "What official fires are near Kelowna?",
    "How far is this selected fire from Kelowna?",
    "Should I evacuate right now?",
    "Who won the Stanley Cup?",
)


@dataclass(frozen=True)
class GoldenTrace:
    case_id: str
    question: str
    route: str
    policy_route: str | None
    input_rail: str
    tools: tuple[str, ...]
    provider_stages: tuple[str, ...]
    retrieval_cycles: int
    outer_chat_turns: int
    grounded_generations: int
    evidence_lane: str
    validation_accepted: bool | None
    response_mode: str
    fallback_reason: str | None
    refused_inferences: tuple[str, ...]


def evidence_lane(execution: AgentExecution) -> str:
    response = execution.response
    has_live = bool(response.live_results)
    has_reviewed = bool(response.evidence) and response.response_mode in {
        ResponseMode.GROUNDED,
        ResponseMode.PARTIAL,
        ResponseMode.CONFLICT,
        ResponseMode.MIXED,
    }
    if has_live and has_reviewed:
        return "mixed"
    if has_live:
        return "live"
    if has_reviewed:
        return "reviewed"
    return "none"


def input_rail(execution: AgentExecution) -> str:
    if execution.route == QueryRoute.PROHIBITED:
        return "input_seatbelt"
    if execution.policy.route == "missing_location":
        return "location_required"
    return "none"


def refused_inferences(execution: AgentExecution) -> tuple[str, ...]:
    response = execution.response
    items: list[str] = []
    if response.reason_code is not None:
        items.append(response.reason_code.value)
    items.extend(response.unknown_items)
    return tuple(dict.fromkeys(items))


def record_golden_trace(
    *,
    case_id: str,
    question: str,
    execution: AgentExecution,
) -> GoldenTrace:
    """Snapshot one Ask execution for replay assertions."""

    response = execution.response
    accepted = None if response.validation is None else response.validation.accepted
    return GoldenTrace(
        case_id=case_id,
        question=question,
        route=execution.route.value,
        policy_route=execution.policy.route,
        input_rail=input_rail(execution),
        tools=tuple(tool.value for tool in execution.tools),
        provider_stages=tuple(execution.policy.provider_stages),
        retrieval_cycles=execution.policy.retrieval_cycles,
        outer_chat_turns=execution.policy.outer_chat_turns,
        grounded_generations=execution.policy.grounded_generations,
        evidence_lane=evidence_lane(execution),
        validation_accepted=accepted,
        response_mode=response.response_mode.value,
        fallback_reason=execution.policy.fallback_reason,
        refused_inferences=refused_inferences(execution),
    )
