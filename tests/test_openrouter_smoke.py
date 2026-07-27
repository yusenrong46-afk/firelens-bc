"""Opt-in, cost-bounded checks against the three real OpenRouter endpoints."""

from __future__ import annotations

import os
import unittest

from firelens.config import FireLensConfig
from firelens.contracts import GroundedDraft
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
        response = await self.provider.generate_grounded(
            [
                {
                    "role": "system",
                    "content": (
                        "Return the requested JSON. Write one short grounded claim and cite "
                        "the exact supplied quote ID E1Q1."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Question: What should an emergency kit contain? Evidence E1Q1: "
                        "An emergency kit should include water."
                    ),
                },
            ],
            output_schema=GroundedDraft.model_json_schema(),
        )
        self.assertEqual(response.draft.answer_type, "grounded")
