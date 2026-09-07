"""Source-bound pet packing requests retain inclusion and omission intent."""

import asyncio
from pathlib import Path

import pytest

from firelens.contracts import QueryRequest
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent


@pytest.mark.parametrize(
    "question",
    [
        "What should be included for pets when evacuating a wildfire?",
        "What is included for pets when evacuating a wildfire?",
        "What should I include for pets when evacuating a wildfire?",
    ],
)
def test_pet_contents_inflections_use_exact_source_without_generation(
    tmp_path: Path, question: str
) -> None:
    async def run() -> None:
        agent, provider, _ = await fixture_agent(tmp_path)
        before = provider.generate_calls
        response = (await agent.answer(QueryRequest(question=question))).response
        assert response.response_mode.value == "partial"
        assert response.claims
        assert provider.generate_calls == before
        sources = {item.evidence_id: item.primary_text for item in response.evidence}
        for claim in response.claims:
            assert claim.publication is not None
            assert claim.publication.kind.value == "official_quote_only"
            assert claim.text == claim.supports[0].quote
            assert claim.text in sources[claim.supports[0].evidence_id]
        assert "leashes" in response.answer and "carriers" in response.answer

    asyncio.run(run())


@pytest.mark.parametrize(
    "question",
    [
        "Which supplies should not be included for pets when evacuating a wildfire?",
        "What should not be packed for pets during a wildfire evacuation?",
        "Which items should not be packed for pets during a wildfire evacuation?",
        "What shouldn't be included in a pet evacuation bag?",
        "What medicines should be included for pets when evacuating a wildfire?",
    ],
)
def test_positive_pet_checklist_cannot_establish_omissions_or_medicines(
    tmp_path: Path, question: str
) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        response = (await agent.answer(QueryRequest(question=question))).response
        assert not response.claims

    asyncio.run(run())
