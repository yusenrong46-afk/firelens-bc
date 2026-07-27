"""Build the existing React client into Vercel's public asset directory."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "prototype/firelens-rag-ui"
    output = frontend / "dist/client"
    public = root / "public"

    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)

    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(output, public)


if __name__ == "__main__":
    main()
