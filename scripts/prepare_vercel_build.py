"""Build the existing React client into Vercel's public asset directory."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

try:
    from scripts.write_runtime_candidate import (
        build_runtime_candidate,
        write_runtime_candidate,
    )
except ModuleNotFoundError as error:  # Direct execution puts scripts/ on sys.path.
    if error.name != "scripts":
        raise
    from write_runtime_candidate import (  # type: ignore[no-redef]
        build_runtime_candidate,
        write_runtime_candidate,
    )


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
        release_version=os.environ.get("FIRELENS_RELEASE_VERSION", "1.5.0-rc.1"),
        corpus_manifest_path=(root / "data/processed/firelens_static_corpus.manifest.json"),
        vector_manifest_path=root / "data/index/firelens_vectors.manifest.json",
    )
    write_runtime_candidate(root / "config/runtime_candidate.v1.json", candidate)

    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(output, public)


if __name__ == "__main__":
    main()
