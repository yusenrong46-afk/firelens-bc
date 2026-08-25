from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from firelens.benchmark import file_sha256, load_benchmark
from firelens.config import FireLensConfig
from firelens.providers.fake import FakeProvider
from firelens.qualification import run_frozen_retrieval_qualification
from firelens.retrieval_review import write_retrieval_review_template
from firelens.runtime import load_runtime


class FrozenQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_holdout_runner_never_claims_the_development_46_of_47_gate(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = FireLensConfig.from_env(project_root)
        dimensions = 1536
        runtime = load_runtime(config, provider=FakeProvider(dimensions=dimensions))
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "firelens.benchmark_support.clean_checkout_commit",
                return_value="a" * 40,
            ):
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

    async def test_v2_manifest_is_permanent_regression_without_running_retrieval(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        dataset_path = project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
        manifest_path = (
            project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
        )

        dataset = load_benchmark(dataset_path, require_release_shape=False)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        answerable = [
            case
            for case in dataset.cases
            if case.split == "holdout" and case.acceptable_evidence
        ]

        self.assertEqual(len(answerable), 47)
        self.assertEqual(manifest["answerable_holdout_case_count"], 47)
        self.assertTrue(manifest["configuration_frozen_before_dataset"])
        self.assertEqual(manifest["evaluation_role"], "permanent_regression")
        self.assertEqual(manifest["baseline_policy"], "paired")
        self.assertIn("fake provider", manifest["retirement_reason"])
        self.assertTrue(manifest["owner_review_required_before_ranking"])
        self.assertEqual(manifest["required_repetitions"], 3)

    async def test_v1_5_runner_rejects_unapproved_review_before_provider_calls(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = FireLensConfig.from_env(project_root)
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(config, provider=provider)
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
            manifest_path = Path(directory) / "v3.manifest.json"
            manifest = json.loads(
                (
                    project_root
                    / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
                ).read_text()
            )
            manifest.update(
                evaluation_role="sealed_release_qualification",
                baseline_policy="required_after_only",
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            review_path = Path(directory) / "review.yaml"
            write_retrieval_review_template(dataset_path, review_path)
            with self.assertRaisesRegex(PermissionError, "complete hash-bound owner review"):
                await run_frozen_retrieval_qualification(
                    runtime,
                    dataset_path=dataset_path,
                    dataset_manifest_path=manifest_path,
                    output_path=Path(directory) / "qualification.json",
                    owner_review_path=review_path,
                    repetitions=3,
                )
        await runtime.aclose()

        self.assertEqual(provider.plan_calls, 0)
        self.assertEqual(provider.embed_calls, 0)
        self.assertEqual(provider.rerank_calls, 0)

    async def test_sealed_role_guard_does_not_depend_on_dataset_name(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source_dataset = project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
        source_manifest = (
            project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
        )
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(project_root), provider=provider)
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            dataset_path = directory_path / "fresh-v3.yaml"
            manifest_path = directory_path / "fresh-v3.manifest.json"
            dataset = yaml.safe_load(source_dataset.read_text(encoding="utf-8"))
            dataset["dataset_version"] = "firelens_v1_5_2_retrieval.v3"
            dataset_path.write_text(yaml.safe_dump(dataset, sort_keys=False), encoding="utf-8")
            manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
            manifest["dataset_version"] = dataset["dataset_version"]
            manifest["dataset_sha256"] = file_sha256(dataset_path)
            manifest["evaluation_role"] = "sealed_release_qualification"
            manifest["baseline_policy"] = "required_after_only"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "exactly 3 repetitions"):
                await run_frozen_retrieval_qualification(
                    runtime,
                    dataset_path=dataset_path,
                    dataset_manifest_path=manifest_path,
                    output_path=directory_path / "unused.json",
                    repetitions=1,
                )
        await runtime.aclose()

        self.assertEqual(provider.plan_calls, 0)
        self.assertEqual(provider.embed_calls, 0)
        self.assertEqual(provider.rerank_calls, 0)

    async def test_v2_regression_runner_no_longer_claims_sealed_gate(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = FireLensConfig.from_env(project_root)
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(config, provider=provider)
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "firelens.benchmark_support.clean_checkout_commit",
                return_value="a" * 40,
            ):
                report = await run_frozen_retrieval_qualification(
                    runtime,
                    dataset_path=(
                        project_root / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
                    ),
                    dataset_manifest_path=(
                        project_root
                        / "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"
                    ),
                    output_path=Path(directory) / "v2-regression.json",
                    repetitions=1,
                )
        await runtime.aclose()

        self.assertFalse(report["sealed_qualification_eligible"])
        self.assertFalse(report["requested_46_of_47_gate_compatible"])
