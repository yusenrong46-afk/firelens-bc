from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pydantic import ValidationError
from rag_helpers import make_runtime

from firelens.benchmark import (
    BenchmarkCase,
    ConversationBenchmarkCase,
    file_sha256,
    load_benchmark,
    load_conversation_benchmark,
    run_benchmark,
    run_conversation_benchmark,
)


class BenchmarkSchemaTests(unittest.TestCase):
    def test_release_benchmark_has_locked_shape(self) -> None:
        root = Path(__file__).resolve().parents[1]
        dataset = load_benchmark(root / "data/evaluation/benchmark_v1.yaml")
        self.assertEqual(len(dataset.cases), 100)
        self.assertEqual(
            Counter(case.split for case in dataset.cases),
            {"development": 60, "holdout": 20, "red_team": 20},
        )

    def test_unknown_case_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            BenchmarkCase.model_validate(
                {
                    "id": "V1-DEV-001",
                    "split": "development",
                    "category": "insufficient_evidence",
                    "risk_level": "ordinary",
                    "question": "Unrelated?",
                    "expected_route": "static",
                    "expected_status": "abstention",
                    "surprise": True,
                }
            )

    def test_conversation_addendum_has_locked_shape_and_hash(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "data/evaluation/benchmark_v1_1_conversation.yaml"
        dataset = load_conversation_benchmark(path)
        self.assertEqual(len(dataset.cases), 50)
        self.assertEqual(
            Counter(case.split for case in dataset.cases),
            {"development": 30, "holdout": 10, "red_team": 10},
        )
        self.assertEqual(
            Counter(case.category for case in dataset.cases),
            {
                "capability": 10,
                "contextual_followup": 10,
                "adjacent_background": 10,
                "tangent": 10,
                "mixed_adversarial": 10,
            },
        )
        self.assertEqual(
            file_sha256(path),
            "922ab1a5e61866bff7f113b59f82d10c0b7a165f83584979d3cce83763ad70d9",
        )
        manifest = json.loads(
            (root / "data/evaluation/benchmark_v1_1_conversation.manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["dataset_sha256"], file_sha256(path))
        self.assertEqual(
            manifest["parent_v1_dataset_sha256"],
            file_sha256(root / "data/evaluation/benchmark_v1.yaml"),
        )

    def test_conversation_history_unknown_fields_are_rejected(self) -> None:
        root = Path(__file__).resolve().parents[1]
        case = load_conversation_benchmark(
            root / "data/evaluation/benchmark_v1_1_conversation.yaml"
        ).cases[0]
        payload = case.model_dump(mode="json")
        payload["history"] = [{"role": "user", "content": "Hello", "surprise": True}]
        with self.assertRaises(ValidationError):
            ConversationBenchmarkCase.model_validate(payload)

    def test_conversation_expected_path_is_cross_validated(self) -> None:
        root = Path(__file__).resolve().parents[1]
        case = load_conversation_benchmark(
            root / "data/evaluation/benchmark_v1_1_conversation.yaml"
        ).cases[0]
        payload = case.model_dump(mode="json")
        payload["expected_response_mode"] = "background"
        with self.assertRaises(ValidationError):
            ConversationBenchmarkCase.model_validate(payload)


class BenchmarkExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_red_team_routes_without_provider_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            runtime, provider, _ = await make_runtime(temporary)
            report = await run_benchmark(
                runtime,
                dataset_path=root / "data/evaluation/benchmark_v1.yaml",
                output_path=temporary / "report.json",
                review_packet_path=temporary / "review.md",
                splits={"red_team"},
            )
            self.assertEqual(report["case_count"], 20)
            self.assertEqual(report["metrics"]["safety_route_accuracy"], 1.0)
            self.assertEqual(report["metrics"]["safety_status_accuracy"], 1.0)
            self.assertEqual(provider.generate_calls, 0)
            self.assertTrue((temporary / "review.md").is_file())

    async def test_conversation_red_team_has_zero_provider_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            runtime, provider, _ = await make_runtime(temporary)
            before = (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            )
            report = await run_conversation_benchmark(
                runtime,
                dataset_path=root / "data/evaluation/benchmark_v1_1_conversation.yaml",
                output_path=temporary / "conversation-red-report.json",
                review_packet_path=temporary / "conversation-red-review.md",
                splits={"red_team"},
                execution_mode="offline_fake",
            )
            after = (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            )
            self.assertEqual(report["case_count"], 10)
            self.assertEqual(report["metrics"]["deterministic_safety_route_accuracy"], 1.0)
            self.assertEqual(report["metrics"]["paid_call_boundary_accuracy"], 1.0)
            self.assertEqual(report["metrics"]["reported_cost_usd"], 0.0)
            self.assertEqual(before, after)

    async def test_conversation_development_report_and_review_are_serialized(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            runtime, provider, _ = await make_runtime(temporary)
            report_path = temporary / "conversation-report.json"
            review_path = temporary / "conversation-review.md"
            report = await run_conversation_benchmark(
                runtime,
                dataset_path=root / "data/evaluation/benchmark_v1_1_conversation.yaml",
                output_path=report_path,
                review_packet_path=review_path,
                splits={"development"},
                execution_mode="offline_fake",
            )
            self.assertEqual(report["case_count"], 30)
            self.assertEqual(report["execution_mode"], "offline_fake")
            self.assertIn("planner_relation_accuracy", report["metrics"])
            self.assertIn("adjacent_background", report["metrics"])
            self.assertIn("paid_call_boundary_accuracy", report["metrics"])
            self.assertGreater(provider.plan_calls, 0)
            self.assertGreater(provider.generate_calls, 0)
            self.assertTrue(report_path.is_file())
            review = review_path.read_text(encoding="utf-8")
            self.assertIn("FireLens V1.1 conversation semantic review packet", review)
            self.assertIn("[ ] supported  [ ] unsupported  [ ] unclear", review)
