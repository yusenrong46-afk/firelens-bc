from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from firelens.config import FireLensConfig
from firelens.providers.fake import FakeProvider
from firelens.qualification import run_frozen_retrieval_qualification
from firelens.runtime import load_runtime


class FrozenQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_holdout_runner_never_claims_the_development_46_of_47_gate(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = FireLensConfig.from_env(project_root)
        dimensions = 1536
        runtime = load_runtime(config, provider=FakeProvider(dimensions=dimensions))
        with tempfile.TemporaryDirectory() as directory:
            report = await run_frozen_retrieval_qualification(
                runtime,
                dataset_path=project_root / "data/evaluation/benchmark_v1.yaml",
                dataset_manifest_path=(
                    project_root / "data/evaluation/benchmark_v1.manifest.json"
                ),
                output_path=Path(directory) / "qualification.json",
                repetitions=2,
            )
        await runtime.aclose()

        self.assertEqual(report["split"], "holdout")
        self.assertFalse(report["tuning_allowed"])
        self.assertFalse(report["relevance_addendum_used"])
        self.assertEqual(report["case_count_per_repetition"], 16)
        self.assertFalse(report["requested_46_of_47_gate_compatible"])
        self.assertFalse(report["owner_approved"])
        self.assertFalse(report["qualified"])
        self.assertEqual(len(report["repetition_reports"]), 2)

    async def test_v1_5_candidate_has_47_frozen_cases_but_requires_owner_review(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = FireLensConfig.from_env(project_root)
        runtime = load_runtime(config, provider=FakeProvider(dimensions=1536))
        with tempfile.TemporaryDirectory() as directory:
            report = await run_frozen_retrieval_qualification(
                runtime,
                dataset_path=(
                    project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
                ),
                dataset_manifest_path=(
                    project_root
                    / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
                ),
                output_path=Path(directory) / "qualification.json",
                repetitions=1,
            )
        await runtime.aclose()

        self.assertEqual(report["case_count_per_repetition"], 47)
        self.assertTrue(report["requested_46_of_47_gate_compatible"])
        self.assertFalse(report["owner_approved"])
        self.assertFalse(report["qualified"])
