"""Independent expected tools/geography and real successive-turn diagnostics."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from firelens.agent.query_plan import AgentGeography, AgentRequestMode, plan_agent_request
from firelens.contracts import ConversationTurn, QueryRequest
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent


@pytest.mark.parametrize("place", ["West Kelowna", "Prince George", "Salmon Arm"])
@pytest.mark.parametrize(
    "clause", ["tell me which ones threaten my house", "should I evacuate?", "am I safe?"]
)
def test_located_records_preserve_personal_boundary(place: str, clause: str) -> None:
    plan = plan_agent_request(QueryRequest(question=f"Show fires near {place} and {clause}"))
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert any(section.kind.value == "safety_boundary" for section in plan.boundaries)
    tools = [call.name.value for call in plan.tool_calls]
    assert "list_official_fires" in tools
    assert "answer_general_background" not in tools


def test_province_roster_is_not_blocked_by_personal_house_clause() -> None:
    plan = plan_agent_request(
        QueryRequest(
            question="List every active wildfire in BC and tell me which ones threaten my house in West Kelowna."
        )
    )
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.mode != AgentRequestMode.TERMINAL
    assert plan.boundaries
    assert "answer_general_background" not in [call.name.value for call in plan.tool_calls]


def test_missing_place_keeps_safety_boundary() -> None:
    plan = plan_agent_request(QueryRequest(question="Fires near me and should I evacuate?"))
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.boundaries
    assert not plan.tool_calls


@pytest.mark.parametrize(
    "question",
    [
        "Show fires near Kelowna",
        "SHOW FIRES NEAR KELOWNA!",
        "Please show fires near Kelowna.",
    ],
)
def test_equivalent_location_binding(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert (plan.location_label or "").casefold() == "kelowna"
    assert "list_official_fires" in [call.name.value for call in plan.tool_calls]


@pytest.mark.parametrize(
    "last_question",
    [
        "Show fires near Prince George",
        "Should I evacuate?",
        "Why do pine cones open after fire?",
    ],
)
def test_three_turn_state_is_built_from_actual_answers(
    tmp_path: Path, last_question: str
) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        history: list[ConversationTurn] = []
        for index, question in enumerate(
            ["Are there fires near me?", "Show fires near Kelowna", last_question]
        ):
            service = agent.live_coordinator.live_service
            with patch.object(service, "nearby_page", wraps=service.nearby_page) as nearby:
                execution = await agent.answer(
                    QueryRequest(question=question, history=history[-6:])
                )
            response = execution.response
            if index == 0:
                assert response.required_input is not None
                assert not response.live_results
            elif index == 1:
                assert response.live_results
            elif "Prince George" in question:
                assert nearby.call_args is not None
                assert nearby.call_args.args[0].label == "Prince George"
            elif question == "Should I evacuate?":
                assert "answer_general_background" not in [
                    tool.value for tool in execution.tools
                ]
                assert "cannot" in (response.answer or "").lower()
            else:
                assert not response.live_results
                assert response.response_mode.value == "background"
            history.extend(
                [
                    ConversationTurn(role="user", content=question),
                    ConversationTurn(
                        role="assistant", content=response.history_text or response.answer or ""
                    ),
                ]
            )
        assert len(history) == 6

    asyncio.run(run())
