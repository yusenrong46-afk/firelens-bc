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
    BENCHMARK_ID,
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


def _resolve_build_benchmark_id() -> str:
    """Read the deploy-bound benchmark identity, preserving legacy builds."""

    configured = os.environ.get("FIRELENS_BENCHMARK_ID")
    benchmark_id = configured.strip() if configured is not None else DEFAULT_BENCHMARK_ID
    if BENCHMARK_ID.fullmatch(benchmark_id) is None:
        raise BuildIdentityError("build benchmark ID from FIRELENS_BENCHMARK_ID is invalid")
    return benchmark_id


def _build_candidate(root: Path, *, commit: str, benchmark_id: str) -> dict[str, str]:
    """Build the deployment candidate from one already-validated identity."""

    return build_runtime_candidate(
        commit=commit,
        benchmark_id=benchmark_id,
        release_version=os.environ.get("FIRELENS_RELEASE_VERSION") or DEFAULT_RELEASE_VERSION,
        corpus_manifest_path=(root / "data/processed/firelens_static_corpus.manifest.json"),
        vector_manifest_path=root / "data/index/firelens_vectors.manifest.json",
        rerank_model=os.environ.get("FIRELENS_RERANK_MODEL"),
        generation_model=os.environ.get("FIRELENS_GENERATION_MODEL"),
        privacy=resolve_openrouter_privacy_from_env(
            os.environ.get, default=APPROVED_PRODUCTION_PRIVACY
        ),
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "apps/web"
    output = frontend / "dist/client"
    public = root / "public"

    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)

    try:
        commit = _resolve_build_commit(root)
        benchmark_id = _resolve_build_benchmark_id()
    except BuildIdentityError as exc:
        raise SystemExit(str(exc)) from exc
    candidate = _build_candidate(root, commit=commit, benchmark_id=benchmark_id)
    write_runtime_candidate(root / "config/runtime_candidate.v1.json", candidate)

    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(output, public)


if __name__ == "__main__":
    main()
