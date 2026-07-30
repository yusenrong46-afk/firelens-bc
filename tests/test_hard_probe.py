from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_hard_probe import file_sha256, load_dataset


class HardProbeDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.dataset_path = self.root / "data/evaluation/hard_probe.v1.yaml"
        self.manifest_path = self.root / "data/evaluation/hard_probe.v1.manifest.json"

    def test_dataset_shape_and_manifest_hash_are_locked(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(len(dataset.cases), 105)
        self.assertEqual(len(dataset.browser_cases), 7)
        self.assertEqual(len(dataset.fixture_cases), 10)
        self.assertEqual(manifest["dataset_sha256"], file_sha256(self.dataset_path))
        self.assertFalse(manifest["sealed_release_holdout"])

    def test_modified_dataset_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "hard_probe.v1.yaml"
            changed.write_bytes(self.dataset_path.read_bytes() + b"\n")

            with self.assertRaisesRegex(ValueError, "hash"):
                load_dataset(changed, self.manifest_path)
