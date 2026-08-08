"""Fail-closed runtime artifact inventory and cross-platform comparison.

This module verifies a staged deployment root. It deliberately does not inspect a
repository checkout as if it were a deployment artifact: the staging step is the
security boundary that must include only runtime inputs.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import numpy as np
import yaml

CONTRACT_SCHEMA = "firelens.runtime_artifact_allowlist.v1"
CANDIDATE_SCHEMA = "firelens.runtime_candidate.v1"
INVENTORY_SCHEMA = "firelens.runtime_artifact_inventory.v1"
COMPARISON_SCHEMA = "firelens.runtime_artifact_comparison.v1"
SUPPORTED_PLATFORMS = frozenset({"docker", "vercel"})
SUPPORTED_RETRIEVAL_STRATEGIES = frozenset(
    {"original_v1", "metadata_context_v1", "document_context_v2"}
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
CSS_REFERENCE_PATTERN = re.compile(
    r"url\(\s*(['\"]?)(.*?)\1\s*\)|@import\s+(?:url\()?\s*(['\"])(.*?)\3",
    re.IGNORECASE,
)
JS_REFERENCE_PATTERNS = (
    re.compile(r"(?:\bimport\s*\(|\bfrom\s*)\s*(['\"])([^'\"]+)\1"),
    re.compile(r"\bimport\s*(['\"])([^'\"]+)\1"),
    re.compile(r"\bnew\s+URL\s*\(\s*(['\"])([^'\"]+)\1\s*,\s*import\.meta\.url"),
)
CHUNK_KEYS = {
    "schema_version",
    "chunk_id",
    "parent_record_id",
    "source_id",
    "title",
    "publisher",
    "canonical_url",
    "temporal_class",
    "authority_class",
    "document_sha256",
    "page_number",
    "chunk_index",
    "section_title",
    "text",
    "char_count",
    "retrieved_at",
    "source_type",
    "section_id",
    "locator",
    "review_provenance",
}


class RuntimeArtifactError(ValueError):
    """Raised when an artifact or inventory violates the frozen contract."""


@dataclass(frozen=True)
class ArtifactIdentity:
    """Externally supplied identity expected inside one built artifact."""

    platform: str
    platform_root: str
    artifact_id: str
    candidate_id: str
    release_version: str
    build_commit: str


class _HTMLReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if value is None:
                continue
            if name.lower() in {"src", "href", "poster"}:
                self.references.append(value)
            elif name.lower() == "srcset":
                self.references.extend(
                    candidate.strip().split()[0]
                    for candidate in value.split(",")
                    if candidate.strip()
                )


def _exact_keys(payload: dict[str, Any], expected: set[str], *, context: str) -> None:
    observed = set(payload)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise RuntimeArtifactError(
            f"{context} keys differ from the contract (missing={missing}, extra={extra})"
        )


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeArtifactError(f"cannot securely read artifact input: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise RuntimeArtifactError(f"artifact input is not a single-link file: {path}")
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RuntimeArtifactError(f"artifact input changed while hashing: {path}")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _file_metadata(files: dict[str, Path]) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for logical, path in files.items():
        metadata = path.stat(follow_symlinks=False)
        result[logical] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
    return result


def _read_json(path: Path, *, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeArtifactError(f"{context} is not readable JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeArtifactError(f"{context} must be a JSON object")
    return payload


def _logical_path(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeArtifactError(f"{context} must be a canonical POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or value in {".", ".."}:
        raise RuntimeArtifactError(f"{context} must be a canonical POSIX relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeArtifactError(f"{context} contains path traversal")
    return value


def _platform_root(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeArtifactError("platform_root must be a canonical absolute POSIX path")
    path = PurePosixPath(value)
    if not path.is_absolute() or value != path.as_posix() or ".." in path.parts:
        raise RuntimeArtifactError("platform_root must be a canonical absolute POSIX path")
    if value == "/":
        raise RuntimeArtifactError("platform_root cannot be the filesystem root")
    return value


def _nonempty_identity(value: str, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeArtifactError(f"{field} must be a non-empty printable string")
    return value


def _validate_identity(identity: ArtifactIdentity) -> None:
    if not isinstance(identity.platform, str) or identity.platform not in SUPPORTED_PLATFORMS:
        raise RuntimeArtifactError("platform must be docker or vercel")
    _platform_root(identity.platform_root)
    _nonempty_identity(identity.artifact_id, field="artifact_id")
    _nonempty_identity(identity.candidate_id, field="candidate_id")
    _nonempty_identity(identity.release_version, field="release_version")
    if not isinstance(identity.build_commit, str) or not GIT_COMMIT_PATTERN.fullmatch(
        identity.build_commit
    ):
        raise RuntimeArtifactError("build_commit must be a lowercase 40- or 64-hex commit")


def _assert_not_symlink(path: Path, *, context: str) -> None:
    try:
        if path.is_symlink():
            raise RuntimeArtifactError(f"{context} cannot be a symlink: {path}")
    except OSError as exc:
        raise RuntimeArtifactError(f"cannot inspect {context}: {path}") from exc


def _load_contract(path: Path) -> tuple[dict[str, Any], str]:
    _assert_not_symlink(path, context="contract")
    if not path.is_file():
        raise RuntimeArtifactError(f"contract is missing: {path}")
    contract = _read_json(path, context="runtime artifact contract")
    _exact_keys(
        contract,
        {
            "schema_version",
            "contract_id",
            "candidate_configuration",
            "required_files",
            "conditional_files",
            "python",
            "frontend",
            "runtime_data",
            "prohibited",
        },
        context="runtime artifact contract",
    )
    if contract["schema_version"] != CONTRACT_SCHEMA:
        raise RuntimeArtifactError("runtime artifact contract has an unsupported schema")
    _nonempty_identity(contract["contract_id"], field="contract_id")

    candidate = contract["candidate_configuration"]
    if not isinstance(candidate, dict):
        raise RuntimeArtifactError("candidate_configuration must be an object")
    _exact_keys(
        candidate,
        {"logical_path", "schema_version", "required_fields"},
        context="candidate_configuration",
    )
    _logical_path(candidate["logical_path"], context="candidate configuration path")
    if candidate["schema_version"] != CANDIDATE_SCHEMA:
        raise RuntimeArtifactError("candidate configuration schema is unsupported")
    required_candidate_fields = candidate["required_fields"]
    if (
        not isinstance(required_candidate_fields, list)
        or not required_candidate_fields
        or any(not isinstance(field, str) or not field for field in required_candidate_fields)
        or len(required_candidate_fields) != len(set(required_candidate_fields))
    ):
        raise RuntimeArtifactError("candidate required_fields must be unique strings")
    expected_candidate_fields = {
        "schema_version",
        "candidate_id",
        "release_version",
        "build_commit",
        "corpus_version",
        "embedding_model",
        "retrieval_text_strategy",
    }
    if set(required_candidate_fields) != expected_candidate_fields:
        raise RuntimeArtifactError(
            "candidate required_fields must bind the complete runtime and release identity"
        )

    required_files = contract["required_files"]
    if not isinstance(required_files, list) or not required_files:
        raise RuntimeArtifactError("required_files must be a non-empty list")
    normalized_required = [
        _logical_path(value, context="required file") for value in required_files
    ]
    if len(normalized_required) != len(set(normalized_required)):
        raise RuntimeArtifactError("required_files contains duplicates")

    conditional_files = contract["conditional_files"]
    if not isinstance(conditional_files, list) or len(conditional_files) != 1:
        raise RuntimeArtifactError("exactly one document-context conditional is required")
    conditional = conditional_files[0]
    if not isinstance(conditional, dict):
        raise RuntimeArtifactError("conditional file entry must be an object")
    _exact_keys(
        conditional,
        {
            "logical_path",
            "candidate_field",
            "vector_manifest_field",
            "required_value",
        },
        context="conditional file",
    )
    _logical_path(conditional["logical_path"], context="conditional file path")
    if conditional["required_value"] != "document_context_v2":
        raise RuntimeArtifactError("document-context conditional value is unsupported")

    python = contract["python"]
    if not isinstance(python, dict):
        raise RuntimeArtifactError("python contract must be an object")
    _exact_keys(python, {"entrypoint", "source_root", "package"}, context="python contract")
    _logical_path(python["entrypoint"], context="Python entrypoint")
    _logical_path(python["source_root"], context="Python source root")
    if python["package"] != "firelens":
        raise RuntimeArtifactError("Python package must remain firelens")

    frontend = contract["frontend"]
    if not isinstance(frontend, dict):
        raise RuntimeArtifactError("frontend contract must be an object")
    _exact_keys(
        frontend,
        {"root", "index", "vite_manifest", "allowed_suffixes"},
        context="frontend contract",
    )
    for field in ("root", "index", "vite_manifest"):
        _logical_path(frontend[field], context=f"frontend {field}")
    suffixes = frontend["allowed_suffixes"]
    if (
        not isinstance(suffixes, list)
        or not suffixes
        or any(not isinstance(suffix, str) or not suffix.startswith(".") for suffix in suffixes)
        or len(suffixes) != len(set(suffixes))
    ):
        raise RuntimeArtifactError("frontend allowed_suffixes must be unique suffixes")

    runtime_data = contract["runtime_data"]
    if not isinstance(runtime_data, dict):
        raise RuntimeArtifactError("runtime_data must be an object")
    _exact_keys(
        runtime_data,
        {
            "corpus",
            "corpus_manifest",
            "vector_matrix",
            "vector_manifest",
            "repair_registry",
            "document_context",
        },
        context="runtime_data",
    )
    for field, value in runtime_data.items():
        _logical_path(value, context=f"runtime_data.{field}")
    if conditional["logical_path"] != runtime_data["document_context"]:
        raise RuntimeArtifactError(
            "document-context conditional must target runtime_data.document_context"
        )
    if (
        conditional["candidate_field"] != "retrieval_text_strategy"
        or conditional["vector_manifest_field"] != "retrieval_text_strategy"
    ):
        raise RuntimeArtifactError(
            "document-context conditional must bind both retrieval_text_strategy fields"
        )
    if (
        frontend["index"] != f"{frontend['root']}/index.html"
        or frontend["vite_manifest"] != f"{frontend['root']}/.vite/manifest.json"
    ):
        raise RuntimeArtifactError("frontend index and Vite manifest must be inside its root")
    mandatory_required = {
        python["entrypoint"],
        "pyproject.toml",
        "requirements.lock",
        "config/runtime_artifact_allowlist.v1.json",
        candidate["logical_path"],
        frontend["index"],
        frontend["vite_manifest"],
        runtime_data["corpus"],
        runtime_data["corpus_manifest"],
        runtime_data["vector_matrix"],
        runtime_data["vector_manifest"],
        runtime_data["repair_registry"],
    }
    if not mandatory_required.issubset(set(normalized_required)):
        raise RuntimeArtifactError("required_files omits a mandatory runtime identity or input")
    if runtime_data["document_context"] in normalized_required:
        raise RuntimeArtifactError(
            "document_context must remain conditional, not unconditionally required"
        )

    prohibited = contract["prohibited"]
    if not isinstance(prohibited, dict):
        raise RuntimeArtifactError("prohibited rules must be an object")
    _exact_keys(
        prohibited,
        {"prefixes", "segments", "basenames", "basename_tokens", "suffixes"},
        context="prohibited rules",
    )
    for field, values in prohibited.items():
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise RuntimeArtifactError(f"prohibited.{field} must contain unique strings")
    for prefix in prohibited["prefixes"]:
        _logical_path(prefix, context="prohibited prefix")
    mandatory_prohibited = {
        "prefixes": {
            ".git",
            ".venv",
            "data/evaluation",
            "data/raw",
            "data/sources",
            "docs",
            "output",
            "tests",
        },
        "segments": {
            "adjudication",
            "browser",
            "evaluation",
            "intermediates",
            "node_modules",
            "review",
            "ux",
        },
        "basenames": {".env", "embedding_cache.jsonl"},
        "basename_tokens": {
            "adjudicat",
            "embedding_cache",
            "holdout",
            "owner_review",
            "sealed",
            "ux_review",
        },
        "suffixes": {".lock", ".map", ".pyc"},
    }
    for field, mandatory in mandatory_prohibited.items():
        if not mandatory.issubset(set(prohibited[field])):
            raise RuntimeArtifactError(f"prohibited.{field} omits mandatory artifact classes")

    return contract, _sha256_file(path)


def _collect_files(root: Path) -> dict[str, Path]:
    _assert_not_symlink(root, context="artifact root")
    if not root.is_dir():
        raise RuntimeArtifactError(f"artifact root is not a directory: {root}")
    resolved_root = root.resolve(strict=True)
    files: dict[str, Path] = {}
    try:
        descendants = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as exc:
        raise RuntimeArtifactError("artifact root cannot be traversed") from exc
    for path in descendants:
        _assert_not_symlink(path, context="artifact input")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeArtifactError(f"artifact contains a non-regular input: {path}")
        metadata = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeArtifactError(
                f"artifact input must be a single-link regular file: {path}"
            )
        try:
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(resolved_root).as_posix()
        except (OSError, ValueError) as exc:
            raise RuntimeArtifactError(f"artifact input escapes its root: {path}") from exc
        logical = _logical_path(relative, context="artifact logical path")
        if logical in files:
            raise RuntimeArtifactError(f"artifact contains duplicate logical path: {logical}")
        files[logical] = path
    if not files:
        raise RuntimeArtifactError("artifact root contains no files")
    return files


def _prohibited_reason(path: str, contract: dict[str, Any]) -> str | None:
    rules = contract["prohibited"]
    lowered = path.lower()
    parts = PurePosixPath(lowered).parts
    basename = parts[-1]
    for prefix in rules["prefixes"]:
        prefix_lower = prefix.lower()
        if lowered == prefix_lower or lowered.startswith(prefix_lower + "/"):
            return f"prohibited prefix {prefix}"
    for segment in rules["segments"]:
        if segment.lower() in parts:
            return f"prohibited path segment {segment}"
    if basename in {value.lower() for value in rules["basenames"]}:
        return f"prohibited basename {basename}"
    if basename.startswith(".env.") or basename.startswith(".git"):
        return f"prohibited environment/Git file {basename}"
    for token in rules["basename_tokens"]:
        if token.lower() in basename:
            return f"prohibited basename token {token}"
    for suffix in rules["suffixes"]:
        if basename.endswith(suffix.lower()) and lowered != "requirements.lock":
            return f"prohibited suffix {suffix}"
    return None


def _load_candidate(
    files: dict[str, Path], contract: dict[str, Any], identity: ArtifactIdentity
) -> dict[str, Any]:
    candidate_contract = contract["candidate_configuration"]
    path = candidate_contract["logical_path"]
    candidate = _read_json(files[path], context="runtime candidate configuration")
    expected_fields = set(candidate_contract["required_fields"])
    _exact_keys(candidate, expected_fields, context="runtime candidate configuration")
    if candidate.get("schema_version") != candidate_contract["schema_version"]:
        raise RuntimeArtifactError("runtime candidate configuration has an unsupported schema")
    for field, expected in (
        ("candidate_id", identity.candidate_id),
        ("release_version", identity.release_version),
        ("build_commit", identity.build_commit),
    ):
        if candidate.get(field) != expected:
            raise RuntimeArtifactError(f"runtime candidate {field} differs from build identity")
    for field in ("corpus_version", "embedding_model"):
        value = candidate.get(field)
        if not isinstance(value, str):
            raise RuntimeArtifactError(f"runtime candidate {field} must be a string")
        _nonempty_identity(value, field=f"runtime candidate {field}")
    if candidate.get("retrieval_text_strategy") not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise RuntimeArtifactError("runtime candidate retrieval_text_strategy is unsupported")
    return candidate


def _load_corpus(
    files: dict[str, Path], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime_data = contract["runtime_data"]
    corpus_path = files[runtime_data["corpus"]]
    chunks: list[dict[str, Any]] = []
    try:
        with corpus_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} is invalid JSON"
                    ) from exc
                if not isinstance(chunk, dict):
                    raise RuntimeArtifactError(f"corpus line {line_number} is not an object")
                _exact_keys(chunk, CHUNK_KEYS, context=f"corpus line {line_number}")
                if chunk.get("schema_version") != "chunk_record.v2":
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} has an unsupported schema"
                    )
                for field in ("chunk_id", "source_id", "document_sha256", "review_provenance"):
                    if not isinstance(chunk.get(field), str) or not chunk[field]:
                        raise RuntimeArtifactError(
                            f"corpus line {line_number} is missing {field}"
                        )
                if not SHA256_PATTERN.fullmatch(chunk["document_sha256"]):
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} has an invalid document_sha256"
                    )
                page = chunk.get("page_number")
                if page is not None and (
                    isinstance(page, bool) or not isinstance(page, int) or page < 1
                ):
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} has an invalid page_number"
                    )
                if (
                    isinstance(chunk.get("chunk_index"), bool)
                    or not isinstance(chunk.get("chunk_index"), int)
                    or chunk["chunk_index"] < 1
                ):
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} has an invalid chunk_index"
                    )
                if not isinstance(chunk.get("text"), str) or not chunk["text"].strip():
                    raise RuntimeArtifactError(f"corpus line {line_number} has empty text")
                if chunk.get("char_count") != len(chunk["text"]):
                    raise RuntimeArtifactError(
                        f"corpus line {line_number} has an inconsistent char_count"
                    )
                chunks.append(chunk)
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeArtifactError("corpus is not readable UTF-8 JSONL") from exc
    if not chunks:
        raise RuntimeArtifactError("corpus is empty")
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise RuntimeArtifactError("corpus contains duplicate chunk IDs")

    manifest = _read_json(files[runtime_data["corpus_manifest"]], context="corpus manifest")
    if manifest.get("combined_chunk_file") != runtime_data["corpus"]:
        raise RuntimeArtifactError("corpus manifest points outside the contracted corpus path")
    if manifest.get("combined_chunk_count") != len(chunks):
        raise RuntimeArtifactError("corpus manifest chunk count does not match the corpus")
    if manifest.get("repair_provenance_policy") != "human_verified_only.v1":
        raise RuntimeArtifactError("corpus manifest lacks approved repair provenance policy")
    if not isinstance(manifest.get("corpus_version"), str) or not manifest["corpus_version"]:
        raise RuntimeArtifactError("corpus manifest has no corpus_version")
    return chunks, manifest


def _validate_repairs(
    files: dict[str, Path],
    contract: dict[str, Any],
    chunks: list[dict[str, Any]],
    corpus_manifest: dict[str, Any],
) -> None:
    repair_path = files[contract["runtime_data"]["repair_registry"]]
    try:
        payload = yaml.safe_load(repair_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RuntimeArtifactError("runtime repair registry is not readable YAML") from exc
    if not isinstance(payload, dict):
        raise RuntimeArtifactError("runtime repair registry must be an object")
    allowed_top = {"repair_registry_version", "reviewed_on", "repairs"}
    if not set(payload).issubset(allowed_top) or "repair_registry_version" not in payload:
        raise RuntimeArtifactError("runtime repair registry has unsupported top-level fields")
    if payload.get("repair_registry_version") != corpus_manifest.get("registry_version"):
        raise RuntimeArtifactError("repair registry version differs from the corpus manifest")
    repairs = payload.get("repairs")
    if not isinstance(repairs, list):
        raise RuntimeArtifactError("runtime repair registry repairs must be a list")

    expected_keys = {
        "source_id",
        "page_number",
        "document_sha256",
        "review_status",
        "reason",
        "replacement_text",
    }
    registry_targets: set[tuple[str, int, str]] = set()
    for index, repair in enumerate(repairs, start=1):
        if not isinstance(repair, dict):
            raise RuntimeArtifactError(f"runtime repair {index} must be an object")
        _exact_keys(repair, expected_keys, context=f"runtime repair {index}")
        if repair.get("review_status") != "human_verified":
            raise RuntimeArtifactError(
                f"runtime repair {index} is not approved human_verified provenance"
            )
        source_id = repair.get("source_id")
        page_number = repair.get("page_number")
        document_sha256 = repair.get("document_sha256")
        if not isinstance(source_id, str) or not source_id:
            raise RuntimeArtifactError(f"runtime repair {index} has an invalid source_id")
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            raise RuntimeArtifactError(f"runtime repair {index} has an invalid page_number")
        if not isinstance(document_sha256, str) or not SHA256_PATTERN.fullmatch(
            document_sha256
        ):
            raise RuntimeArtifactError(f"runtime repair {index} has an invalid document_sha256")
        if not isinstance(repair.get("reason"), str) or not repair["reason"].strip():
            raise RuntimeArtifactError(f"runtime repair {index} has no review reason")
        if (
            not isinstance(repair.get("replacement_text"), str)
            or not repair["replacement_text"].strip()
        ):
            raise RuntimeArtifactError(f"runtime repair {index} has no replacement text")
        target = (source_id, page_number, document_sha256)
        if target in registry_targets:
            raise RuntimeArtifactError("runtime repair registry has duplicate targets")
        registry_targets.add(target)

    repaired_targets = {
        (chunk["source_id"], chunk.get("page_number"), chunk["document_sha256"])
        for chunk in chunks
        if chunk["review_provenance"] == "human_verified_repair"
    }
    if any(target[1] is None for target in repaired_targets):
        raise RuntimeArtifactError("repaired corpus chunks must retain page provenance")
    if registry_targets != repaired_targets:
        raise RuntimeArtifactError(
            "runtime repair registry must contain exactly the repairs used by the corpus"
        )
    allowed_provenance = {"native_text", "human_verified_repair"}
    if any(chunk["review_provenance"] not in allowed_provenance for chunk in chunks):
        raise RuntimeArtifactError("corpus contains unapproved review provenance")


def _validate_vector_and_context(
    files: dict[str, Path],
    contract: dict[str, Any],
    candidate: dict[str, Any],
    chunks: list[dict[str, Any]],
    corpus_manifest: dict[str, Any],
) -> None:
    runtime_data = contract["runtime_data"]
    vector_manifest = _read_json(
        files[runtime_data["vector_manifest"]], context="vector manifest"
    )
    _exact_keys(
        vector_manifest,
        {
            "schema_version",
            "corpus_version",
            "corpus_sha256",
            "embedding_model",
            "retrieval_text_strategy",
            "dimensions",
            "chunk_ids",
            "matrix_sha256",
            "created_at",
        },
        context="vector manifest",
    )
    if vector_manifest["schema_version"] != "firelens_vector_index.v1":
        raise RuntimeArtifactError("vector manifest has an unsupported schema")
    for candidate_field, vector_field in (
        ("corpus_version", "corpus_version"),
        ("embedding_model", "embedding_model"),
        ("retrieval_text_strategy", "retrieval_text_strategy"),
    ):
        if candidate[candidate_field] != vector_manifest.get(vector_field):
            raise RuntimeArtifactError(
                f"runtime candidate {candidate_field} differs from the vector manifest"
            )
    if candidate["corpus_version"] != corpus_manifest["corpus_version"]:
        raise RuntimeArtifactError(
            "runtime candidate corpus_version differs from corpus manifest"
        )
    if vector_manifest.get("corpus_sha256") != _sha256_file(files[runtime_data["corpus"]]):
        raise RuntimeArtifactError("vector manifest corpus_sha256 does not match the corpus")
    if vector_manifest.get("matrix_sha256") != _sha256_file(
        files[runtime_data["vector_matrix"]]
    ):
        raise RuntimeArtifactError("vector manifest matrix_sha256 does not match the matrix")
    expected_ids = [chunk["chunk_id"] for chunk in chunks]
    if vector_manifest.get("chunk_ids") != expected_ids:
        raise RuntimeArtifactError("vector manifest chunk IDs differ from the corpus")
    dimensions = vector_manifest["dimensions"]
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise RuntimeArtifactError("vector manifest dimensions must be a positive integer")
    try:
        matrix = np.load(files[runtime_data["vector_matrix"]], allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise RuntimeArtifactError(
            "vector matrix is not a valid non-pickled NPY array"
        ) from exc
    if matrix.ndim != 2 or matrix.shape != (len(chunks), dimensions):
        raise RuntimeArtifactError("vector matrix shape differs from its manifest")
    if not np.issubdtype(matrix.dtype, np.number) or not np.isfinite(matrix).all():
        raise RuntimeArtifactError("vector matrix must contain only finite numeric values")

    conditional = contract["conditional_files"][0]
    context_path = conditional["logical_path"]
    candidate_value = candidate.get(conditional["candidate_field"])
    vector_value = vector_manifest.get(conditional["vector_manifest_field"])
    if candidate_value != vector_value:
        raise RuntimeArtifactError("document-context strategy inputs disagree")
    context_required = candidate_value == conditional["required_value"]
    context_present = context_path in files
    if context_required != context_present:
        disposition = "required" if context_required else "prohibited for this candidate"
        raise RuntimeArtifactError(f"document_context_v2 is {disposition}")
    if not context_required:
        return

    context_records: dict[str, dict[str, Any]] = {}
    try:
        with files[context_path].open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeArtifactError(
                        f"document context line {line_number} is invalid JSON"
                    ) from exc
                if not isinstance(record, dict):
                    raise RuntimeArtifactError(
                        f"document context line {line_number} is not an object"
                    )
                expected_fields = {
                    "schema_version",
                    "document_sha256",
                    "chunk_id",
                    "model_id",
                    "prompt_sha256",
                    "context",
                }
                _exact_keys(
                    record, expected_fields, context=f"document context line {line_number}"
                )
                chunk_id = record.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id or chunk_id in context_records:
                    raise RuntimeArtifactError(
                        "document context has invalid or duplicate chunk IDs"
                    )
                context_records[chunk_id] = record
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeArtifactError("document context is not readable UTF-8 JSONL") from exc
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    if set(context_records) != set(chunks_by_id):
        raise RuntimeArtifactError("document context does not cover the corpus exactly")
    for chunk_id, record in context_records.items():
        if record["schema_version"] != "firelens_document_context.v2":
            raise RuntimeArtifactError("document context has an unsupported schema")
        if record["document_sha256"] != chunks_by_id[chunk_id]["document_sha256"]:
            raise RuntimeArtifactError("document context is stale for its corpus chunk")
        if not isinstance(record["model_id"], str) or not record["model_id"]:
            raise RuntimeArtifactError("document context has no model identity")
        if not isinstance(record["prompt_sha256"], str) or not SHA256_PATTERN.fullmatch(
            record["prompt_sha256"]
        ):
            raise RuntimeArtifactError("document context has an invalid prompt identity")
        if not isinstance(record["context"], str) or not record["context"].strip():
            raise RuntimeArtifactError("document context has empty context text")


def _module_paths(module: str, files: dict[str, Path], source_root: str) -> set[str]:
    module_parts = module.split(".")
    base = PurePosixPath(source_root, *module_parts)
    candidates = {f"{base.as_posix()}.py", (base / "__init__.py").as_posix()}
    resolved = candidates & set(files)
    if not resolved:
        raise RuntimeArtifactError(
            f"runtime Python import is missing from the artifact: {module}"
        )
    result = set(resolved)
    for depth in range(1, len(module_parts) + 1):
        initializer = PurePosixPath(
            source_root, *module_parts[:depth], "__init__.py"
        ).as_posix()
        if initializer in files:
            result.add(initializer)
    return result


def _python_closure(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    python_contract = contract["python"]
    entrypoint = python_contract["entrypoint"]
    source_root = python_contract["source_root"]
    package = python_contract["package"]
    closure = {entrypoint}
    queue = [entrypoint]
    entry_tree: ast.AST | None = None
    while queue:
        logical = queue.pop()
        try:
            tree = ast.parse(files[logical].read_text(encoding="utf-8"), filename=logical)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise RuntimeArtifactError(
                f"runtime Python file cannot be parsed: {logical}"
            ) from exc
        if logical == entrypoint:
            entry_tree = tree
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(
                    alias.name for alias in node.names if alias.name.startswith(package)
                )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise RuntimeArtifactError(
                        f"relative runtime import is not supported by the verifier: {logical}"
                    )
                if node.module and node.module.startswith(package):
                    modules.add(node.module)
                    for alias in node.names:
                        possible = f"{node.module}.{alias.name}"
                        possible_path = PurePosixPath(source_root, *possible.split("."))
                        if (
                            f"{possible_path.as_posix()}.py" in files
                            or (possible_path / "__init__.py").as_posix() in files
                        ):
                            modules.add(possible)
        for module in modules:
            for dependency in _module_paths(module, files, source_root):
                if dependency not in closure:
                    closure.add(dependency)
                    queue.append(dependency)
    if entry_tree is None:
        raise RuntimeArtifactError("runtime Python entrypoint was not inspected")
    app_values: list[ast.expr | None] = []
    for node in ast.walk(entry_tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "app" for target in node.targets
        ):
            app_values.append(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "app"
        ):
            app_values.append(node.value)
    if not app_values:
        raise RuntimeArtifactError("runtime Python entrypoint does not export app")
    if not any(
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "create_app"
        for value in app_values
    ):
        raise RuntimeArtifactError(
            "runtime Python entrypoint app is not constructed by create_app"
        )
    if not any(path.startswith(f"{source_root}/{package}/") for path in closure):
        raise RuntimeArtifactError("runtime Python entrypoint is not connected to the package")
    return closure


def _resource_path(reference: str, *, source: str, frontend_root: str) -> str | None:
    value = reference.strip()
    if not value or value.startswith("#") or value.lower().startswith("data:"):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("//"):
        raise RuntimeArtifactError(f"frontend reference must be local: {reference}")
    path_value = parsed.path
    if not path_value:
        return None
    if "\\" in path_value or "\x00" in path_value:
        raise RuntimeArtifactError(f"frontend reference is not a POSIX path: {reference}")
    if path_value.startswith("/"):
        candidate = PurePosixPath(frontend_root, path_value.lstrip("/"))
    else:
        candidate = PurePosixPath(source).parent / path_value
    if ".." in candidate.parts:
        raise RuntimeArtifactError(f"frontend reference contains path traversal: {reference}")
    normalized = candidate.as_posix()
    _logical_path(normalized, context="frontend reference")
    if normalized != frontend_root and not normalized.startswith(frontend_root + "/"):
        raise RuntimeArtifactError(f"frontend reference escapes its root: {reference}")
    return normalized


def _frontend_closure(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    frontend = contract["frontend"]
    root = frontend["root"]
    index_path = frontend["index"]
    manifest_path = frontend["vite_manifest"]
    frontend_files = {
        logical for logical in files if logical == root or logical.startswith(root + "/")
    }
    allowed_suffixes = tuple(frontend["allowed_suffixes"])
    for logical in frontend_files:
        if not logical.lower().endswith(allowed_suffixes):
            raise RuntimeArtifactError(
                f"frontend artifact has a prohibited file type: {logical}"
            )

    closure = {index_path, manifest_path}
    parser = _HTMLReferences()
    try:
        parser.feed(files[index_path].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeArtifactError("frontend index is not readable UTF-8 HTML") from exc
    for reference in parser.references:
        resolved = _resource_path(reference, source=index_path, frontend_root=root)
        if resolved is not None:
            closure.add(resolved)

    manifest = _read_json(files[manifest_path], context="Vite manifest")
    if not manifest or "index.html" not in manifest:
        raise RuntimeArtifactError("Vite manifest lacks its index.html entry")
    allowed_entry_fields = {
        "file",
        "name",
        "names",
        "src",
        "isEntry",
        "isDynamicEntry",
        "imports",
        "dynamicImports",
        "css",
        "assets",
    }
    manifest_relations: dict[str, list[str]] = {}
    manifest_outputs: dict[str, list[str]] = {}
    for key, entry in manifest.items():
        if not isinstance(key, str) or not key or not isinstance(entry, dict):
            raise RuntimeArtifactError("Vite manifest entries must be named objects")
        extra = set(entry) - allowed_entry_fields
        if extra:
            raise RuntimeArtifactError(
                f"Vite manifest entry {key} has unsupported fields: {extra}"
            )
        file_value = entry.get("file")
        if not isinstance(file_value, str) or not file_value:
            raise RuntimeArtifactError(f"Vite manifest entry {key} has no output file")
        output_groups: list[list[str]] = []
        for field in ("css", "assets"):
            values = entry.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(reference, str) for reference in values
            ):
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} has invalid {field} outputs"
                )
            output_groups.append(values)
        manifest_outputs[key] = [file_value, *output_groups[0], *output_groups[1]]
        relations: list[str] = []
        for relation in ("imports", "dynamicImports"):
            related = entry.get(relation, [])
            if not isinstance(related, list) or any(
                not isinstance(reference, str) for reference in related
            ):
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} has invalid {relation} references"
                )
            missing_keys = sorted(set(related) - set(manifest))
            if missing_keys:
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} references missing entries: {missing_keys}"
                )
            relations.extend(related)
        manifest_relations[key] = relations
    if manifest["index.html"].get("isEntry") is not True:
        raise RuntimeArtifactError("Vite index.html entry is not marked as an entrypoint")

    reachable_entries: set[str] = set()
    manifest_queue = ["index.html"]
    while manifest_queue:
        key = manifest_queue.pop()
        if key in reachable_entries:
            continue
        reachable_entries.add(key)
        manifest_queue.extend(manifest_relations[key])
        for reference in manifest_outputs[key]:
            resolved = _resource_path(
                "/" + reference.lstrip("/"), source=index_path, frontend_root=root
            )
            if resolved is not None:
                closure.add(resolved)
    unreachable_entries = sorted(set(manifest) - reachable_entries)
    if unreachable_entries:
        raise RuntimeArtifactError(
            f"Vite manifest contains unreachable entries: {unreachable_entries}"
        )

    queue = list(closure)
    inspected: set[str] = set()
    while queue:
        logical = queue.pop()
        if logical in inspected or logical not in files:
            continue
        inspected.add(logical)
        suffix = PurePosixPath(logical).suffix.lower()
        references: list[str] = []
        if suffix == ".css":
            try:
                text = files[logical].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeArtifactError(f"frontend CSS is not readable: {logical}") from exc
            for match in CSS_REFERENCE_PATTERN.finditer(text):
                references.append(match.group(2) or match.group(4))
        elif suffix == ".js":
            try:
                text = files[logical].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeArtifactError(f"frontend JS is not readable: {logical}") from exc
            for pattern in JS_REFERENCE_PATTERNS:
                references.extend(match.group(2) for match in pattern.finditer(text))
        for reference in references:
            resolved = _resource_path(reference, source=logical, frontend_root=root)
            if resolved is not None and resolved not in closure:
                closure.add(resolved)
                queue.append(resolved)

    missing = sorted(closure - set(files))
    if missing:
        raise RuntimeArtifactError(f"frontend reference closure is missing files: {missing}")
    orphaned = sorted(frontend_files - closure)
    if orphaned:
        raise RuntimeArtifactError(f"frontend bundle contains unreferenced files: {orphaned}")
    return closure


def _allowed_files(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    required = set(contract["required_files"])
    missing = sorted(required - set(files))
    if missing:
        raise RuntimeArtifactError(f"artifact is missing required files: {missing}")
    conditional_path = contract["conditional_files"][0]["logical_path"]
    allowed = required | _python_closure(files, contract) | _frontend_closure(files, contract)
    if conditional_path in files:
        allowed.add(conditional_path)
    return allowed


def build_runtime_inventory(
    *,
    artifact_root: Path,
    contract_path: Path,
    identity: ArtifactIdentity,
) -> dict[str, Any]:
    """Verify a staged artifact and return its deterministic inventory."""

    _validate_identity(identity)
    contract, contract_sha256 = _load_contract(contract_path)
    files = _collect_files(artifact_root)
    initial_metadata = _file_metadata(files)
    for logical in files:
        reason = _prohibited_reason(logical, contract)
        if reason is not None:
            raise RuntimeArtifactError(f"artifact contains {reason}: {logical}")

    allowed = _allowed_files(files, contract)
    unexpected = sorted(set(files) - allowed)
    if unexpected:
        raise RuntimeArtifactError(f"artifact contains unallowlisted files: {unexpected}")

    embedded_contract_path = "config/runtime_artifact_allowlist.v1.json"
    if _sha256_file(files[embedded_contract_path]) != contract_sha256:
        raise RuntimeArtifactError("artifact embeds a different runtime artifact contract")
    candidate = _load_candidate(files, contract, identity)
    chunks, corpus_manifest = _load_corpus(files, contract)
    _validate_repairs(files, contract, chunks, corpus_manifest)
    _validate_vector_and_context(files, contract, candidate, chunks, corpus_manifest)
    if _file_metadata(files) != initial_metadata:
        raise RuntimeArtifactError("artifact changed while it was being validated")

    platform_root = PurePosixPath(identity.platform_root)
    entries = []
    for logical in sorted(files):
        path = files[logical]
        entries.append(
            {
                "logical_path": logical,
                "platform_path": (platform_root / logical).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if _file_metadata(files) != initial_metadata:
        raise RuntimeArtifactError("artifact changed while it was being inventoried")
    inventory: dict[str, Any] = {
        "schema_version": INVENTORY_SCHEMA,
        "assurance": {
            "scope": "staged_logical_bundle",
            "platform_export_provenance_verified": False,
            "runtime_candidate_identity_observed": False,
        },
        "contract": {
            "schema_version": CONTRACT_SCHEMA,
            "contract_id": contract["contract_id"],
            "logical_path": embedded_contract_path,
            "sha256": contract_sha256,
        },
        "identity": {
            "platform": identity.platform,
            "platform_root": identity.platform_root,
            "artifact_id": identity.artifact_id,
            "candidate_id": identity.candidate_id,
            "release_version": identity.release_version,
            "build_commit": identity.build_commit,
        },
        "runtime_configuration": {
            "logical_path": contract["candidate_configuration"]["logical_path"],
            "sha256": _sha256_file(files[contract["candidate_configuration"]["logical_path"]]),
            "corpus_version": candidate["corpus_version"],
            "embedding_model": candidate["embedding_model"],
            "retrieval_text_strategy": candidate["retrieval_text_strategy"],
        },
        "file_count": len(entries),
        "total_size_bytes": sum(entry["size_bytes"] for entry in entries),
        "files": entries,
    }
    inventory["inventory_sha256"] = _sha256_bytes(_canonical_json(inventory))
    return inventory


def _validate_inventory_document(inventory: dict[str, Any], *, context: str) -> None:
    _exact_keys(
        inventory,
        {
            "schema_version",
            "assurance",
            "contract",
            "identity",
            "runtime_configuration",
            "file_count",
            "total_size_bytes",
            "files",
            "inventory_sha256",
        },
        context=context,
    )
    if inventory["schema_version"] != INVENTORY_SCHEMA:
        raise RuntimeArtifactError(f"{context} has an unsupported schema")
    if inventory["assurance"] != {
        "scope": "staged_logical_bundle",
        "platform_export_provenance_verified": False,
        "runtime_candidate_identity_observed": False,
    }:
        raise RuntimeArtifactError(
            f"{context} cannot claim platform provenance from a staged directory"
        )
    supplied_hash = inventory["inventory_sha256"]
    if not isinstance(supplied_hash, str) or not SHA256_PATTERN.fullmatch(supplied_hash):
        raise RuntimeArtifactError(f"{context} has an invalid inventory_sha256")
    unhashed = dict(inventory)
    del unhashed["inventory_sha256"]
    if supplied_hash != _sha256_bytes(_canonical_json(unhashed)):
        raise RuntimeArtifactError(f"{context} inventory_sha256 does not match its content")

    contract = inventory["contract"]
    if not isinstance(contract, dict):
        raise RuntimeArtifactError(f"{context} contract identity must be an object")
    _exact_keys(
        contract,
        {"schema_version", "contract_id", "logical_path", "sha256"},
        context=f"{context} contract identity",
    )
    if (
        contract["schema_version"] != CONTRACT_SCHEMA
        or not isinstance(contract["sha256"], str)
        or not SHA256_PATTERN.fullmatch(contract["sha256"])
    ):
        raise RuntimeArtifactError(f"{context} contract identity is invalid")

    identity = inventory["identity"]
    if not isinstance(identity, dict):
        raise RuntimeArtifactError(f"{context} artifact identity must be an object")
    _exact_keys(
        identity,
        {
            "platform",
            "platform_root",
            "artifact_id",
            "candidate_id",
            "release_version",
            "build_commit",
        },
        context=f"{context} artifact identity",
    )
    _validate_identity(ArtifactIdentity(**identity))

    runtime_configuration = inventory["runtime_configuration"]
    if not isinstance(runtime_configuration, dict):
        raise RuntimeArtifactError(f"{context} runtime configuration must be an object")
    _exact_keys(
        runtime_configuration,
        {
            "logical_path",
            "sha256",
            "corpus_version",
            "embedding_model",
            "retrieval_text_strategy",
        },
        context=f"{context} runtime configuration",
    )
    _logical_path(runtime_configuration["logical_path"], context="runtime configuration path")
    if not isinstance(runtime_configuration["sha256"], str) or not SHA256_PATTERN.fullmatch(
        runtime_configuration["sha256"]
    ):
        raise RuntimeArtifactError(f"{context} runtime configuration hash is invalid")
    for field in ("corpus_version", "embedding_model"):
        value = runtime_configuration[field]
        if not isinstance(value, str):
            raise RuntimeArtifactError(f"{context} runtime configuration {field} is invalid")
        _nonempty_identity(value, field=f"{context} runtime configuration {field}")
    if runtime_configuration["retrieval_text_strategy"] not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise RuntimeArtifactError(
            f"{context} runtime configuration retrieval_text_strategy is invalid"
        )

    entries = inventory["files"]
    if not isinstance(entries, list) or not entries:
        raise RuntimeArtifactError(f"{context} files must be a non-empty list")
    expected_platform_root = PurePosixPath(identity["platform_root"])
    logical_paths: list[str] = []
    total_size = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeArtifactError(f"{context} file {index} must be an object")
        _exact_keys(
            entry,
            {"logical_path", "platform_path", "size_bytes", "sha256"},
            context=f"{context} file {index}",
        )
        logical = _logical_path(entry["logical_path"], context=f"{context} file path")
        expected_platform = (expected_platform_root / logical).as_posix()
        if entry["platform_path"] != expected_platform:
            raise RuntimeArtifactError(
                f"{context} file {logical} has a non-canonical platform path"
            )
        size = entry["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RuntimeArtifactError(f"{context} file {logical} has an invalid size")
        if not isinstance(entry["sha256"], str) or not SHA256_PATTERN.fullmatch(
            entry["sha256"]
        ):
            raise RuntimeArtifactError(f"{context} file {logical} has an invalid SHA-256")
        logical_paths.append(logical)
        total_size += size
    if logical_paths != sorted(logical_paths) or len(logical_paths) != len(set(logical_paths)):
        raise RuntimeArtifactError(f"{context} file paths must be unique and sorted")
    if inventory["file_count"] != len(entries) or inventory["total_size_bytes"] != total_size:
        raise RuntimeArtifactError(f"{context} file totals do not match its entries")


def compare_runtime_inventories(
    vercel_inventory: dict[str, Any], docker_inventory: dict[str, Any]
) -> dict[str, Any]:
    """Compare logical identities while retaining platform-specific paths and IDs."""

    _validate_inventory_document(vercel_inventory, context="Vercel inventory")
    _validate_inventory_document(docker_inventory, context="Docker inventory")
    if vercel_inventory["identity"]["platform"] != "vercel":
        raise RuntimeArtifactError("first comparison inventory must be Vercel")
    if docker_inventory["identity"]["platform"] != "docker":
        raise RuntimeArtifactError("second comparison inventory must be Docker")

    mismatches: list[dict[str, Any]] = []
    for field in ("contract", "runtime_configuration"):
        if vercel_inventory[field] != docker_inventory[field]:
            mismatches.append({"kind": f"{field}_mismatch"})
    for field in ("candidate_id", "release_version", "build_commit"):
        left = vercel_inventory["identity"][field]
        right = docker_inventory["identity"][field]
        if left != right:
            mismatches.append(
                {
                    "kind": "candidate_identity_mismatch",
                    "field": field,
                    "vercel": left,
                    "docker": right,
                }
            )

    def logical_rows(inventory: dict[str, Any]) -> dict[str, tuple[int, str]]:
        return {
            entry["logical_path"]: (entry["size_bytes"], entry["sha256"])
            for entry in inventory["files"]
        }

    vercel_rows = logical_rows(vercel_inventory)
    docker_rows = logical_rows(docker_inventory)
    for path in sorted(set(vercel_rows) | set(docker_rows)):
        if path not in vercel_rows:
            mismatches.append({"kind": "missing_on_vercel", "logical_path": path})
        elif path not in docker_rows:
            mismatches.append({"kind": "missing_on_docker", "logical_path": path})
        elif vercel_rows[path] != docker_rows[path]:
            mismatches.append(
                {
                    "kind": "logical_identity_mismatch",
                    "logical_path": path,
                    "vercel": {
                        "size_bytes": vercel_rows[path][0],
                        "sha256": vercel_rows[path][1],
                    },
                    "docker": {
                        "size_bytes": docker_rows[path][0],
                        "sha256": docker_rows[path][1],
                    },
                }
            )

    staged_logical_parity = not mismatches
    qualification_blockers = [
        "platform_export_provenance_unverified",
        "runtime_candidate_identity_not_observed",
    ]
    comparison: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA,
        "qualified": staged_logical_parity,
        "release_qualified": False,
        "staged_logical_parity": staged_logical_parity,
        "qualification_blockers": qualification_blockers,
        "candidate_id": vercel_inventory["identity"]["candidate_id"],
        "release_version": vercel_inventory["identity"]["release_version"],
        "build_commit": vercel_inventory["identity"]["build_commit"],
        "contract_sha256": vercel_inventory["contract"]["sha256"],
        "vercel_artifact_id": vercel_inventory["identity"]["artifact_id"],
        "docker_artifact_id": docker_inventory["identity"]["artifact_id"],
        "vercel_inventory_sha256": vercel_inventory["inventory_sha256"],
        "docker_inventory_sha256": docker_inventory["inventory_sha256"],
        "logical_file_count": len(set(vercel_rows) | set(docker_rows)),
        "mismatches": mismatches,
    }
    comparison["comparison_sha256"] = _sha256_bytes(_canonical_json(comparison))
    return comparison


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(rendered)
        return
    _assert_not_symlink(path, context="output")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory", help="verify and inventory one artifact")
    inventory.add_argument("--artifact-root", type=Path, required=True)
    inventory.add_argument("--contract", type=Path, required=True)
    inventory.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), required=True)
    inventory.add_argument("--platform-root", required=True)
    inventory.add_argument("--artifact-id", required=True)
    inventory.add_argument("--candidate-id", required=True)
    inventory.add_argument("--release-version", required=True)
    inventory.add_argument("--build-commit", required=True)
    inventory.add_argument("--output", type=Path)

    compare = subparsers.add_parser("compare", help="compare Vercel and Docker inventories")
    compare.add_argument("--vercel-inventory", type=Path, required=True)
    compare.add_argument("--docker-inventory", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            identity = ArtifactIdentity(
                platform=args.platform,
                platform_root=args.platform_root,
                artifact_id=args.artifact_id,
                candidate_id=args.candidate_id,
                release_version=args.release_version,
                build_commit=args.build_commit,
            )
            payload = build_runtime_inventory(
                artifact_root=args.artifact_root,
                contract_path=args.contract,
                identity=identity,
            )
            _write_json(args.output, payload)
            return 0
        vercel = _read_json(args.vercel_inventory, context="Vercel inventory")
        docker = _read_json(args.docker_inventory, context="Docker inventory")
        comparison = compare_runtime_inventories(vercel, docker)
        _write_json(args.output, comparison)
        return 0 if comparison["qualified"] else 2
    except RuntimeArtifactError as exc:
        print(f"runtime artifact verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
