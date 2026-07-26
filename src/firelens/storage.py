"""Small atomic-file helpers for generated FireLens artifacts."""

from __future__ import annotations

import fcntl
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def atomic_text_writer(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temp_path = Path(stream.name)
        try:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    os.replace(temp_path, path)


@contextmanager
def atomic_binary_writer(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w+b",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temp_path = Path(stream.name)
        try:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    os.replace(temp_path, path)


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Fail fast when another process is building the same artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Artifact build is already in progress: {path}") from exc
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
