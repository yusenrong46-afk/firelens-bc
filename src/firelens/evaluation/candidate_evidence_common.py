"""Shared constants and filesystem primitives for candidate evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "firelens.candidate_evidence.v2"
SECURITY_SCHEMA_VERSION = "firelens.candidate_security.v1"
QUALIFICATION_SCHEMA_VERSION = "firelens.candidate_qualification.v2"
BUILD_TYPE = "https://firelens-bc.local/build-types/candidate-evidence/v2"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
STALE_REPORT_PATH = re.compile(r"(^|/)v1_5[^/]*(/|$)", re.IGNORECASE)

MATERIAL_PATHS = (
    "requirements.lock",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "Dockerfile",
    "vercel.json",
    "render.yaml",
    "config/runtime_artifact_allowlist.v1.json",
    "data/processed/firelens_static_corpus.manifest.json",
    "data/processed/firelens_static_corpus.chunks.jsonl",
    "data/index/firelens_vectors.manifest.json",
    "data/index/firelens_vectors.npy",
    "data/typed_claims/high_risk_v1.yaml",
    "docs/openapi.v1.json",
    "data/evaluation/hard_probe.v1.yaml",
    "data/evaluation/hard_probe.v1.manifest.json",
    "data/evaluation/v1_6_user_end_questions_50.json",
    "data/evaluation/v1_6_user_end_questions_50.manifest.json",
    "docs/reports/V1_6_STRUCTURED_PUBLICATION_HARD_PROBE.json",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_1_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_3_DECISIONS.yaml",
    "docs/reports/V1_6_SOURCE_REPAIR_SCOPE_DECISIONS.yaml",
    ".github/workflows/candidate.yml",
)
SUBJECT_FILE = "config/runtime_candidate.v1.json"
SUBJECT_TREE = "apps/web/dist"
RAW_EVIDENCE_NAMES = (
    "inputs/python-audit.json",
    "inputs/npm-audit.json",
    "inputs/dependency-licenses.json",
    "inputs/checkout-state.json",
    "inputs/build-environment.json",
    "inputs/command-outcomes.json",
    "inputs/credential-absence.json",
    "inputs/workflow-identity.json",
    "inputs/structured-publication-eval.json",
    "inputs/hard-probe.json",
    "inputs/hard-probe-baseline.json",
)
GENERATED_NAMES = (
    "candidate-sbom.cdx.json",
    "candidate-provenance.intoto.json",
    "candidate-security-summary.json",
    "candidate-qualification-summary.json",
)

REQUIRED_COMMAND_POLICIES: dict[str, frozenset[int]] = {
    "lockfiles": frozenset({0}),
    "action_pins": frozenset({0}),
    "make_verify": frozenset({0}),
    "runtime_candidate": frozenset({0}),
    "frontend_build": frozenset({0}),
    "structured_publication_eval": frozenset({0}),
    # The permanent runner returns one when any of 105 cases fail. The v2
    # qualification validator owns the frozen 86/no-regression gate.
    "hard_probe_offline": frozenset({0, 1}),
    "python_audit": frozenset({0, 1}),
    "npm_audit": frozenset({0, 1}),
    "dependency_licenses": frozenset({0}),
    "candidate_artifact_scope": frozenset({0}),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def strict_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe evidence path: {relative}")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"candidate evidence requires a regular file: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"candidate evidence path escapes its root: {relative}")
    return path


def file_record(root: Path, relative: str) -> dict[str, object]:
    data = strict_file(root, relative).read_bytes()
    return {"name": relative, "sha256": sha256_bytes(data), "size_bytes": len(data)}


def tree_record(root: Path, relative: str) -> dict[str, object]:
    tree = root / relative
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError(f"candidate evidence requires a regular directory: {relative}")
    files: list[dict[str, object]] = []
    total_size = 0
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"candidate subject tree contains a symlink: {path}")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        total_size += len(data)
        files.append({"name": name, "sha256": sha256_bytes(data), "size_bytes": len(data)})
    if not files:
        raise ValueError(f"candidate subject tree is empty: {relative}")
    digest = sha256_bytes(canonical_bytes(files))
    return {
        "name": relative,
        "sha256": digest,
        "size_bytes": total_size,
        "file_count": len(files),
        "files": files,
    }


def load_json(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular JSON file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc
