#!/usr/bin/env python3
"""Write the exact commit-bound runtime candidate included in deployment artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

COMMIT = re.compile(r"^[0-9a-f]{40}$")
BENCHMARK_ID = re.compile(r"^[a-z][a-z0-9_]{1,127}$")
ALLOWED_STRATEGIES = {"original_v1", "metadata_context_v1", "document_context_v2"}


def _object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def build_runtime_candidate(
    *,
    commit: str,
    benchmark_id: str,
    release_version: str,
    corpus_manifest_path: Path,
    vector_manifest_path: Path,
) -> dict[str, str]:
    """Build a strict candidate document from the shipped corpus/vector manifests."""

    if COMMIT.fullmatch(commit) is None:
        raise ValueError("runtime candidate commit must be a full lowercase Git SHA")
    if BENCHMARK_ID.fullmatch(benchmark_id) is None:
        raise ValueError("runtime candidate benchmark ID is invalid")
    if not release_version or release_version != release_version.strip():
        raise ValueError("runtime candidate release version is invalid")
    corpus = _object(corpus_manifest_path, "corpus manifest")
    vector = _object(vector_manifest_path, "vector manifest")
    corpus_version = corpus.get("corpus_version")
    embedding_model = vector.get("embedding_model")
    retrieval_text_strategy = vector.get("retrieval_text_strategy")
    if not isinstance(corpus_version, str) or not corpus_version:
        raise ValueError("corpus manifest has no corpus version")
    if vector.get("corpus_version") != corpus_version:
        raise ValueError("vector and corpus manifests use different corpus versions")
    if not isinstance(embedding_model, str) or not embedding_model:
        raise ValueError("vector manifest has no embedding model")
    if retrieval_text_strategy not in ALLOWED_STRATEGIES:
        raise ValueError("vector manifest retrieval strategy is unsupported")
    return {
        "schema_version": "firelens.runtime_candidate.v1",
        "candidate_id": f"{benchmark_id.replace('_', '-')}:{commit}",
        "release_version": release_version,
        "build_commit": commit,
        "corpus_version": corpus_version,
        "embedding_model": embedding_model,
        "retrieval_text_strategy": retrieval_text_strategy,
    }


def write_runtime_candidate(output: Path, document: dict[str, str]) -> None:
    """Atomically replace only the generated candidate file, never a symlink."""

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("runtime candidate output cannot be a symlink")
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--commit",
        default=os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("FIRELENS_BUILD_COMMIT"),
    )
    parser.add_argument("--benchmark-id", default="firelens_v1_5_2")
    parser.add_argument(
        "--release-version",
        default=os.environ.get("FIRELENS_RELEASE_VERSION", "1.5.0-rc.1"),
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=Path("data/processed/firelens_static_corpus.manifest.json"),
    )
    parser.add_argument(
        "--vector-manifest",
        type=Path,
        default=Path("data/index/firelens_vectors.manifest.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = build_runtime_candidate(
            commit=args.commit or "",
            benchmark_id=args.benchmark_id,
            release_version=args.release_version,
            corpus_manifest_path=args.corpus_manifest,
            vector_manifest_path=args.vector_manifest,
        )
        write_runtime_candidate(args.output, document)
    except (OSError, ValueError) as exc:
        print(f"runtime candidate refused: {exc}")
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
