"""Regression tests for request-owned ordinary-background fallback."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from rag_helpers import make_chunk, make_runtime

from firelens.contracts import (
    PlanningDecision,
    PlanningResponse,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    SupportDecision,
    SupportStatus,
)
from firelens.providers.fake import FakeProvider


class RelatedPlanner(FakeProvider):
    """Force retrieval so the service, not a tangent shortcut, owns the fallback."""

    async def plan(self, messages, *, output_schema):  # type: ignore[no-untyped-def]
        del messages, output_schema
        self.plan_calls += 1
        return PlanningResponse(
            model="fake/related-planner",
            decision=PlanningDecision(
                relation=QueryRelation.GROUNDED_CANDIDATE,
                retrieval_queries=["wildfire background"],
                explanation="Related corpus material is available.",
            ),
        )


class GeneralBackgroundFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_low_risk_support_outcomes_use_background(self) -> None:
        """Adjacent packets cannot turn an ordinary explanation into a conflict or handoff."""

        outcomes = (
            SupportStatus.INSUFFICIENT_EVIDENCE,
            SupportStatus.PARTIAL,
            SupportStatus.CONFLICT,
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            for status in outcomes:
                with self.subTest(status=status):
                    support = SupportDecision(
                        status=status,
                        reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
                        explanation="The nearby reviewed material is not direct support.",
                    )
                    with patch(
                        "firelens.answering.service.decide_support", return_value=support
                    ):
                        response = await runtime.service.ask(
                            QueryRequest(question="How do wildfires spread?")
                        )
                    self.assertEqual(response.response_mode, ResponseMode.BACKGROUND)
                    self.assertTrue(response.validation and response.validation.accepted)
                    self.assertFalse(response.evidence)
            await runtime.aclose()

    async def test_directly_supported_low_risk_request_keeps_grounded_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            support = SupportDecision(
                status=SupportStatus.ANSWERABLE,
                reason_code=ReasonCode.APPROVED_STATIC_EVIDENCE,
                explanation="Approved stable guidance is available.",
            )
            with patch("firelens.answering.service.decide_support", return_value=support):
                response = await runtime.service.ask(
                    QueryRequest(question="How do wildfires spread?")
                )
            await runtime.aclose()

        self.assertEqual(response.response_mode, ResponseMode.GROUNDED)
        self.assertTrue(response.evidence)

    async def test_ordinary_wildfire_explanations_remain_labelled_background(self) -> None:
        questions = (
            "Why are wildfires dangerous?",
            "How do wildfires spread?",
            "Why do some pine cones open after fire?",
            "Why do some pine cones open if exposed to fire?",
            "How can fire ecology change if a forest burns?",
            "What are controlled burns?",
            "Can you explain fire ecology?",
            "What caused the 2023 BC wildfire season?",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            for question in questions:
                with self.subTest(question=question):
                    response = await runtime.service.ask(QueryRequest(question=question))
                    self.assertEqual(response.response_mode, ResponseMode.BACKGROUND)
                    self.assertTrue(response.validation and response.validation.accepted)
                    self.assertFalse(response.evidence)
            await runtime.aclose()

    async def test_reviewed_guidance_live_and_personalized_requests_never_fall_back(
        self,
    ) -> None:
        questions = (
            "What should I know about wildfire smoke?",
            "What should I pack in a grab-and-go bag?",
            "What does an evacuation alert mean?",
            "What should I do if I smell gas?",
            "What fires are active right now in BC?",
            "What is the current AQHI?",
            "Should I evacuate my home?",
            "What is the current history of controlled burns?",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            for question in questions:
                with self.subTest(question=question):
                    response = await runtime.service.ask(QueryRequest(question=question))
                    self.assertNotEqual(response.response_mode, ResponseMode.BACKGROUND)
            await runtime.aclose()

    async def test_unrelated_question_ignores_stale_selected_live_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            response = await runtime.service.ask(
                QueryRequest(
                    question="How do wildfires spread?",
                    context={"selected_live_result_id": "R1"},
                )
            )
            await runtime.aclose()

        self.assertEqual(response.response_mode, ResponseMode.BACKGROUND)

    async def test_deictic_selected_record_question_does_not_use_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner()
            )
            response = await runtime.service.ask(
                QueryRequest(
                    question="How large is it?",
                    context={"selected_live_result_id": "R1"},
                )
            )
            await runtime.aclose()

        self.assertNotEqual(response.response_mode, ResponseMode.BACKGROUND)

    async def test_explicit_named_source_or_identifier_never_becomes_background(self) -> None:
        chunk = replace(
            make_chunk("SRC-01", "PreparedBC is a provincial program."),
            source_id="preparedbc_wildfire_guide",
            title="PreparedBC Wildfire Guide",
        )
        questions = (
            "What does PreparedBC say about fire ecology?",
            "According to the PreparedBC guide, explain fire ecology.",
            "What does SRC-01 say about fire ecology?",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner(), chunks=[chunk]
            )
            for question in questions:
                with self.subTest(question=question):
                    response = await runtime.service.ask(QueryRequest(question=question))
                    self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
                    self.assertTrue(response.related_links)
                    self.assertIn("requested reviewed source", response.answer or "")
            await runtime.aclose()

    async def test_explicit_preparedbc_exclusion_request_uses_source_handoff(self) -> None:
        chunk = replace(
            make_chunk(
                "preparedbc-bag",
                "Build grab-and-go bags with water, food, and copies of important documents.",
            ),
            source_id="preparedbc_wildfire_guide",
            title="PreparedBC Wildfire Guide",
            publisher="PreparedBC",
        )
        question = "According to PreparedBC, what is not needed in a grab-and-go bag?"
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, _config = await make_runtime(Path(directory), chunks=[chunk])
            response = await runtime.service.ask(QueryRequest(question=question))
            await runtime.aclose()

        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertEqual(response.reason_code, ReasonCode.NO_APPROVED_EVIDENCE)
        self.assertEqual(response.claims, [])
        self.assertEqual(response.evidence, [])
        self.assertTrue(response.related_links)
        self.assertEqual(provider.generate_calls, 0)
        self.assertIn("found the requested reviewed source", response.answer or "")
        self.assertNotIn("Build grab-and-go bags", response.answer or "")

    async def test_known_explicit_source_identifier_keeps_reviewed_source_handoff(self) -> None:
        chunk = replace(
            make_chunk("SRC-01", "PreparedBC is a provincial program."),
            source_id="preparedbc_wildfire_guide",
            title="PreparedBC Wildfire Guide",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, _provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner(), chunks=[chunk]
            )
            response = await runtime.service.ask(
                QueryRequest(question="What does SRC-01 say about fire ecology?")
            )
            await runtime.aclose()

        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertTrue(response.related_links)
        self.assertIn("found the requested reviewed source", response.answer or "")

    async def test_unknown_explicit_source_identifier_fails_closed_without_evidence(
        self,
    ) -> None:
        unrelated_chunk = replace(
            make_chunk("SRC-99", "PreparedBC is a provincial program."),
            source_id="preparedbc_wildfire_guide",
            title="PreparedBC Wildfire Guide",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, _config = await make_runtime(
                Path(directory), provider=RelatedPlanner(), chunks=[unrelated_chunk]
            )
            before = (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            )
            execution = await runtime.service.execute_ask(
                QueryRequest(question="What does SRC-01 say about fire ecology?")
            )
            response = execution.response
            await runtime.aclose()

        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertEqual(response.reason_code, ReasonCode.NO_APPROVED_EVIDENCE)
        self.assertEqual(execution.plan.route, QueryRoute.RELATED)
        self.assertEqual(response.claims, [])
        self.assertEqual(response.evidence, [])
        self.assertEqual(response.related_links, [])
        self.assertEqual(
            (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            ),
            before,
        )
        self.assertIn("could not find", response.answer or "")
        self.assertIn("SRC-01", response.answer or "")
        self.assertNotIn("found the requested reviewed source", response.answer or "")
