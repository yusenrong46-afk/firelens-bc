"""Focused deterministic routing regressions for guided source-aware requests."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import AgentRequestMode, plan_agent_request
from firelens.answering.intent_automaton import parse_request_intent
from firelens.contracts import (
    AskResponse,
    LiveResultKind,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
)
from firelens.live_answering import LiveAnswerCoordinator


@pytest.mark.parametrize(
    "question",
    (
        "What actions should I take after an evacuation order?",
        "How should I respond to an evacuation order?",
        "How should I get my evacuation route and vehicle ready?",
        "What should I pack for pets during a wildfire evacuation?",
    ),
)
def test_stable_evacuation_actions_use_reviewed_guidance(question: str) -> None:
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert plan.mode == AgentRequestMode.STATIC


def test_current_listed_evacuation_records_remain_live() -> None:
    question = "What evacuation alerts or orders are currently listed in Kelowna?"
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert not parsed.has_reviewed_guidance
    assert parsed.live_layers == (LiveResultKind.EVACUATION,)


def test_all_three_official_record_types_selects_all_live_layers() -> None:
    parsed = parse_request_intent("Open all three official record types for Kelowna, BC")

    assert parsed.live_layers == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
        LiveResultKind.EVACUATION,
    )


class _OuterLoopProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_turn(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("validated corpus capabilities must bypass the outer loop")


class _StaticSpy:
    def __init__(self) -> None:
        self.provider = _OuterLoopProvider()
        self.calls: list[tuple[QueryRequest, dict[str, Any]]] = []

    async def ask(self, request: QueryRequest, **kwargs: Any) -> AskResponse:
        self.calls.append((request, dict(kwargs)))
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="c" * 32,
            response_mode=ResponseMode.CAPABILITY,
            answer="Source-bound static response.",
        )


@pytest.mark.parametrize(
    "question",
    (
        "According to official guidance, what mistakes should I avoid during an evacuation?",
        "Who should I call when I am in danger during a wildfire?",
    ),
)
def test_validated_corpus_capabilities_bypass_outer_loop(question: str) -> None:
    static = _StaticSpy()
    agent = FireLensAgent(
        cast(Any, static),
        LiveAnswerCoordinator(cast(Any, object())),
    )

    execution = asyncio.run(agent.answer(QueryRequest(question=question)))

    assert static.provider.calls == 0
    assert execution.policy.outer_chat_turns == 0
    assert len(static.calls) == 1
    called_request, kwargs = static.calls[0]
    assert called_request.question == question
    assert kwargs == {"allow_live": False, "prefer_reviewed_quotes": True}
