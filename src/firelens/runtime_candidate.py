"""Build, validate, and bind the staged runtime candidate identity."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from firelens.config import DEFAULT_RELEASE_VERSION, FireLensConfig
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY, OpenRouterPrivacyPolicy
from firelens.runtime_artifact_common import (
    CANDIDATE_RELATIVE_PATH,
    CANDIDATE_REQUIRED_FIELDS,
    CANDIDATE_SCHEMA,
    SUPPORTED_RETRIEVAL_STRATEGIES,
    RuntimeArtifactError,
    assert_candidate_has_no_secrets,
    assert_not_symlink,
    nonempty_identity,
    read_json,
    require_candidate_privacy,
    require_model_id,
)

COMMIT = re.compile(r"^[0-9a-f]{40}$")
BENCHMARK_ID = re.compile(r"^[a-z][a-z0-9_]{1,127}$")
CANDIDATE_ID_PREFIX = re.compile(r"^[a-z][a-z0-9-]{1,127}$")
LOCAL_UNQUALIFIED = "this environment is not a production-qualified artifact"
DEFAULT_BENCHMARK_ID = "firelens_v1_6_rc2"


def _object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def require_candidate_identity(payload: dict[str, Any]) -> None:
    """Require a Git SHA and a candidate ID whose suffix is that SHA."""

    commit = payload.get("build_commit")
    candidate_id = payload.get("candidate_id")
    if not isinstance(commit, str) or COMMIT.fullmatch(commit) is None:
        raise RuntimeArtifactError(
            "runtime candidate build_commit must be a full lowercase Git SHA"
        )
    if not isinstance(candidate_id, str):
        raise RuntimeArtifactError("runtime candidate candidate_id must be a string")
    prefix, separator, suffix = candidate_id.rpartition(":")
    if not separator or suffix != commit or CANDIDATE_ID_PREFIX.fullmatch(prefix) is None:
        raise RuntimeArtifactError(
            "runtime candidate candidate_id must bind a valid prefix to build_commit"
        )


def _model_id(value: str, *, field: str) -> str:
    try:
        return require_model_id(value, field=field)
    except RuntimeArtifactError as exc:
        raise ValueError(str(exc)) from exc


def build_runtime_candidate(
    *,
    commit: str,
    benchmark_id: str,
    release_version: str | None = None,
    corpus_manifest_path: Path,
    vector_manifest_path: Path,
    rerank_model: str | None = None,
    generation_model: str | None = None,
    privacy: OpenRouterPrivacyPolicy | None = None,
) -> dict[str, str]:
    """Build a strict candidate document from shipped manifests and model policy."""

    if COMMIT.fullmatch(commit) is None:
        raise ValueError("runtime candidate commit must be a full lowercase Git SHA")
    if BENCHMARK_ID.fullmatch(benchmark_id) is None:
        raise ValueError("runtime candidate benchmark ID is invalid")
    version = release_version if release_version is not None else DEFAULT_RELEASE_VERSION
    if not version or version != version.strip():
        raise ValueError("runtime candidate release version is invalid")
    corpus = _object(corpus_manifest_path, "corpus manifest")
    vector = _object(vector_manifest_path, "vector manifest")
    corpus_version = corpus.get("corpus_version")
    embedding_model = vector.get("embedding_model")
    retrieval_text_strategy = vector.get("retrieval_text_strategy")
    if not isinstance(corpus_version, str) or not corpus_version:
        raise ValueError("corpus manifest has no corpus version")
    if vector.get("corpus_version") != corpus_version:
        raise ValueError("vector and corpus manifests use different corpus versions")
    if not isinstance(embedding_model, str) or not embedding_model:
        raise ValueError("vector manifest has no embedding model")
    embedding = _model_id(embedding_model, field="embedding_model")
    if retrieval_text_strategy not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise ValueError("vector manifest retrieval strategy is unsupported")
    rerank = _model_id(
        rerank_model or str(FireLensConfig.model_fields["rerank_model"].default),
        field="rerank_model",
    )
    generation = _model_id(
        generation_model or str(FireLensConfig.model_fields["generation_model"].default),
        field="generation_model",
    )
    policy = privacy if privacy is not None else APPROVED_PRODUCTION_PRIVACY
    document = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": f"{benchmark_id.replace('_', '-')}:{commit}",
        "release_version": version,
        "build_commit": commit,
        "corpus_version": corpus_version,
        "embedding_model": embedding,
        "retrieval_text_strategy": str(retrieval_text_strategy),
        "rerank_model": rerank,
        "generation_model": generation,
        **policy.candidate_fields(),
    }
    try:
        assert_candidate_has_no_secrets(document)
    except RuntimeArtifactError as exc:
        raise ValueError(str(exc)) from exc
    return document


def write_runtime_candidate(output: Path, document: dict[str, str]) -> None:
    """Atomically replace only the generated candidate file, never a symlink."""

    try:
        assert_candidate_has_no_secrets(document)
    except RuntimeArtifactError as exc:
        raise ValueError(str(exc)) from exc
    if document.get("schema_version") != CANDIDATE_SCHEMA:
        raise ValueError("runtime candidate schema is unsupported")
    if set(document) != CANDIDATE_REQUIRED_FIELDS:
        raise ValueError("runtime candidate fields are not exact")
    try:
        assert_candidate_has_no_secrets(document)
        require_candidate_privacy(document, context="runtime candidate")
        require_candidate_identity(document)
    except RuntimeArtifactError as exc:
        raise ValueError(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("runtime candidate output cannot be a symlink")
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def load_runtime_candidate_document(path: Path) -> dict[str, str]:
    """Load and validate one bound candidate document."""

    assert_not_symlink(path, context="runtime candidate")
    payload = read_json(path, context="runtime candidate")
    if payload.get("schema_version") != CANDIDATE_SCHEMA:
        raise RuntimeArtifactError("runtime candidate schema is unsupported")
    if set(payload) != CANDIDATE_REQUIRED_FIELDS:
        raise RuntimeArtifactError("runtime candidate fields are not exact")
    assert_candidate_has_no_secrets(payload)
    require_candidate_privacy(payload, context="runtime candidate")
    if payload.get("retrieval_text_strategy") not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise RuntimeArtifactError("runtime candidate retrieval_text_strategy is unsupported")
    for field in ("candidate_id", "release_version", "build_commit", "corpus_version"):
        value = payload.get(field)
        if not isinstance(value, str):
            raise RuntimeArtifactError(f"runtime candidate {field} must be a string")
        nonempty_identity(value, field=f"runtime candidate {field}")
    require_candidate_identity(payload)
    for field in ("embedding_model", "rerank_model", "generation_model"):
        require_model_id(payload.get(field), field=f"runtime candidate {field}")
    return {key: str(payload[key]) for key in sorted(CANDIDATE_REQUIRED_FIELDS)}


def candidate_mismatches(
    document: dict[str, str],
    config: FireLensConfig,
    *,
    corpus_version: str | None = None,
) -> list[str]:
    """Return identity fields that differ between the candidate and this process."""

    expected = {
        "embedding_model": config.embedding_model,
        "rerank_model": config.rerank_model,
        "generation_model": config.generation_model,
        "retrieval_text_strategy": config.retrieval_text_strategy.value,
        **config.privacy.candidate_fields(),
        "release_version": config.release_version,
    }
    mismatched = [field for field, value in expected.items() if document.get(field) != value]
    if config.build_commit is not None:
        if document.get("build_commit") != config.build_commit:
            mismatched.append("build_commit")
    elif config.deployment_environment in {"preview", "production"}:
        mismatched.append("build_commit")
    if corpus_version is not None and document.get("corpus_version") != corpus_version:
        mismatched.append("corpus_version")
    return mismatched


def apply_runtime_candidate_binding(
    config: FireLensConfig,
    *,
    corpus_version: str | None = None,
) -> list[str]:
    """Bind env/config to the staged candidate.

    Preview and production fail closed on a missing or mismatched candidate.
    Local development remains usable and records that it is not qualified.
    """

    path = config.project_root / CANDIDATE_RELATIVE_PATH
    deployed = config.deployment_environment in {"preview", "production"}
    if not path.is_file():
        message = f"bound runtime candidate is absent; {LOCAL_UNQUALIFIED}"
        if deployed:
            raise RuntimeError("deployed runtime is missing the bound candidate document")
        return [message]
    try:
        document = load_runtime_candidate_document(path)
    except (OSError, RuntimeArtifactError) as exc:
        if deployed:
            raise RuntimeError("deployed runtime candidate is invalid") from exc
        return [f"bound runtime candidate is invalid; {LOCAL_UNQUALIFIED}"]
    mismatched = candidate_mismatches(document, config, corpus_version=corpus_version)
    if not mismatched:
        return []
    detail = ", ".join(mismatched)
    if deployed:
        raise RuntimeError(f"runtime environment differs from the bound candidate ({detail})")
    return [
        f"bound runtime candidate does not match this process ({detail}); {LOCAL_UNQUALIFIED}"
    ]
