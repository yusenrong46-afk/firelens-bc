from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rag_helpers import make_chunk, make_runtime

from firelens.contracts import AuthorityClass, QueryRequest, ResponseMode, ResponseStatus


class ConflictHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_cross_authority_material_difference_is_surfaced(self) -> None:
        alpha = replace(
            make_chunk(
                "alpha",
                "Residents must attach one teal readiness tag to the emergency bag zipper.",
            ),
            title="Provincial Readiness Guide",
            publisher="Government of British Columbia",
            authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT.value,
            document_sha256="a" * 64,
        )
        beta = replace(
            make_chunk(
                "beta",
                "Residents must attach one orange readiness tag to the emergency bag zipper.",
                parent="parent-b",
            ),
            source_id="source-b",
            title="Wildfire Readiness Guide",
            publisher="FireSmart BC",
            authority_class=AuthorityClass.WILDFIRE_PREPAREDNESS.value,
            document_sha256="b" * 64,
        )

        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, _config = await make_runtime(
                Path(directory), chunks=[alpha, beta]
            )
            response = await runtime.service.ask(
                QueryRequest(question="What colour readiness tag belongs on the emergency bag?")
            )

        self.assertEqual(response.response_mode, ResponseMode.CONFLICT)
        self.assertEqual(response.reason_code, "conflicting_evidence")
        self.assertEqual(provider.generate_calls, 0)

    async def test_authority_precedence_matrix_surfaces_material_differences(self) -> None:
        authority_pairs = (
            (
                AuthorityClass.PROVINCIAL_GOVERNMENT,
                AuthorityClass.PROVINCIAL_GOVERNMENT,
            ),
            (
                AuthorityClass.PROVINCIAL_GOVERNMENT,
                AuthorityClass.PROVINCIAL_PUBLIC_HEALTH,
            ),
            (
                AuthorityClass.PROVINCIAL_GOVERNMENT,
                AuthorityClass.WILDFIRE_PREPAREDNESS,
            ),
            (
                AuthorityClass.PROVINCIAL_GOVERNMENT,
                AuthorityClass.LOCAL_AUTHORITY,
            ),
        )
        for left_authority, right_authority in authority_pairs:
            with self.subTest(left=left_authority, right=right_authority):
                alpha = replace(
                    make_chunk(
                        "alpha",
                        "Residents must attach one teal readiness tag to the emergency bag zipper.",
                        authority=left_authority.value,
                    ),
                    document_sha256="a" * 64,
                )
                beta = replace(
                    make_chunk(
                        "beta",
                        "Residents must attach one orange readiness tag to the emergency bag zipper.",
                        parent="parent-b",
                        authority=right_authority.value,
                    ),
                    source_id="source-b",
                    document_sha256="b" * 64,
                )
                with tempfile.TemporaryDirectory() as directory:
                    runtime, _provider, _config = await make_runtime(
                        Path(directory), chunks=[alpha, beta]
                    )
                    response = await runtime.service.ask(
                        QueryRequest(
                            question="What colour readiness tag belongs on the emergency bag?"
                        )
                    )

                self.assertEqual(response.response_mode, ResponseMode.CONFLICT)
                self.assertIn("cannot determine which", response.answer.casefold())

    async def test_date_and_jurisdiction_differences_surface_without_precedence(self) -> None:
        cases = (
            (
                "The 2024 guide says residents must attach one teal readiness tag to the bag zipper.",
                "The 2025 guide says residents must attach one orange readiness tag to the bag zipper.",
            ),
            (
                "Residents in Kelowna must attach one teal readiness tag to the bag zipper.",
                "Residents in Kamloops must attach one orange readiness tag to the bag zipper.",
            ),
        )
        for left_text, right_text in cases:
            with self.subTest(left=left_text, right=right_text):
                alpha = replace(make_chunk("alpha", left_text), document_sha256="a" * 64)
                beta = replace(
                    make_chunk("beta", right_text, parent="parent-b"),
                    source_id="source-b",
                    document_sha256="b" * 64,
                )
                with tempfile.TemporaryDirectory() as directory:
                    runtime, _provider, _config = await make_runtime(
                        Path(directory), chunks=[alpha, beta]
                    )
                    response = await runtime.service.ask(
                        QueryRequest(question="What readiness tag is required?")
                    )

                self.assertEqual(response.response_mode, ResponseMode.CONFLICT)
                self.assertTrue(response.validation and response.validation.accepted)

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
