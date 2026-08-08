#!/usr/bin/env python3
"""Read-only repository snapshot for the project-mastery-tutor skill.

It prints Git identity, a redacted worktree state, file-map highlights,
configuration entry points, and declared test/build commands. It never reads
secret values and never writes repository files.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


def find_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit("repository root not found")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return (
        result.stdout.strip()
        if result.returncode == 0
        else f"unavailable ({result.stderr.strip()})"
    )


def files(root: Path) -> list[str]:
    ignored = {".git", ".venv", "node_modules", "output", "dist", "__pycache__"}
    paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        paths.append(path.relative_to(root).as_posix())
    return sorted(paths)


def package_summary(root: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = payload.get("project", {})
        result["python_project"] = {
            "name": project.get("name"),
            "requires_python": project.get("requires-python"),
            "has_cli": bool(project.get("scripts")),
        }
    package = root / "prototype/firelens-rag-ui/package.json"
    if package.is_file():
        payload = json.loads(package.read_text(encoding="utf-8"))
        result["frontend"] = {
            "name": payload.get("name"),
            "scripts": sorted((payload.get("scripts") or {}).keys()),
        }
    return result


def main() -> int:
    root = find_root(Path(__file__).resolve())
    names = files(root)
    highlights = [
        path
        for path in names
        if path
        in {
            "README.md",
            "pyproject.toml",
            "Makefile",
            "app.py",
            "Dockerfile",
            "vercel.json",
            "render.yaml",
        }
        or path.startswith(("src/firelens/", "tests/", "prototype/firelens-rag-ui/src/"))
    ]
    print(f"root: {root}")
    print(f"branch: {git(root, 'branch', '--show-current')}")
    print(f"commit: {git(root, 'rev-parse', 'HEAD')}")
    print("status:")
    status = git(root, "status", "--short")
    print(status or "clean")
    print("packages:")
    print(json.dumps(package_summary(root), indent=2, sort_keys=True))
    print(f"highlighted_files: {len(highlights)}")
    for path in highlights:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
