"""Shared fail-closed primitives for runtime artifact verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_SCHEMA = "firelens.runtime_artifact_allowlist.v1"
CANDIDATE_SCHEMA = "firelens.runtime_candidate.v2"
INVENTORY_SCHEMA = "firelens.runtime_artifact_inventory.v2"
COMPARISON_SCHEMA = "firelens.runtime_artifact_comparison.v1"
CANDIDATE_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "release_version",
        "build_commit",
        "corpus_version",
        "embedding_model",
        "retrieval_text_strategy",
        "rerank_model",
        "generation_model",
        "require_zdr",
    }
)
RUNTIME_CONFIGURATION_FIELDS = frozenset(
    {
        "logical_path",
        "sha256",
        "corpus_version",
        "embedding_model",
        "retrieval_text_strategy",
        "rerank_model",
        "generation_model",
        "require_zdr",
    }
)
REQUIRE_ZDR_VALUES = frozenset({"true", "false"})
CANDIDATE_RELATIVE_PATH = "config/runtime_candidate.v1.json"
SECRET_FIELD_TOKENS = ("api_key", "token", "secret", "password", "authorization", "bearer")
SECRET_VALUE_MARKERS = ("sk-", "or-v1-")
MODEL_ID_MAX_CHARS = 200
MODEL_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{0,63}(?:/[a-z0-9][a-z0-9._-]{0,127}){1,3}"
    r"(?::[a-z0-9][a-z0-9._-]{0,63})?$"
)
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


class HTMLReferences(HTMLParser):
    """Collect local asset references from a built HTML document."""

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


def exact_keys(payload: dict[str, Any], expected: set[str], *, context: str) -> None:
    """Reject both omitted and unexpected fields in a frozen document."""

    observed = set(payload)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise RuntimeArtifactError(
            f"{context} keys differ from the contract (missing={missing}, extra={extra})"
        )


def canonical_json(payload: Any) -> bytes:
    """Render stable UTF-8 JSON for cryptographic commitments."""

    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one stable, single-link regular file without following symlinks."""

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


def file_metadata(files: dict[str, Path]) -> dict[str, tuple[int, int, int, int]]:
    """Capture identities used to reject mutation during verification."""

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


def read_json(path: Path, *, context: str) -> dict[str, Any]:
    """Read a UTF-8 JSON object with a stable domain error."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeArtifactError(f"{context} is not readable JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeArtifactError(f"{context} must be a JSON object")
    return payload


def logical_path(value: Any, *, context: str) -> str:
    """Validate a canonical relative POSIX artifact path."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeArtifactError(f"{context} must be a canonical POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or value in {".", ".."}:
        raise RuntimeArtifactError(f"{context} must be a canonical POSIX relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeArtifactError(f"{context} contains path traversal")
    return value


def platform_root(value: Any) -> str:
    """Validate a non-root canonical absolute POSIX deployment path."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeArtifactError("platform_root must be a canonical absolute POSIX path")
    path = PurePosixPath(value)
    if not path.is_absolute() or value != path.as_posix() or ".." in path.parts:
        raise RuntimeArtifactError("platform_root must be a canonical absolute POSIX path")
    if value == "/":
        raise RuntimeArtifactError("platform_root cannot be the filesystem root")
    return value


def nonempty_identity(value: str, *, field: str) -> str:
    """Validate one printable, whitespace-stable identity value."""

    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeArtifactError(f"{field} must be a non-empty printable string")
    return value


def validate_identity(identity: ArtifactIdentity) -> None:
    """Validate the complete externally supplied artifact identity."""

    if not isinstance(identity.platform, str) or identity.platform not in SUPPORTED_PLATFORMS:
        raise RuntimeArtifactError("platform must be docker or vercel")
    platform_root(identity.platform_root)
    nonempty_identity(identity.artifact_id, field="artifact_id")
    nonempty_identity(identity.candidate_id, field="candidate_id")
    nonempty_identity(identity.release_version, field="release_version")
    if not isinstance(identity.build_commit, str) or not GIT_COMMIT_PATTERN.fullmatch(
        identity.build_commit
    ):
        raise RuntimeArtifactError("build_commit must be a lowercase 40- or 64-hex commit")


def require_zdr_policy(value: Any, *, context: str) -> str:
    """Accept only the canonical string policy values bound into artifacts."""

    if not isinstance(value, str) or value not in REQUIRE_ZDR_VALUES:
        raise RuntimeArtifactError(f"{context} require_zdr must be 'true' or 'false'")
    return value


def secret_shaped_text(value: str) -> bool:
    """True when a string contains a credential-shaped token anywhere."""

    lowered = value.lower()
    return any(marker in lowered for marker in SECRET_VALUE_MARKERS)


def require_model_id(value: Any, *, field: str) -> str:
    """Accept only a bounded OpenRouter-style model id with no credential material."""

    identity = nonempty_identity(value, field=field)
    if secret_shaped_text(identity):
        raise RuntimeArtifactError("runtime candidate cannot contain secrets")
    if len(identity) > MODEL_ID_MAX_CHARS or MODEL_ID_PATTERN.fullmatch(identity) is None:
        raise RuntimeArtifactError(f"{field} is not a valid model id")
    return identity


def assert_candidate_has_no_secrets(payload: dict[str, Any]) -> None:
    """Refuse API keys or other credentials in a candidate document."""

    for key, value in payload.items():
        lowered = key.lower()
        if any(token in lowered for token in SECRET_FIELD_TOKENS):
            raise RuntimeArtifactError("runtime candidate cannot contain secrets")
        if isinstance(value, str) and secret_shaped_text(value):
            raise RuntimeArtifactError("runtime candidate cannot contain secrets")


def assert_not_symlink(path: Path, *, context: str) -> None:
    """Reject symlinks at a security-sensitive artifact boundary."""

    try:
        if path.is_symlink():
            raise RuntimeArtifactError(f"{context} cannot be a symlink: {path}")
    except OSError as exc:
        raise RuntimeArtifactError(f"cannot inspect {context}: {path}") from exc
