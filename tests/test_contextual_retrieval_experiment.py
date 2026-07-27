from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_helpers import make_runtime

from firelens.contextual_retrieval_experiment import (
    CANDIDATE_A,
    CANDIDATE_B,
    CANDIDATE_C,
    run_contextual_retrieval_comparison,
    select_contextual_strategy,
)
from firelens.contracts import RetrievalTextStrategy
from firelens.retrieval.embeddings import sha256_file


class ContextualRetrievalSelectionTests(unittest.TestCase):
    def test_selection_requires_safe_two_point_gain_over_planned_original(self) -> None:
        candidates = {
            CANDIDATE_B: {
                "complete": True,
                "metrics": {"rerank_recall_at_5": 0.80},
            },
            CANDIDATE_C: {
                "complete": True,
                "metrics": {"rerank_recall_at_5": 0.81},
            },
        }
        selected, reason = select_contextual_strategy(candidates, safety_passed=True)
        self.assertEqual(selected, RetrievalTextStrategy.ORIGINAL_V1.value)
        self.assertIn("two-point", reason)

        candidates[CANDIDATE_C]["metrics"]["rerank_recall_at_5"] = 0.82
        selected, _ = select_contextual_strategy(candidates, safety_passed=True)
        self.assertEqual(selected, RetrievalTextStrategy.METADATA_CONTEXT_V1.value)

        selected, _ = select_contextual_strategy(candidates, safety_passed=False)
        self.assertEqual(selected, RetrievalTextStrategy.ORIGINAL_V1.value)


class ContextualRetrievalRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_provider_builds_isolated_index_and_reuses_saved_plans(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        dataset_path = project_root / "data/evaluation/benchmark_v1_1_conversation.yaml"
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            runtime, provider, config = await make_runtime(temporary)
            await runtime.aclose()
            governed_before = {
                "matrix": sha256_file(config.vector_matrix_path),
                "manifest": sha256_file(config.vector_manifest_path),
                "cache": sha256_file(config.embedding_cache_path),
            }
            output_path = temporary / "reports" / "contextual.json"
            experiment_dir = temporary / "isolated-experiment"

            report = await run_contextual_retrieval_comparison(
                config,
                dataset_path=dataset_path,
                output_path=output_path,
                experiment_dir=experiment_dir,
                provider=provider,
            )

            self.assertEqual(report["case_count"], 8)
            self.assertFalse(report["holdout_opened"])
            self.assertEqual(set(report["candidates"]), {CANDIDATE_A, CANDIDATE_B, CANDIDATE_C})
            for candidate in report["candidates"].values():
                self.assertEqual(
                    set(candidate["metrics"]),
                    {
                        "bm25_recall_at_20",
                        "dense_recall_at_20",
                        "fused_recall_at_20",
                        "rerank_recall_at_5",
                        "rerank_mrr_at_5",
                    },
                )
            self.assertEqual(provider.plan_calls, 8)
            b_rows = report["details"][CANDIDATE_B]
            c_rows = report["details"][CANDIDATE_C]
            self.assertEqual(
                [row["plan_sha256"] for row in b_rows],
                [row["plan_sha256"] for row in c_rows],
            )
            self.assertTrue(report["safety_checks"]["governed_original_index_unchanged"])
            self.assertTrue(report["safety_checks"]["passed"])
            self.assertEqual(
                report["selected_retrieval_text_strategy"],
                RetrievalTextStrategy.ORIGINAL_V1.value,
            )

            contextual_manifest = Path(report["contextual_index"]["manifest_path"])
            self.assertTrue(contextual_manifest.is_file())
            manifest = json.loads(contextual_manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["retrieval_text_strategy"],
                RetrievalTextStrategy.METADATA_CONTEXT_V1.value,
            )
            self.assertTrue(output_path.is_file())
            governed_after = {
                "matrix": sha256_file(config.vector_matrix_path),
                "manifest": sha256_file(config.vector_manifest_path),
                "cache": sha256_file(config.embedding_cache_path),
            }
            self.assertEqual(governed_before, governed_after)
