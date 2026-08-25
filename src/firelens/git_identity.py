"""Fail-closed Git identity helpers for generated evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path


def clean_checkout_commit(
    repository_root: Path,
    *,
    context: str,
    fallback: str | None = None,
) -> str | None:
    """Return HEAD only when a Git checkout is clean, or a fallback outside Git.

    Evidence generated from a dirty checkout cannot truthfully be attributed to
    ``HEAD``.  A directory that is not a Git worktree keeps the historical
    fallback behavior used by packaged/runtime tests, while a detected Git
    worktree fails closed if either status or identity cannot be verified.
    """

    git_metadata_present = (repository_root / ".git").exists()
    try:
        worktree = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if git_metadata_present:
            raise ValueError(f"{context} could not verify clean Git identity") from exc
        return fallback
    if worktree.returncode != 0 or worktree.stdout.strip() != "true":
        if git_metadata_present:
            detail = (worktree.stderr or worktree.stdout).strip() or "Git worktree unavailable"
            raise ValueError(f"{context} could not verify clean Git identity: {detail}")
        return fallback

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{context} could not verify clean Git identity") from exc
    if status.stdout:
        raise ValueError(f"{context} requires a clean working tree")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError(f"{context} did not resolve a full lowercase Git commit")
    return commit
