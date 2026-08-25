"""Runtime-candidate identity and active-artifact binding validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from firelens.runtime_artifact_common import (
    SHA256_PATTERN,
    SUPPORTED_RETRIEVAL_STRATEGIES,
    ArtifactIdentity,
    RuntimeArtifactError,
    assert_candidate_has_no_secrets,
    exact_keys,
    nonempty_identity,
    read_json,
    require_candidate_privacy,
    require_model_id,
    sha256_file,
)


def load_candidate(
    files: dict[str, Path], contract: dict[str, Any], identity: ArtifactIdentity
) -> dict[str, Any]:
    """Load and validate the candidate's release and runtime identity."""

    candidate_contract = contract["candidate_configuration"]
    path = candidate_contract["logical_path"]
    candidate = read_json(files[path], context="runtime candidate configuration")
    if candidate.get("schema_version") != candidate_contract["schema_version"]:
        raise RuntimeArtifactError("runtime candidate configuration has an unsupported schema")
    expected_fields = set(candidate_contract["required_fields"])
    exact_keys(candidate, expected_fields, context="runtime candidate configuration")
    for field, expected in (
        ("candidate_id", identity.candidate_id),
        ("release_version", identity.release_version),
        ("build_commit", identity.build_commit),
    ):
        if candidate.get(field) != expected:
            raise RuntimeArtifactError(f"runtime candidate {field} differs from build identity")
    corpus_version = candidate.get("corpus_version")
    if not isinstance(corpus_version, str):
        raise RuntimeArtifactError("runtime candidate corpus_version must be a string")
    nonempty_identity(corpus_version, field="runtime candidate corpus_version")
    runtime_data = contract["runtime_data"]
    artifact_fields = {
        "corpus_sha256": runtime_data["corpus"],
        "corpus_manifest_sha256": runtime_data["corpus_manifest"],
        "vector_matrix_sha256": runtime_data["vector_matrix"],
        "vector_manifest_sha256": runtime_data["vector_manifest"],
    }
    for field in artifact_fields:
        digest = candidate.get(field)
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise RuntimeArtifactError(f"runtime candidate {field} is not lowercase SHA-256")
    for field in ("embedding_model", "rerank_model", "generation_model"):
        require_model_id(candidate.get(field), field=f"runtime candidate {field}")
    if candidate.get("retrieval_text_strategy") not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise RuntimeArtifactError("runtime candidate retrieval_text_strategy is unsupported")
    require_candidate_privacy(candidate, context="runtime candidate")
    assert_candidate_has_no_secrets(candidate)
    return candidate


def validate_candidate_artifact_hashes(
    files: dict[str, Path],
    contract: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    """Bind candidate-declared artifact hashes to the staged active bytes."""

    runtime_data = contract["runtime_data"]
    artifact_fields = {
        "corpus_sha256": runtime_data["corpus"],
        "corpus_manifest_sha256": runtime_data["corpus_manifest"],
        "vector_matrix_sha256": runtime_data["vector_matrix"],
        "vector_manifest_sha256": runtime_data["vector_manifest"],
    }
    for field, logical in artifact_fields.items():
        if candidate[field] != sha256_file(files[logical]):
            raise RuntimeArtifactError(
                f"runtime candidate {field} differs from the active artifact"
            )
