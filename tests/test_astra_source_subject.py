"""Integration-found source-subject regression; unsealed supplemental controls."""

import asyncio
from pathlib import Path

import pytest

from firelens.answering.intent_conversation import explicit_corpus_attribution
from firelens.contracts import QueryRequest, ResponseMode
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent
from firelens.guidance_capabilities import resolve_capability


@pytest.mark.parametrize(
    "question",
    [
        "What documents and medicines should I have ready to evacuate?",
        "What documents should we pack in our emergency bag?",
        "Which documents must I bring when evacuating?",
        "What documents can we keep ready for wildfire evacuation?",
    ],
)
def test_personal_papers_are_not_a_named_source(question: str) -> None:
    assert not explicit_corpus_attribution(question)


@pytest.mark.parametrize(
    "question",
    [
        "According to PreparedBC, what documents should I pack?",
        "What does the Cedar Ridge guide say about documents I should bring?",
        "Do the Cedar Ridge documents agree on the readiness tag colour?",
    ],
)
def test_explicit_attribution_remains_required(question: str) -> None:
    assert explicit_corpus_attribution(question)


@pytest.mark.parametrize(
    "question",
    [
        "According to Cedar Ridge, what documents should I pack for evacuation?",
        "What documents should I pack for evacuation according to Cedar Ridge?",
        "What documents should I prepare for a mortgage?",
        "What documents should I pack for evacuation and should I leave now?",
    ],
)
def test_preparation_binding_does_not_steal_sources_or_other_clauses(question: str) -> None:
    assert resolve_capability(question) is None


def test_document_preparation_preserves_supported_quote(tmp_path: Path) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        execution = await agent.answer(
            QueryRequest(
                question="What documents and medicines should I have ready to evacuate?"
            )
        )
        response = execution.response
        assert response.response_mode == ResponseMode.PARTIAL
        assert response.evidence
        assert any(claim.publication.kind == "official_quote_only" for claim in response.claims)
        assert "documents" in response.answer
        assert "sprinkler" not in response.answer.lower()

    asyncio.run(run())
