from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pydantic import ValidationError
from rag_helpers import make_runtime

from firelens.benchmark import BenchmarkCase, load_benchmark, run_benchmark


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
