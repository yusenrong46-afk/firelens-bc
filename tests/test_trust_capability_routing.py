from __future__ import annotations

import asyncio
from pathlib import Path

from rag_helpers import make_runtime

from firelens.answering.intent import plan_query
from firelens.contracts import QueryRequest, QueryRoute, ResponseMode
from firelens.providers.fake import FakeProvider

QUESTION = (
    "How can I tell whether information in your answer is current or just "
    "preparedness guidance?"
)


def test_trust_explanation_is_a_zero_provider_capability_response(tmp_path: Path) -> None:
    async def run() -> None:
        plan = plan_query(QueryRequest(question=QUESTION))
        assert plan.route == QueryRoute.CAPABILITY

        provider = FakeProvider()
        runtime, _, _ = await make_runtime(tmp_path, provider=provider)
        initial_calls = (
            provider.plan_calls,
            provider.embed_calls,
            provider.rerank_calls,
            provider.generate_calls,
        )
        try:
            assert runtime.service is not None
            response = await runtime.service.ask(QueryRequest(question=QUESTION))
        finally:
            await runtime.aclose()

        assert response.response_mode == ResponseMode.CAPABILITY
        assert (
            provider.plan_calls,
            provider.embed_calls,
            provider.rerank_calls,
            provider.generate_calls,
        ) == initial_calls

        public_text = " ".join([response.answer or "", *response.limitations]).casefold()
        assert "official live records" in public_text
        assert "official source updated" in public_text
        assert "firelens retrieved" in public_text
        assert "reviewed structured claims" in public_text
        assert "exact source wording" in public_text
        assert "general background" in public_text
        assert "human semantic review" in public_text

    asyncio.run(run())
