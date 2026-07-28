from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_helpers import make_chunk

from firelens.graphrag_experiment import prepare_graphrag_workspace, select_graphrag


class GraphRAGExperimentTests(unittest.TestCase):
    def test_export_retains_raw_chunk_provenance_and_no_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = prepare_graphrag_workspace(
                [make_chunk("raw-1", "Exact raw guidance")],
                output_dir=Path(directory),
                openrouter_base_url="https://openrouter.ai/api/v1",
            )
            exported = json.loads(Path(report["input_path"]).read_text(encoding="utf-8"))
            settings = Path(report["settings_path"]).read_text(encoding="utf-8")
        self.assertEqual(exported["id"], "raw-1")
        self.assertEqual(exported["text"], "Exact raw guidance")
        self.assertIn("${OPENROUTER_API_KEY}", settings)
        self.assertNotIn("sk-", settings)

    def test_promotion_requires_a_distinct_win_and_complete_provenance(self) -> None:
        selected, _reason = select_graphrag(
            standard_passes=8,
            graph_passes=10,
            case_count=12,
            provenance_rate=1.0,
            ordinary_regressions=0,
            p95_latency_seconds=9.0,
            cost_ratio=4.0,
        )
        self.assertTrue(selected)
        rejected, _reason = select_graphrag(
            standard_passes=8,
            graph_passes=10,
            case_count=12,
            provenance_rate=0.99,
            ordinary_regressions=0,
            p95_latency_seconds=9.0,
            cost_ratio=4.0,
        )
        self.assertFalse(rejected)
