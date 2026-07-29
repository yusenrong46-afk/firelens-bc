from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rag_helpers import make_chunk, make_runtime

from firelens.contracts import QueryRequest, ResponseMode, ResponseStatus


class ConflictHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_near_matching_prescriptive_sources_return_visible_conflict(self) -> None:
        alpha_text = (
            "The required primary marking colour for the North Bend household readiness tag "
            "is teal. Households must attach one teal readiness tag to the bag zipper."
        )
        beta_text = (
            "The required primary marking colour for the North Bend household readiness tag "
            "is orange. Households must attach one orange readiness tag to the bag zipper."
        )
        alpha = replace(
            make_chunk("alpha", alpha_text),
            title="North Bend Checklist Alpha",
            publisher="North Bend Guidance Desk",
            document_sha256="a" * 64,
        )
        beta = replace(
            make_chunk("beta", beta_text, parent="parent-b"),
            source_id="source-b",
            title="North Bend Checklist Beta",
            publisher="North Bend Guidance Desk",
            document_sha256="b" * 64,
        )

        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, _config = await make_runtime(
                Path(directory), chunks=[alpha, beta]
            )
            response = await runtime.service.ask(
                QueryRequest(
                    question="What colour readiness tag does North Bend require on the bag?"
                )
            )

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.CONFLICT)
        self.assertEqual(response.reason_code, "conflicting_evidence")
        self.assertIn("conflict", response.answer.casefold())
        self.assertEqual(len(response.claims), 2)
        self.assertEqual(len(response.evidence), 2)
        self.assertTrue(response.validation and response.validation.accepted)
        self.assertEqual(provider.generate_calls, 0)

    async def test_different_non_prescriptive_passages_do_not_invent_conflict(self) -> None:
        first = make_chunk("first", "Wildfire smoke can affect indoor air quality.")
        second = replace(
            make_chunk(
                "second",
                "A household emergency kit can include water and a flashlight.",
                parent="parent-b",
            ),
            source_id="source-b",
            document_sha256="b" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), chunks=[first, second]
            )
            response = await runtime.service.ask(
                QueryRequest(question="What can a household emergency kit include?")
            )
        self.assertNotEqual(response.response_mode, ResponseMode.CONFLICT)
