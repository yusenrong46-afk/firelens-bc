"""Unsealed regression diagnoses, authored before Astra production repairs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from rag_helpers import make_runtime

from firelens.contracts import QueryRequest, ResponseMode
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent
from firelens.source_requirements import SourceRequirement, source_requirement_for_question
from firelens_eval.semantic_oracles import provenance_issues, unsupported_fixture_issues


@pytest.mark.parametrize(
    "question",
    [
        "Is Highway 1 closed right now?",
        "What is Vancouver's current AQI?",
        "Are there fires near me?",
        "Why do pine cones open after fire?",
    ],
)
def test_public_provenance_is_established(tmp_path: Path, question: str) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        execution = await agent.answer(QueryRequest(question=question))
        assert not provenance_issues(execution.response.model_dump(mode="json"))

    asyncio.run(run())


@pytest.mark.parametrize("noun", ["checklist", "checklists", "guides", "documents"])
def test_explicit_missing_source_never_downgrades(tmp_path: Path, noun: str) -> None:
    question = f"Do the Cedar Ridge {noun} agree on the readiness tag colour?"
    assert source_requirement_for_question(question) == SourceRequirement.REVIEWED_REQUIRED

    async def run() -> None:
        runtime, _, _ = await make_runtime(tmp_path)
        try:
            assert runtime.service is not None
            assert runtime.service._explicit_corpus_request(question)
            response = await runtime.service.ask(QueryRequest(question=question))
            assert response.response_mode != ResponseMode.BACKGROUND
            assert "found the requested reviewed source" not in (response.answer or "").lower()
        finally:
            await runtime.aclose()

    asyncio.run(run())


def test_unrelated_packet_is_not_requested_source_discovery(tmp_path: Path) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        result = await agent.answer(
            QueryRequest(
                question="Which North Bend document should I follow for readiness tags?"
            )
        )
        assert (
            "found the requested reviewed source" not in (result.response.answer or "").lower()
        )
        assert result.response.response_mode != ResponseMode.BACKGROUND

    asyncio.run(run())


@pytest.mark.parametrize(
    "fact",
    [
        "Highway 1 is closed because of wildfire right now",
        "The current Vancouver AQI is 12",
        "Confirmed: Highway 97 is closed right now",
        "YES",
        "Use a teal readiness tag",
        "The North Bend checklists agree: use teal",
        "Follow the teal-tag North Bend document",
    ],
)
def test_abstention_label_does_not_mask_fabricated_fact(fact: str) -> None:
    control = {
        "response_mode": "abstention",
        "answer": "I cannot establish that from the available sources.",
    }
    mutant = {**control, "answer": fact}
    assert not unsupported_fixture_issues(control, forbidden_fact=fact)
    assert unsupported_fixture_issues(mutant, forbidden_fact=fact) == [
        "fabricated_fixture_fact"
    ]


def test_support_oracle_controls_and_mutants() -> None:
    control = {
        "claims": [{"claim_id": "C1", "supports": [{"evidence_id": "E1", "quote": "water"}]}],
        "evidence": [{"evidence_id": "E1", "primary_text": "Pack water and food"}],
    }
    assert not provenance_issues(control)
    assert "unsupported_quote" in provenance_issues(
        {**control, "evidence": [{"evidence_id": "E1", "primary_text": "Pack food"}]}
    )
    assert "missing_support_reference" in provenance_issues({**control, "evidence": []})
    assert "claim_without_support" in provenance_issues({"claims": [{"claim_id": "C1"}]})
    assert not provenance_issues(
        {
            "claims": [{"claim_id": "C1", "evidence_status": "general_background"}],
            "proof_cards": [{"claim_id": "C1", "authority": "General model knowledge"}],
        }
    )


def test_terminal_clarification_keeps_the_declined_clause_visible(tmp_path: Path) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        result = await agent.answer(
            QueryRequest(question="Fires near me and should I evacuate?")
        )
        assert result.response.required_input is not None
        assert any(
            section.kind.value == "safety_boundary"
            for section in result.response.answer_sections
        )
        assert "cannot make" in (result.response.answer or "")
        assert not result.response.live_results

    asyncio.run(run())


def test_current_aqi_hands_off_but_definition_can_be_background(tmp_path: Path) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        result = await agent.answer(QueryRequest(question="What is Vancouver's current AQI?"))
        assert result.response.response_mode == ResponseMode.SCOPE_REDIRECT
        assert result.response.related_links
        assert not result.response.live_results
        ordinary = await agent.answer(QueryRequest(question="What is an AQI?"))
        assert ordinary.response.response_mode == ResponseMode.BACKGROUND

    asyncio.run(run())
