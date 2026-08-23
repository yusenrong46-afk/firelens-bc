"""One logical runtime-file set shared by Vercel and Docker/Render."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWLIST_RELATIVE = "config/runtime_artifact_allowlist.v1.json"


def load_allowlist(repository_root: Path) -> dict[str, Any]:
    payload = json.loads((repository_root / ALLOWLIST_RELATIVE).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("runtime allowlist must be an object")
    return payload


def logical_runtime_paths(allowlist: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for path in allowlist["required_files"]:
        if str(path).startswith(("data/", "config/", "apps/web/dist/")):
            paths.append(path)
    runtime_data = allowlist["runtime_data"]
    for key in (
        "corpus",
        "corpus_manifest",
        "vector_matrix",
        "vector_manifest",
        "repair_registry",
        "document_context",
    ):
        path = runtime_data[key]
        if path not in paths:
            paths.append(path)
    candidate = allowlist["candidate_configuration"]["logical_path"]
    if candidate not in paths:
        paths.append(candidate)
    return paths


def verify_packaging_parity(repository_root: Path) -> dict[str, Any]:
    allowlist = load_allowlist(repository_root)
    required = logical_runtime_paths(allowlist)
    dockerfile = (repository_root / "Dockerfile").read_text(encoding="utf-8")
    vercel = json.loads((repository_root / "vercel.json").read_text(encoding="utf-8"))
    include_files = vercel["services"]["firelens"]["functions"]["**/*.py"]["includeFiles"]
    missing_docker = [path for path in required if not _dockerfile_covers(dockerfile, path)]
    missing_vercel = [
        path
        for path in required
        if path not in include_files and not _glob_covers(include_files, path)
    ]
    document_context = allowlist["runtime_data"]["document_context"]
    return {
        "status": "passed" if not missing_docker and not missing_vercel else "failed",
        "logical_paths": required,
        "missing_from_dockerfile": missing_docker,
        "missing_from_vercel": missing_vercel,
        "document_context_in_docker": _dockerfile_covers(dockerfile, document_context),
        "document_context_in_vercel": _glob_covers(include_files, document_context),
        "reuse": [
            "python -m firelens.runtime_artifact inventory",
            "python -m firelens.runtime_artifact compare",
            "python scripts/qualify_deployment_gates.py",
            "python scripts/candidate_evidence.py",
        ],
    }


def _dockerfile_covers(dockerfile: str, path: str) -> bool:
    if path in dockerfile:
        return True
    current = Path(path)
    while current.parts:
        posix = current.as_posix()
        if re.search(rf"COPY(?:\s+\S+)+\s+\.?/?{re.escape(posix)}\b", dockerfile):
            return True
        current = current.parent
    return False


def _glob_covers(include_files: str, path: str) -> bool:
    if path in include_files:
        return True
    current = Path(path)
    while current.parts:
        posix = current.as_posix()
        if f"{posix}/**" in include_files:
            return True
        current = current.parent
    if path.startswith("data/processed/firelens_static_corpus.") and (
        "firelens_static_corpus.*" in include_files
    ):
        return True
    if (
        path.startswith("config/runtime_")
        and path.endswith(".json")
        and ("config/runtime_*.json" in include_files)
    ):
        return True
    if (
        path
        in {
            "data/index/firelens_vectors.npy",
            "data/index/firelens_vectors.manifest.json",
        }
        and "firelens_vectors.{npy,manifest.json}" in include_files
    ):
        return True
    return False
