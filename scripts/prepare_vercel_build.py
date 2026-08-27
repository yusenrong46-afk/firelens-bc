"""Build the existing React client into Vercel's public asset directory."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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

_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class BuildIdentityError(RuntimeError):
    """Sanitized failure when a Vercel build has no exact Git SHA."""


def _validated_commit(value: str | None, *, source: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if _FULL_COMMIT.fullmatch(stripped) is None:
        raise BuildIdentityError(
            f"build commit from {source} is not a full 40-character lowercase SHA"
        )
    return stripped


def _resolve_build_commit(root: Path) -> str:
    configured = _validated_commit(
        os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("FIRELENS_BUILD_COMMIT"),
        source="environment",
    )
    if configured is not None:
        return configured
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise BuildIdentityError(
            "build commit is missing: set FIRELENS_BUILD_COMMIT or "
            "VERCEL_GIT_COMMIT_SHA to a full 40-character lowercase SHA "
            "before uploading a tree without .git"
        ) from exc
    commit = _validated_commit(resolved, source="git")
    if commit is None:
        raise BuildIdentityError("git rev-parse HEAD returned an empty commit")
    return commit


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "apps/web"
    output = frontend / "dist/client"
    public = root / "public"

    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)

    try:
        commit = _resolve_build_commit(root)
    except BuildIdentityError as exc:
        raise SystemExit(str(exc)) from exc
    candidate = build_runtime_candidate(
        commit=commit,
        benchmark_id=DEFAULT_BENCHMARK_ID,
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
