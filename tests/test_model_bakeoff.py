from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from firelens import model_bakeoff
from firelens.contracts import GroundedDraft, SupportStatus


class _FakeService:
    def __init__(self, retrieval_cost: float) -> None:
        self.retrieval_cost = retrieval_cost
        self.search_calls = 0

    async def search(self, request: object) -> SimpleNamespace:
        del request
        self.search_calls += 1
        return SimpleNamespace(
            support=SimpleNamespace(status=SupportStatus.ANSWERABLE),
            retrieval=SimpleNamespace(
                provider_usage={"embedding": {"cost": self.retrieval_cost}},
                reranked_hits=[],
            ),
            plan=SimpleNamespace(normalized_question="test question"),
        )


class _FakeRuntime:
    def __init__(self, retrieval_cost: float) -> None:
        self.service = _FakeService(retrieval_cost)
        self.corpus_version = "test-corpus"
        self.chunks: list[object] = []
        self.problems: list[str] = []
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeProvider:
    generation_cost = 0.0
    generation_calls = 0

    def __init__(self, config: object) -> None:
        del config

    async def generate_grounded(
        self, messages: object, *, output_schema: object
    ) -> SimpleNamespace:
        del messages, output_schema
        type(self).generation_calls += 1
        return SimpleNamespace(
            model="fake/model",
            draft=GroundedDraft(
                answer_type="grounded",
                claims=[{"text": "Supported claim.", "evidence_quote_ids": ["q1"]}],
            ),
            usage={"cost": type(self).generation_cost},
        )

    async def aclose(self) -> None:
        return None


class ModelBakeoffBudgetTests(unittest.TestCase):
    def _run(
        self,
        runtime: _FakeRuntime,
        *,
        cases: list[object],
        models: tuple[str, ...] = ("fake/model",),
        max_cost_usd: float = 1.0,
        retrieval_reserve: float = 0.0,
        generation_reserve: float = 0.0,
    ) -> dict[str, object]:
        _FakeProvider.generation_calls = 0
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            dataset_path = directory_path / "dataset.json"
            dataset_path.write_text("{}\n", encoding="utf-8")
            config = SimpleNamespace(
                generation_model="fake/model",
                model_copy=lambda **kwargs: SimpleNamespace(**kwargs),
            )
            with (
                patch.object(model_bakeoff, "load_runtime", return_value=runtime),
                patch.object(model_bakeoff, "_balanced_cases", return_value=cases),
                patch.object(model_bakeoff, "OpenRouterProvider", _FakeProvider),
                patch.object(
                    model_bakeoff, "build_evidence_packet", return_value=SimpleNamespace()
                ),
                patch.object(model_bakeoff, "generation_messages", return_value=[]),
                patch.object(model_bakeoff, "draft_schema", return_value={}),
                patch.object(
                    model_bakeoff,
                    "validate_draft",
                    return_value=SimpleNamespace(
                        model_dump=lambda **kwargs: {"accepted": True}
                    ),
                ),
                patch.object(model_bakeoff, "_write_review_packet"),
            ):
                return asyncio.run(
                    model_bakeoff.run_model_bakeoff(
                        config,
                        dataset_path=dataset_path,
                        output_path=directory_path / "report.json",
                        review_packet_path=directory_path / "review.md",
                        models=models,
                        case_limit=1,
                        max_cost_usd=max_cost_usd,
                        retrieval_case_cost_reserve_usd=retrieval_reserve,
                        generation_call_cost_reserve_usd=generation_reserve,
                    )
                )

    def test_reservation_blocks_retrieval_before_any_paid_call(self) -> None:
        runtime = _FakeRuntime(retrieval_cost=0.0)
        case = SimpleNamespace(id="case-1", category="test", question="Question?")

        report = self._run(
            runtime,
            cases=[case],
            max_cost_usd=0.10,
            retrieval_reserve=0.01,
            generation_reserve=0.10,
        )

        self.assertEqual(runtime.service.search_calls, 0)
        self.assertEqual(_FakeProvider.generation_calls, 0)
        self.assertTrue(report["budget_reservation_exhausted"])
        self.assertFalse(report["complete"])

    def test_observed_retrieval_overrun_stops_generation_and_marks_incomplete(self) -> None:
        runtime = _FakeRuntime(retrieval_cost=0.11)
        case = SimpleNamespace(id="case-1", category="test", question="Question?")

        report = self._run(
            runtime,
            cases=[case],
            max_cost_usd=0.10,
        )

        self.assertEqual(runtime.service.search_calls, 1)
        self.assertEqual(_FakeProvider.generation_calls, 0)
        self.assertTrue(report["cost_budget_exceeded"])
        self.assertFalse(report["complete"])

    def test_empty_packets_or_models_cannot_report_complete(self) -> None:
        no_packets = self._run(_FakeRuntime(retrieval_cost=0.0), cases=[])
        no_models = self._run(
            _FakeRuntime(retrieval_cost=0.0),
            cases=[SimpleNamespace(id="case-1", category="test", question="Question?")],
            models=(),
        )

        self.assertEqual(no_packets["packet_count"], 0)
        self.assertFalse(no_packets["complete"])
        self.assertEqual(no_models["packet_count"], 1)
        self.assertFalse(no_models["complete"])
