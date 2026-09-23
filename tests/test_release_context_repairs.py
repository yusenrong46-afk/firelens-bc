"""Frozen release-context regressions; real corpus, offline provider and live data."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from test_v1_6_user_end_questions_end_to_end import _fire, _FixtureLiveService

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import plan_agent_request
from firelens.answering.intent_conversation import conversation_planning_question
from firelens.answering.request_facets import contents_request_facet
from firelens.answering.static_guidance_subject import static_guidance_subject
from firelens.config import FireLensConfig
from firelens.contracts import QueryRequest
from firelens.live_answering import LiveAnswerCoordinator
from firelens.providers.fake import FakeProvider
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/release_context_regressions.v1.json").read_text())[
    "cases"
]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_frozen_release_context(case: dict) -> None:
    request = QueryRequest.model_validate(case["request"])
    question = conversation_planning_question(request)
    plan = plan_agent_request(request)
    expected = case["expectation"]
    subject = static_guidance_subject(question)
    if expected == "pet_guidance":
        assert subject == "pet_grab_and_go"
        assert any(tool.name == "search_reviewed_guidance" for tool in plan.tool_calls)
    elif expected in {"live_pg", "no_history_live"}:
        assert plan.mode == "live"
        assert plan.location_label == "Prince George"
    elif expected == "weather":
        assert plan.scope_result == "scope_redirect"
    elif expected in {"independent", "no_context", "different_history", "not_pet_guidance"}:
        assert subject != "pet_grab_and_go"
    elif expected == "context":
        assert "earlier question" in question
    elif expected in {"selected", "background"}:
        assert question == request.question
    else:
        pytest.fail(f"Missing expectation oracle: {expected}")
    if not case["publication_check"]:
        return

    async def run() -> None:
        runtime = load_runtime(
            FireLensConfig.from_env(ROOT), provider=FakeProvider(dimensions=1536)
        )
        try:
            execution = await FireLensAgent(
                runtime.service, LiveAnswerCoordinator(_FixtureLiveService([_fire()]))
            ).answer(request)
            response = execution.response
            if expected == "pet_guidance":
                source = next(
                    json.loads(line)
                    for line in (ROOT / "data/processed/firelens_static_corpus.chunks.jsonl")
                    .read_text()
                    .splitlines()
                    if json.loads(line)["chunk_id"] == case["source"]["chunk_id"]
                )
                # Full exact passage preserves the conditions in its final sentences.
                assert any(claim.text == source["text"] for claim in response.claims)
                assert any(
                    evidence.document_sha256 == source["document_sha256"]
                    and source["text"] in evidence.primary_text
                    for evidence in response.evidence
                )
                assert all(
                    claim.publication and claim.publication.kind == "official_quote_only"
                    for claim in response.claims
                )
            else:
                assert response.live_results
                assert response.live_results[0].result_id == _fire().result_id
        finally:
            await runtime.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("pronoun", ["I", "we", "you", "they"])
def test_person_is_not_a_contents_container(pronoun: str) -> None:
    assert contents_request_facet(f"What should {pronoun} include for our animals?") is None


def test_named_container_remains_a_contents_request() -> None:
    facet = contents_request_facet("What should an emergency bag include?")
    assert facet is not None
    assert facet.container == "emergency bag"


@pytest.mark.parametrize(
    "question",
    [
        "Separate topic: what supplies should I bring for my cat on vacation?",
        "What supplies should I bring for my dog's birthday party?",
        "What should I pack for my pets on an airplane?",
    ],
)
def test_explicit_new_pet_purpose_does_not_inherit_emergency_authority(question: str) -> None:
    request = QueryRequest.model_validate(
        {
            "question": question,
            "history": CASES[0]["request"]["history"],
        }
    )
    assert conversation_planning_question(request) == question
    assert static_guidance_subject(conversation_planning_question(request)) is None
    independent = plan_agent_request(QueryRequest(question=question))
    assert plan_agent_request(request).tool_calls == independent.tool_calls
