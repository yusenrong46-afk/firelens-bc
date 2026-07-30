from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_actions_pinned import unpinned_actions
from scripts.check_lockfiles import check_node_lock, check_python_lock


class CIControlTests(unittest.TestCase):
    def test_repository_actions_are_sha_pinned(self) -> None:
        self.assertEqual(unpinned_actions(), [])

    def test_unpinned_action_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "bad.yml"
            workflow.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
            self.assertTrue(unpinned_actions(Path(directory)))

    def test_lockfiles_match_declared_dependencies(self) -> None:
        self.assertEqual(check_python_lock(), [])
        self.assertEqual(check_node_lock(), [])
