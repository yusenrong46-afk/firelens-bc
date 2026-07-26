"""Opt-in, cost-bounded checks against the three real OpenRouter endpoints."""

from __future__ import annotations

import os
import unittest

from firelens.answering.generate import draft_schema
from firelens.config import FireLensConfig
from firelens.providers.openrouter import OpenRouterProvider


@unittest.skipUnless(
    os.environ.get("FIRELENS_RUN_OPENROUTER_SMOKE") == "1",
    "set FIRELENS_RUN_OPENROUTER_SMOKE=1 after rotating the local API key",
)
class OpenRouterSmokeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = FireLensConfig.from_env()
        self.provider = OpenRouterProvider(self.config)

    async def test_embedding_endpoint(self) -> None:
        response = await self.provider.embed(["wildfire preparedness"])
        self.assertEqual(len(response.vectors), 1)
        self.assertTrue(response.vectors[0])

    async def test_rerank_endpoint(self) -> None:
        response = await self.provider.rerank(
            "emergency water",
            ["Store emergency water.", "Paint the garden fence."],
            top_n=1,
        )
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].index, 0)

    async def test_generation_endpoint(self) -> None:
        response = await self.provider.generate(
            [
                {
                    "role": "system",
                    "content": "Return the requested JSON. Abstain because no evidence is supplied.",
                },
                {"role": "user", "content": "Answer using no outside information."},
            ],
            output_schema=draft_schema(),
        )
        self.assertEqual(response.draft.answer_type, "abstention")
