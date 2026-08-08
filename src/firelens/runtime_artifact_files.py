"""Fail-closed staged filesystem traversal and prohibited-path policy."""

from __future__ import annotations

import stat
from pathlib import Path, PurePosixPath
from typing import Any

from firelens.runtime_artifact_common import (
    RuntimeArtifactError,
    assert_not_symlink,
    logical_path,
)


def collect_files(root: Path) -> dict[str, Path]:
    """Collect single-link regular files without following or escaping symlinks."""

    assert_not_symlink(root, context="artifact root")
    if not root.is_dir():
        raise RuntimeArtifactError(f"artifact root is not a directory: {root}")
    resolved_root = root.resolve(strict=True)
    files: dict[str, Path] = {}
    try:
        descendants = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as exc:
        raise RuntimeArtifactError("artifact root cannot be traversed") from exc
    for path in descendants:
        assert_not_symlink(path, context="artifact input")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeArtifactError(f"artifact contains a non-regular input: {path}")
        metadata = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeArtifactError(
                f"artifact input must be a single-link regular file: {path}"
            )
        try:
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(resolved_root).as_posix()
        except (OSError, ValueError) as exc:
            raise RuntimeArtifactError(f"artifact input escapes its root: {path}") from exc
        logical = logical_path(relative, context="artifact logical path")
        if logical in files:
            raise RuntimeArtifactError(f"artifact contains duplicate logical path: {logical}")
        files[logical] = path
    if not files:
        raise RuntimeArtifactError("artifact root contains no files")
    return files


def prohibited_reason(path: str, contract: dict[str, Any]) -> str | None:
    """Return the frozen prohibition violated by a logical path, if any."""

    rules = contract["prohibited"]
    lowered = path.lower()
    parts = PurePosixPath(lowered).parts
    basename = parts[-1]
    for prefix in rules["prefixes"]:
        prefix_lower = prefix.lower()
        if lowered == prefix_lower or lowered.startswith(prefix_lower + "/"):
            return f"prohibited prefix {prefix}"
    for segment in rules["segments"]:
        if segment.lower() in parts:
            return f"prohibited path segment {segment}"
    if basename in {value.lower() for value in rules["basenames"]}:
        return f"prohibited basename {basename}"
    if basename.startswith(".env.") or basename.startswith(".git"):
        return f"prohibited environment/Git file {basename}"
    for token in rules["basename_tokens"]:
        if token.lower() in basename:
            return f"prohibited basename token {token}"
    for suffix in rules["suffixes"]:
        if basename.endswith(suffix.lower()) and lowered != "requirements.lock":
            return f"prohibited suffix {suffix}"
    return None
