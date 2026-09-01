"""Fail-closed runtime artifact inventory and cross-platform comparison.
This module verifies a staged deployment root. It deliberately does not inspect a
repository checkout as if it were a deployment artifact: the staging step is the
security boundary that must include only runtime inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from firelens.document_context import CONTEXT_MODEL_ID, PROMPT_VERSION, prompt_sha256
from firelens.runtime_artifact_candidate import (
    load_candidate as _load_candidate,
)
from firelens.runtime_artifact_candidate import (
    validate_candidate_artifact_hashes as _validate_candidate_artifact_hashes,
)
from firelens.runtime_artifact_closure import allowed_files as _allowed_files
from firelens.runtime_artifact_common import (
    CANDIDATE_REQUIRED_FIELDS,
    CANDIDATE_SCHEMA,
    CHUNK_KEYS,
    CONTRACT_SCHEMA,
    INVENTORY_SCHEMA,
    SHA256_PATTERN,
    SUPPORTED_PLATFORMS,
)
from firelens.runtime_artifact_common import (
    ArtifactIdentity as ArtifactIdentity,
)
from firelens.runtime_artifact_common import (
    RuntimeArtifactError as RuntimeArtifactError,
)
from firelens.runtime_artifact_common import (
    assert_not_symlink as _assert_not_symlink,
)
from firelens.runtime_artifact_common import (
    canonical_json as _canonical_json,
)
from firelens.runtime_artifact_common import (
    exact_keys as _exact_keys,
)
from firelens.runtime_artifact_common import (
    file_metadata as _file_metadata,
)
from firelens.runtime_artifact_common import (
    logical_path as _logical_path,
)
from firelens.runtime_artifact_common import (
    nonempty_identity as _nonempty_identity,
)
from firelens.runtime_artifact_common import (
    read_json as _read_json,
)
from firelens.runtime_artifact_common import (
    sha256_bytes as _sha256_bytes,
)
from firelens.runtime_artifact_common import (
    sha256_file as _sha256_file,
)
from firelens.runtime_artifact_common import (
    strict_json_loads as _strict_json_loads,
)
from firelens.runtime_artifact_common import (
    strict_yaml_load as _strict_yaml_load,
)
from firelens.runtime_artifact_common import (
    validate_identity as _validate_identity,
)
from firelens.runtime_artifact_comparison import (
    compare_runtime_inventories as compare_runtime_inventories,
)
from firelens.runtime_artifact_contract import (
    validate_prohibited_contract as _validate_prohibited_contract,
)
from firelens.runtime_artifact_files import (
    collect_files as _collect_files,
)
from firelens.runtime_artifact_files import (
    prohibited_reason as _prohibited_reason,
)


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
    candidate = _validate_candidate_contract(contract["candidate_configuration"])
    required = _validate_required_files(contract["required_files"])
    conditional = _validate_conditional_contract(contract["conditional_files"])
    python = _validate_python_contract(contract["python"])
    frontend = _validate_frontend_contract(contract["frontend"])
    runtime_data = _validate_runtime_data(contract["runtime_data"])
    _validate_contract_relationships(
        candidate, required, conditional, python, frontend, runtime_data
    )
    _validate_prohibited_contract(contract["prohibited"])
    return contract, _sha256_file(path)


def _validate_candidate_contract(value: Any) -> dict[str, Any]:
    candidate = value
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
    if set(required_candidate_fields) != CANDIDATE_REQUIRED_FIELDS:
        raise RuntimeArtifactError(
            "candidate required_fields must bind the complete runtime and release identity"
        )
    return candidate


def _validate_required_files(value: Any) -> list[str]:
    required_files = value
    if not isinstance(required_files, list) or not required_files:
        raise RuntimeArtifactError("required_files must be a non-empty list")
    normalized_required = [
        _logical_path(value, context="required file") for value in required_files
    ]
    if len(normalized_required) != len(set(normalized_required)):
        raise RuntimeArtifactError("required_files contains duplicates")
    return normalized_required


def _validate_conditional_contract(value: Any) -> dict[str, Any]:
    conditional_files = value
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
    return conditional


def _validate_python_contract(value: Any) -> dict[str, Any]:
    python = value
    if not isinstance(python, dict):
        raise RuntimeArtifactError("python contract must be an object")
    _exact_keys(python, {"entrypoint", "source_root", "package"}, context="python contract")
    _logical_path(python["entrypoint"], context="Python entrypoint")
    _logical_path(python["source_root"], context="Python source root")
    if python["package"] != "firelens":
        raise RuntimeArtifactError("Python package must remain firelens")
    return python


def _validate_frontend_contract(value: Any) -> dict[str, Any]:
    frontend = value
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
    return frontend


def _validate_runtime_data(value: Any) -> dict[str, Any]:
    runtime_data = value
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
    return runtime_data


def _validate_contract_relationships(
    candidate: dict[str, Any],
    required: list[str],
    conditional: dict[str, Any],
    python: dict[str, Any],
    frontend: dict[str, Any],
    runtime_data: dict[str, Any],
) -> None:
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
    if not mandatory_required.issubset(set(required)):
        raise RuntimeArtifactError("required_files omits a mandatory runtime identity or input")
    if runtime_data["document_context"] in required:
        raise RuntimeArtifactError(
            "document_context must remain conditional, not unconditionally required"
        )


def _load_corpus(
    files: dict[str, Path], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime_data = contract["runtime_data"]
    corpus_path = files[runtime_data["corpus"]]
    try:
        with corpus_path.open(encoding="utf-8") as stream:
            chunks = [
                _validated_corpus_chunk(line, number)
                for number, line in enumerate(stream, start=1)
                if line.strip()
            ]
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


def _validated_corpus_chunk(line: str, line_number: int) -> dict[str, Any]:
    chunk = _strict_json_loads(line, context=f"corpus line {line_number}")
    if not isinstance(chunk, dict):
        raise RuntimeArtifactError(f"corpus line {line_number} is not an object")
    context = f"corpus line {line_number}"
    _exact_keys(chunk, CHUNK_KEYS, context=context)
    if chunk.get("schema_version") != "chunk_record.v2":
        raise RuntimeArtifactError(f"{context} has an unsupported schema")
    for field in ("chunk_id", "source_id", "document_sha256", "review_provenance"):
        if not isinstance(chunk.get(field), str) or not chunk[field]:
            raise RuntimeArtifactError(f"{context} is missing {field}")
    if not SHA256_PATTERN.fullmatch(chunk["document_sha256"]):
        raise RuntimeArtifactError(f"{context} has an invalid document_sha256")
    page = chunk.get("page_number")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        raise RuntimeArtifactError(f"{context} has an invalid page_number")
    index = chunk.get("chunk_index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise RuntimeArtifactError(f"{context} has an invalid chunk_index")
    if not isinstance(chunk.get("text"), str) or not chunk["text"].strip():
        raise RuntimeArtifactError(f"{context} has empty text")
    if chunk.get("char_count") != len(chunk["text"]):
        raise RuntimeArtifactError(f"{context} has an inconsistent char_count")
    return chunk


def _validate_repairs(
    files: dict[str, Path],
    contract: dict[str, Any],
    chunks: list[dict[str, Any]],
    corpus_manifest: dict[str, Any],
) -> None:
    repair_path = files[contract["runtime_data"]["repair_registry"]]
    try:
        payload = _strict_yaml_load(
            repair_path.read_text(encoding="utf-8"),
            context="runtime repair registry",
        )
    except (OSError, UnicodeDecodeError) as exc:
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
    approved_targets: set[tuple[str, int, str]] = set()
    quarantined_targets: set[tuple[str, int, str, str, str]] = set()
    for index, repair in enumerate(repairs, start=1):
        target, review_status, reason = _validated_repair_target(repair, index, expected_keys)
        if target in approved_targets or any(
            target == pending[:3] for pending in quarantined_targets
        ):
            raise RuntimeArtifactError("runtime repair registry has duplicate targets")
        if review_status == "human_verified":
            approved_targets.add(target)
        else:
            quarantined_targets.add((*target, review_status, reason))

    repaired_targets = {
        (chunk["source_id"], chunk.get("page_number"), chunk["document_sha256"])
        for chunk in chunks
        if chunk["review_provenance"] == "human_verified_repair"
    }
    if any(target[1] is None for target in repaired_targets):
        raise RuntimeArtifactError("repaired corpus chunks must retain page provenance")
    if any(target[:3] in repaired_targets for target in quarantined_targets):
        raise RuntimeArtifactError(
            "not approved repair provenance appears in the admitted corpus"
        )
    if approved_targets != repaired_targets:
        raise RuntimeArtifactError(
            "runtime repair registry must contain exactly the repairs used by the corpus"
        )
    manifest_quarantine = corpus_manifest.get("quarantined_pages", [])
    if not isinstance(manifest_quarantine, list):
        raise RuntimeArtifactError("corpus manifest quarantined_pages is malformed")
    manifest_targets: set[tuple[str, int, str, str, str]] = set()
    for index, page in enumerate(manifest_quarantine, start=1):
        context = f"corpus manifest quarantined page {index}"
        if not isinstance(page, dict):
            raise RuntimeArtifactError(f"{context} is not an object")
        _exact_keys(
            page,
            {"source_id", "page_number", "document_sha256", "review_status", "reason"},
            context=context,
        )
        source_id, page_number, digest = _validated_repair_target_fields(page, context)
        status = page["review_status"]
        reason = page["reason"]
        if status not in {"pending_owner_review", "automated_visual_reviewed"}:
            raise RuntimeArtifactError(f"{context} has an unsupported quarantine status")
        candidate = (source_id, page_number, digest, status, reason)
        if candidate in manifest_targets:
            raise RuntimeArtifactError("corpus manifest has duplicate quarantined pages")
        manifest_targets.add(candidate)
    if manifest_targets != quarantined_targets:
        raise RuntimeArtifactError(
            "not approved repair provenance is missing an exact quarantined-page record"
        )
    allowed_provenance = {"native_text", "human_verified_repair"}
    if any(chunk["review_provenance"] not in allowed_provenance for chunk in chunks):
        raise RuntimeArtifactError("corpus contains unapproved review provenance")


def _validated_repair_target(
    repair: Any, index: int, expected_keys: set[str]
) -> tuple[tuple[str, int, str], str, str]:
    context = f"runtime repair {index}"
    if not isinstance(repair, dict):
        raise RuntimeArtifactError(f"{context} must be an object")
    _exact_keys(repair, expected_keys, context=context)
    source_id, page, digest = _validated_repair_target_fields(repair, context)
    status = repair.get("review_status")
    if status not in {"human_verified", "pending_owner_review", "automated_visual_reviewed"}:
        raise RuntimeArtifactError(f"{context} has an unsupported review status")
    reason = repair["reason"]
    replacement = repair.get("replacement_text")
    if not isinstance(replacement, str) or not replacement.strip():
        raise RuntimeArtifactError(f"{context} has no replacement text")
    return (source_id, page, digest), status, reason


def _validated_repair_target_fields(
    repair: dict[str, Any], context: str
) -> tuple[str, int, str]:
    source_id, page, digest = (
        repair.get("source_id"),
        repair.get("page_number"),
        repair.get("document_sha256"),
    )
    if not isinstance(source_id, str) or not source_id:
        raise RuntimeArtifactError(f"{context} has an invalid source_id")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise RuntimeArtifactError(f"{context} has an invalid page_number")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise RuntimeArtifactError(f"{context} has an invalid document_sha256")
    if not isinstance(repair.get("reason"), str) or not repair["reason"].strip():
        raise RuntimeArtifactError(f"{context} has no review reason")
    return source_id, page, digest


def _validate_vector_and_context(
    files: dict[str, Path],
    contract: dict[str, Any],
    candidate: dict[str, Any],
    chunks: list[dict[str, Any]],
    corpus_manifest: dict[str, Any],
) -> None:
    runtime_data = contract["runtime_data"]
    vector_manifest = _validated_vector_manifest(
        files, runtime_data, candidate, chunks, corpus_manifest
    )
    _validate_vector_matrix(files, runtime_data, vector_manifest, len(chunks))
    conditional = contract["conditional_files"][0]
    context_path = conditional["logical_path"]
    context_required = _context_requirement(
        conditional, candidate, vector_manifest, context_path in files
    )
    if not context_required:
        return
    records = _load_context_records(files[context_path])
    _validate_context_records(records, chunks)


def _validated_vector_manifest(
    files: dict[str, Path],
    runtime_data: dict[str, Any],
    candidate: dict[str, Any],
    chunks: list[dict[str, Any]],
    corpus_manifest: dict[str, Any],
) -> dict[str, Any]:
    manifest = _read_json(files[runtime_data["vector_manifest"]], context="vector manifest")
    _exact_keys(
        manifest,
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
    if manifest["schema_version"] != "firelens_vector_index.v1":
        raise RuntimeArtifactError("vector manifest has an unsupported schema")
    for candidate_field, vector_field in (
        ("corpus_version", "corpus_version"),
        ("embedding_model", "embedding_model"),
        ("retrieval_text_strategy", "retrieval_text_strategy"),
    ):
        if candidate[candidate_field] != manifest.get(vector_field):
            raise RuntimeArtifactError(
                f"runtime candidate {candidate_field} differs from the vector manifest"
            )
    if candidate["corpus_version"] != corpus_manifest["corpus_version"]:
        raise RuntimeArtifactError(
            "runtime candidate corpus_version differs from corpus manifest"
        )
    if manifest.get("corpus_sha256") != _sha256_file(files[runtime_data["corpus"]]):
        raise RuntimeArtifactError("vector manifest corpus_sha256 does not match the corpus")
    if manifest.get("matrix_sha256") != _sha256_file(files[runtime_data["vector_matrix"]]):
        raise RuntimeArtifactError("vector manifest matrix_sha256 does not match the matrix")
    expected_ids = [chunk["chunk_id"] for chunk in chunks]
    if manifest.get("chunk_ids") != expected_ids:
        raise RuntimeArtifactError("vector manifest chunk IDs differ from the corpus")
    return manifest


def _validate_vector_matrix(
    files: dict[str, Path],
    runtime_data: dict[str, Any],
    manifest: dict[str, Any],
    chunk_count: int,
) -> None:
    dimensions = manifest["dimensions"]
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise RuntimeArtifactError("vector manifest dimensions must be a positive integer")
    try:
        matrix = np.load(files[runtime_data["vector_matrix"]], allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise RuntimeArtifactError(
            "vector matrix is not a valid non-pickled NPY array"
        ) from exc
    if matrix.ndim != 2 or matrix.shape != (chunk_count, dimensions):
        raise RuntimeArtifactError("vector matrix shape differs from its manifest")
    if not np.issubdtype(matrix.dtype, np.number) or not np.isfinite(matrix).all():
        raise RuntimeArtifactError("vector matrix must contain only finite numeric values")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
        raise RuntimeArtifactError("vector matrix rows must be unit normalized")


def _context_requirement(
    conditional: dict[str, Any],
    candidate: dict[str, Any],
    manifest: dict[str, Any],
    present: bool,
) -> bool:
    candidate_value = candidate.get(conditional["candidate_field"])
    vector_value = manifest.get(conditional["vector_manifest_field"])
    if candidate_value != vector_value:
        raise RuntimeArtifactError("document-context strategy inputs disagree")
    context_required = candidate_value == conditional["required_value"]
    if context_required != present:
        disposition = "required" if context_required else "prohibited for this candidate"
        raise RuntimeArtifactError(f"document_context_v2 is {disposition}")
    return bool(context_required)


def _load_context_records(path: Path) -> dict[str, dict[str, Any]]:
    context_records: dict[str, dict[str, Any]] = {}
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                record = _strict_json_loads(
                    line,
                    context=f"document context line {line_number}",
                )
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
    return context_records


def _validate_context_records(
    context_records: dict[str, dict[str, Any]], chunks: list[dict[str, Any]]
) -> None:
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    if set(context_records) != set(chunks_by_id):
        raise RuntimeArtifactError("document context does not cover the corpus exactly")
    for chunk_id, record in context_records.items():
        if record["schema_version"] != PROMPT_VERSION:
            raise RuntimeArtifactError("document context has an unsupported schema")
        if record["document_sha256"] != chunks_by_id[chunk_id]["document_sha256"]:
            raise RuntimeArtifactError("document context is stale for its corpus chunk")
        if record["model_id"] != CONTEXT_MODEL_ID:
            raise RuntimeArtifactError("document context model identity is not current")
        if record["prompt_sha256"] != prompt_sha256():
            raise RuntimeArtifactError("document context prompt identity is not current")
        if not isinstance(record["context"], str) or not record["context"].strip():
            raise RuntimeArtifactError("document context has empty context text")


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
    _validate_candidate_artifact_hashes(files, contract, candidate)
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
            "corpus_sha256": candidate["corpus_sha256"],
            "corpus_manifest_sha256": candidate["corpus_manifest_sha256"],
            "vector_matrix_sha256": candidate["vector_matrix_sha256"],
            "vector_manifest_sha256": candidate["vector_manifest_sha256"],
            "embedding_model": candidate["embedding_model"],
            "retrieval_text_strategy": candidate["retrieval_text_strategy"],
            "rerank_model": candidate["rerank_model"],
            "generation_model": candidate["generation_model"],
            "data_collection": candidate["data_collection"],
            "allow_fallbacks": candidate["allow_fallbacks"],
            "require_parameters": candidate["require_parameters"],
            "embedding_zdr": candidate["embedding_zdr"],
            "reranking_zdr": candidate["reranking_zdr"],
            "generation_zdr": candidate["generation_zdr"],
        },
        "file_count": len(entries),
        "total_size_bytes": sum(entry["size_bytes"] for entry in entries),
        "files": entries,
    }
    inventory["inventory_sha256"] = _sha256_bytes(_canonical_json(inventory))
    return inventory


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
