#!/usr/bin/env python3
"""Write the exact commit-bound runtime candidate included in deployment artifacts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from firelens.config import DEFAULT_RELEASE_VERSION
from firelens.privacy_policy import (
    APPROVED_PRODUCTION_PRIVACY,
    resolve_openrouter_privacy_from_env,
)
from firelens.runtime_candidate import (
    DEFAULT_BENCHMARK_ID,
    build_runtime_candidate,
    write_runtime_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--commit",
        default=os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("FIRELENS_BUILD_COMMIT"),
    )
    parser.add_argument("--benchmark-id", default=DEFAULT_BENCHMARK_ID)
    parser.add_argument(
        "--release-version",
        default=os.environ.get("FIRELENS_RELEASE_VERSION") or DEFAULT_RELEASE_VERSION,
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
    parser.add_argument(
        "--rerank-model",
        default=os.environ.get("FIRELENS_RERANK_MODEL"),
    )
    parser.add_argument(
        "--generation-model",
        default=os.environ.get("FIRELENS_GENERATION_MODEL"),
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
            rerank_model=args.rerank_model,
            generation_model=args.generation_model,
            privacy=resolve_openrouter_privacy_from_env(
                os.environ.get, default=APPROVED_PRODUCTION_PRIVACY
            ),
        )
        write_runtime_candidate(args.output, document)
    except (OSError, ValueError) as exc:
        print(f"runtime candidate refused: {exc}")
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
