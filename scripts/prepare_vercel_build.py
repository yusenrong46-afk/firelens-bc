"""Build the existing React client into Vercel's public asset directory."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from firelens.config import DEFAULT_RELEASE_VERSION
from firelens.privacy_policy import (
    APPROVED_PRODUCTION_PRIVACY,
    resolve_openrouter_privacy_from_env,
)
from firelens.runtime_candidate import build_runtime_candidate, write_runtime_candidate


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "apps/web"
    output = frontend / "dist/client"
    public = root / "public"

    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)

    commit = os.environ.get("VERCEL_GIT_COMMIT_SHA")
    if not commit:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    candidate = build_runtime_candidate(
        commit=commit,
        benchmark_id="firelens_v1_5_2",
        release_version=os.environ.get("FIRELENS_RELEASE_VERSION") or DEFAULT_RELEASE_VERSION,
        corpus_manifest_path=(root / "data/processed/firelens_static_corpus.manifest.json"),
        vector_manifest_path=root / "data/index/firelens_vectors.manifest.json",
        rerank_model=os.environ.get("FIRELENS_RERANK_MODEL"),
        generation_model=os.environ.get("FIRELENS_GENERATION_MODEL"),
        privacy=resolve_openrouter_privacy_from_env(
            os.environ.get, default=APPROVED_PRODUCTION_PRIVACY
        ),
    )
    write_runtime_candidate(root / "config/runtime_candidate.v1.json", candidate)

    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(output, public)


if __name__ == "__main__":
    main()
