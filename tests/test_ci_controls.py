from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_actions_pinned import unpinned_actions, unpinned_dockerfile_bases
from scripts.check_lockfiles import check_node_lock, check_python_lock


class CIControlTests(unittest.TestCase):
    def test_repository_actions_are_sha_pinned(self) -> None:
        self.assertEqual(unpinned_actions(), [])
        self.assertEqual(unpinned_dockerfile_bases(), [])

    def test_unpinned_action_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "bad.yml"
            workflow.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
            self.assertTrue(unpinned_actions(Path(directory)))

    def test_tagged_docker_action_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "bad.yml"
            workflow.write_text("steps:\n  - uses: docker://alpine:3.20\n", encoding="utf-8")
            self.assertTrue(unpinned_actions(Path(directory)))

    def test_digest_pinned_docker_action_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "good.yml"
            workflow.write_text(
                "steps:\n  - uses: docker://alpine@sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            self.assertEqual(unpinned_actions(Path(directory)), [])

    def test_tagged_dockerfile_base_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dockerfile = Path(directory) / "Dockerfile"
            dockerfile.write_text("FROM python:3.12-slim AS runtime\n", encoding="utf-8")
            self.assertTrue(unpinned_dockerfile_bases(dockerfile))

    def test_digest_pinned_dockerfile_base_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dockerfile = Path(directory) / "Dockerfile"
            dockerfile.write_text(
                "FROM python:3.12-slim@sha256:" + "a" * 64 + " AS runtime\n",
                encoding="utf-8",
            )
            self.assertEqual(unpinned_dockerfile_bases(dockerfile), [])

    def test_secret_scan_includes_nonignored_untracked_files(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            tracked = repository / "tracked.txt"
            tracked.write_text("safe\n", encoding="utf-8")
            subprocess.run(["git", "add", tracked.name], cwd=repository, check=True)
            untracked = repository / "product-secret.txt"
            untracked.write_text(
                "sk" + "-or-v1-" + "synthetic-regression-token\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(root / "scripts/secret_scan.py")],
                cwd=repository,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(untracked.name, result.stderr + result.stdout)

    def test_lockfiles_match_declared_dependencies(self) -> None:
        self.assertEqual(check_python_lock(), [])
        self.assertEqual(check_node_lock(), [])
