"""Validation and logical comparison of staged runtime artifact inventories."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from firelens.runtime_artifact_common import (
    COMPARISON_SCHEMA,
    CONTRACT_SCHEMA,
    INVENTORY_SCHEMA,
    SHA256_PATTERN,
    SUPPORTED_RETRIEVAL_STRATEGIES,
    ArtifactIdentity,
    RuntimeArtifactError,
    canonical_json,
    exact_keys,
    logical_path,
    nonempty_identity,
    sha256_bytes,
    validate_identity,
)


def _validate_inventory_document(inventory: dict[str, Any], *, context: str) -> None:
    _validate_inventory_header(inventory, context=context)
    _validate_contract_identity(inventory["contract"], context=context)
    identity = _validate_artifact_identity(inventory["identity"], context=context)
    _validate_runtime_configuration(inventory["runtime_configuration"], context=context)
    _validate_inventory_files(inventory, identity, context=context)


def _validate_inventory_header(inventory: dict[str, Any], *, context: str) -> None:
    exact_keys(
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
    if supplied_hash != sha256_bytes(canonical_json(unhashed)):
        raise RuntimeArtifactError(f"{context} inventory_sha256 does not match its content")


def _validate_contract_identity(contract: Any, *, context: str) -> None:
    if not isinstance(contract, dict):
        raise RuntimeArtifactError(f"{context} contract identity must be an object")
    exact_keys(
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


def _validate_artifact_identity(identity: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(identity, dict):
        raise RuntimeArtifactError(f"{context} artifact identity must be an object")
    exact_keys(
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
    validate_identity(ArtifactIdentity(**identity))
    return identity


def _validate_runtime_configuration(runtime_configuration: Any, *, context: str) -> None:
    if not isinstance(runtime_configuration, dict):
        raise RuntimeArtifactError(f"{context} runtime configuration must be an object")
    exact_keys(
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
    logical_path(runtime_configuration["logical_path"], context="runtime configuration path")
    if not isinstance(runtime_configuration["sha256"], str) or not SHA256_PATTERN.fullmatch(
        runtime_configuration["sha256"]
    ):
        raise RuntimeArtifactError(f"{context} runtime configuration hash is invalid")
    for field in ("corpus_version", "embedding_model"):
        value = runtime_configuration[field]
        if not isinstance(value, str):
            raise RuntimeArtifactError(f"{context} runtime configuration {field} is invalid")
        nonempty_identity(value, field=f"{context} runtime configuration {field}")
    if runtime_configuration["retrieval_text_strategy"] not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise RuntimeArtifactError(
            f"{context} runtime configuration retrieval_text_strategy is invalid"
        )


def _validate_inventory_files(
    inventory: dict[str, Any], identity: dict[str, Any], *, context: str
) -> None:
    entries = inventory["files"]
    if not isinstance(entries, list) or not entries:
        raise RuntimeArtifactError(f"{context} files must be a non-empty list")
    expected_platform_root = PurePosixPath(identity["platform_root"])
    logical_paths: list[str] = []
    total_size = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeArtifactError(f"{context} file {index} must be an object")
        exact_keys(
            entry,
            {"logical_path", "platform_path", "size_bytes", "sha256"},
            context=f"{context} file {index}",
        )
        logical = logical_path(entry["logical_path"], context=f"{context} file path")
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
    comparison: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA,
        "qualified": staged_logical_parity,
        "release_qualified": False,
        "staged_logical_parity": staged_logical_parity,
        "qualification_blockers": [
            "platform_export_provenance_unverified",
            "runtime_candidate_identity_not_observed",
        ],
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
    comparison["comparison_sha256"] = sha256_bytes(canonical_json(comparison))
    return comparison
