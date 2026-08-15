"""Runtime artifact inventory, portability, and metric evidence validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from firelens.evaluation.common import ROOT, file_sha256
from firelens.evaluation.spec_models import BenchmarkSpec
from firelens.runtime_artifact import (
    ArtifactIdentity,
    RuntimeArtifactError,
    build_runtime_inventory,
    compare_runtime_inventories,
)
from firelens.runtime_artifact_common import CANDIDATE_REQUIRED_FIELDS, CANDIDATE_SCHEMA
from firelens.storage import atomic_text_writer

RUNTIME_ARTIFACT_CONTRACT = ROOT / "config/runtime_artifact_allowlist.v1.json"


def _artifact(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": file_sha256(path),
    }


def _runtime_candidate_id(benchmark_id: str, commit: str) -> str:
    return f"{benchmark_id.replace('_', '-')}:{commit}"


def _resolved_artifact_root(path: Path | None, *, platform_name: str) -> Path:
    if path is None:
        raise ValueError(f"after capture requires the {platform_name} artifact root")
    if path.is_symlink():
        raise ValueError(f"{platform_name} artifact root cannot be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{platform_name} artifact root is not readable: {path}") from error
    if not resolved.is_dir():
        raise ValueError(f"{platform_name} artifact root must be a directory")
    if resolved == Path(resolved.anchor) or resolved == ROOT.resolve():
        raise ValueError(
            f"{platform_name} artifact root must be an isolated extracted build, "
            "not a filesystem or repository root"
        )
    return resolved


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _inventory_file_entry(inventory: dict[str, Any], logical_path: str) -> dict[str, Any]:
    files = inventory.get("files")
    if not isinstance(files, list):
        raise ValueError("runtime artifact inventory files must be a list")
    matches = [
        entry
        for entry in files
        if isinstance(entry, dict) and entry.get("logical_path") == logical_path
    ]
    if len(matches) != 1:
        raise ValueError(
            f"runtime artifact inventory must contain exactly one {logical_path} entry"
        )
    return matches[0]


def _runtime_candidate_evidence(
    artifact_root: Path, inventory: dict[str, Any]
) -> dict[str, Any]:
    logical_path = "config/runtime_candidate.v1.json"
    candidate_path = artifact_root / logical_path
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ValueError("runtime candidate configuration is missing or is a symlink")
    raw = candidate_path.read_bytes()
    entry = _inventory_file_entry(inventory, logical_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != entry["sha256"] or len(raw) != entry["size_bytes"]:
        raise ValueError("runtime candidate configuration differs from its built inventory")
    try:
        text = raw.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("runtime candidate configuration is not UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise ValueError("runtime candidate configuration must be a JSON object")
    return {
        "logical_path": logical_path,
        "raw_json": text,
        "sha256": digest,
        "size_bytes": len(raw),
    }


def _build_runtime_artifact_pair(
    *,
    spec: BenchmarkSpec,
    commit: str,
    release_version: str,
    vercel_artifact_root: Path | None,
    vercel_artifact_id: str | None,
    vercel_platform_root: str | None,
    docker_artifact_root: Path | None,
    docker_artifact_id: str | None,
    docker_platform_root: str | None,
    output_dir: Path,
) -> dict[str, Any]:
    vercel_root = _resolved_artifact_root(vercel_artifact_root, platform_name="Vercel")
    docker_root = _resolved_artifact_root(docker_artifact_root, platform_name="Docker")
    resolved_output = output_dir.resolve()
    if _paths_overlap(vercel_root, docker_root):
        raise ValueError("Vercel and Docker artifact roots must be distinct and non-nested")
    if _paths_overlap(vercel_root, resolved_output) or _paths_overlap(
        docker_root, resolved_output
    ):
        raise ValueError(
            "runtime artifact roots must be outside the benchmark output directory"
        )
    if not isinstance(vercel_artifact_id, str) or not vercel_artifact_id.strip():
        raise ValueError("after capture requires an exact Vercel artifact ID")
    if not isinstance(docker_artifact_id, str) or not docker_artifact_id.strip():
        raise ValueError("after capture requires an exact Docker artifact ID")
    if vercel_artifact_id == docker_artifact_id:
        raise ValueError("Vercel and Docker artifact IDs must be distinct")
    if not isinstance(vercel_platform_root, str) or not vercel_platform_root:
        raise ValueError("after capture requires the exact Vercel platform root")
    if not isinstance(docker_platform_root, str) or not docker_platform_root:
        raise ValueError("after capture requires the exact Docker platform root")

    contract_path = RUNTIME_ARTIFACT_CONTRACT
    candidate_id = _runtime_candidate_id(spec.benchmark_id, commit)

    def inventory(
        platform_name: str,
        artifact_root: Path,
        platform_root: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        try:
            return build_runtime_inventory(
                artifact_root=artifact_root,
                contract_path=contract_path,
                identity=ArtifactIdentity(
                    platform=platform_name,
                    platform_root=platform_root,
                    artifact_id=artifact_id,
                    candidate_id=candidate_id,
                    release_version=release_version,
                    build_commit=commit,
                ),
            )
        except RuntimeArtifactError as error:
            raise ValueError(
                f"{platform_name} runtime artifact is ineligible: {error}"
            ) from error

    vercel = inventory("vercel", vercel_root, vercel_platform_root, vercel_artifact_id)
    docker = inventory("docker", docker_root, docker_platform_root, docker_artifact_id)
    try:
        comparison = compare_runtime_inventories(vercel, docker)
    except RuntimeArtifactError as error:
        raise ValueError(f"runtime artifact comparison is invalid: {error}") from error
    return {
        "status": "complete",
        "capture_method": "capture_owned_build_runtime_inventory.v1",
        "contract": {
            "path": "config/runtime_artifact_allowlist.v1.json",
            "sha256": file_sha256(contract_path),
        },
        "inventories": {"vercel": vercel, "docker": docker},
        "candidate_configurations": {
            "vercel": _runtime_candidate_evidence(vercel_root, vercel),
            "docker": _runtime_candidate_evidence(docker_root, docker),
        },
        "comparison": comparison,
    }


def _finalize_runtime_artifact_pair(
    pre_command: dict[str, Any], post_command: dict[str, Any]
) -> dict[str, Any]:
    if post_command != pre_command:
        raise ValueError("Vercel or Docker runtime artifact changed during benchmark capture")
    inventory_hashes = {
        platform_name: inventory["inventory_sha256"]
        for platform_name, inventory in post_command["inventories"].items()
    }
    return {
        **post_command,
        "capture_sequence": {
            "pre_command_inventory_sha256": inventory_hashes,
            "post_command_inventory_sha256": inventory_hashes,
            "unchanged": True,
        },
    }


def _runtime_prohibited_reason(logical_path: str, contract: dict[str, Any]) -> str | None:
    rules = contract["prohibited"]
    lowered = logical_path.lower()
    parts = Path(lowered).parts
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


def _runtime_candidate_document(evidence: Any, *, platform_name: str) -> dict[str, Any]:
    expected_evidence_keys = {"logical_path", "raw_json", "sha256", "size_bytes"}
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_keys:
        raise ValueError(f"{platform_name} runtime candidate evidence is malformed")
    if evidence["logical_path"] != "config/runtime_candidate.v1.json":
        raise ValueError(f"{platform_name} runtime candidate path is invalid")
    raw_json = evidence["raw_json"]
    if not isinstance(raw_json, str):
        raise ValueError(f"{platform_name} runtime candidate raw_json must be text")
    raw = raw_json.encode("utf-8")
    if (
        evidence["size_bytes"] != len(raw)
        or evidence["sha256"] != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError(f"{platform_name} runtime candidate raw bytes are not authentic")
    try:
        document = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"{platform_name} runtime candidate is invalid JSON") from error
    expected_document_keys = set(CANDIDATE_REQUIRED_FIELDS)
    if not isinstance(document, dict) or set(document) != expected_document_keys:
        raise ValueError(f"{platform_name} runtime candidate fields are not exact")
    if document["schema_version"] != CANDIDATE_SCHEMA:
        raise ValueError(f"{platform_name} runtime candidate schema is unsupported")
    return document


def _rendered_json_sha256(payload: Any) -> str:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _runtime_artifact_metric_values(
    snapshot: dict[str, Any],
) -> dict[str, bool | int | None]:
    section = snapshot.get("runtime_artifact")
    metric_keys = {
        "runtime_artifact_qualified",
        "runtime_artifact_missing_required_count",
        "runtime_artifact_prohibited_count",
        "runtime_artifact_identity_match",
        "runtime_artifact_candidate_commit_match",
    }
    if section == {"status": "required_after_only"}:
        return {key: None for key in metric_keys}
    expected_section_keys = {
        "status",
        "capture_method",
        "contract",
        "inventories",
        "candidate_configurations",
        "comparison",
        "capture_sequence",
    }
    if not isinstance(section, dict) or set(section) != expected_section_keys:
        raise ValueError("runtime artifact snapshot evidence is missing or malformed")
    if (
        section["status"] != "complete"
        or section["capture_method"] != "capture_owned_build_runtime_inventory.v1"
    ):
        raise ValueError("runtime artifact snapshot did not use capture-owned inventorying")
    inventories = section["inventories"]
    if not isinstance(inventories, dict) or set(inventories) != {"vercel", "docker"}:
        raise ValueError("runtime artifact snapshot must retain both inventories")
    try:
        recomputed_comparison = compare_runtime_inventories(
            inventories["vercel"], inventories["docker"]
        )
    except RuntimeArtifactError as error:
        raise ValueError(f"runtime artifact inventories are invalid: {error}") from error
    if section["comparison"] != recomputed_comparison:
        raise ValueError(
            "runtime artifact comparison differs from recomputed inventory evidence"
        )

    contract_path = RUNTIME_ARTIFACT_CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_sha256 = file_sha256(contract_path)
    expected_contract = {
        "path": "config/runtime_artifact_allowlist.v1.json",
        "sha256": contract_sha256,
    }
    if section["contract"] != expected_contract:
        raise ValueError("runtime artifact evidence uses the wrong allowlist contract")

    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("runtime artifact evidence has no snapshot identity")
    commit = identity.get("commit")
    benchmark_id = snapshot.get("benchmark_id")
    if not isinstance(commit, str) or not isinstance(benchmark_id, str):
        raise ValueError("runtime artifact evidence has incomplete candidate identity")
    expected_candidate = {
        "candidate_id": identity.get("candidate_id"),
        "release_version": identity.get("release_version"),
        "build_commit": commit,
        "corpus_version": identity.get("corpus_version"),
        "embedding_model": (identity.get("configuration") or {}).get("embedding_model"),
        "retrieval_text_strategy": (identity.get("configuration") or {}).get(
            "retrieval_text_strategy"
        ),
        "rerank_model": (identity.get("configuration") or {}).get("rerank_model"),
        "generation_model": (identity.get("configuration") or {}).get("generation_model"),
        "require_zdr": (identity.get("configuration") or {}).get("require_zdr"),
    }
    if expected_candidate["candidate_id"] != _runtime_candidate_id(benchmark_id, commit):
        raise ValueError("snapshot candidate ID is not canonical for its benchmark and commit")
    if any(not isinstance(value, str) or not value for value in expected_candidate.values()):
        raise ValueError("runtime artifact expected candidate identity is incomplete")

    candidate_evidence = section["candidate_configurations"]
    if not isinstance(candidate_evidence, dict) or set(candidate_evidence) != {
        "vercel",
        "docker",
    }:
        raise ValueError("runtime artifact candidate evidence must cover both platforms")
    candidate_documents: dict[str, dict[str, Any]] = {}
    for platform_name in ("vercel", "docker"):
        inventory = inventories[platform_name]
        document = _runtime_candidate_document(
            candidate_evidence[platform_name], platform_name=platform_name
        )
        candidate_documents[platform_name] = document
        entry = _inventory_file_entry(inventory, "config/runtime_candidate.v1.json")
        if (
            entry["sha256"] != candidate_evidence[platform_name]["sha256"]
            or entry["size_bytes"] != candidate_evidence[platform_name]["size_bytes"]
            or inventory["runtime_configuration"]["sha256"] != entry["sha256"]
        ):
            raise ValueError(
                f"{platform_name} runtime candidate bytes differ from its inventory"
            )
        contract_entry = _inventory_file_entry(
            inventory, "config/runtime_artifact_allowlist.v1.json"
        )
        if (
            contract_entry["sha256"] != contract_sha256
            or contract_entry["size_bytes"] != contract_path.stat().st_size
        ):
            raise ValueError(
                f"{platform_name} embedded runtime contract differs from the frozen contract"
            )

    expected_document = {
        "schema_version": CANDIDATE_SCHEMA,
        **expected_candidate,
    }
    candidate_commit_match = all(
        inventory["identity"]["build_commit"] == commit
        and candidate_documents[platform_name]["build_commit"] == commit
        for platform_name, inventory in inventories.items()
    )
    contract_identity = (identity.get("identity_input_sha256") or {}).get(
        "config/runtime_artifact_allowlist.v1.json"
    )
    identity_match = (
        recomputed_comparison["staged_logical_parity"] is True
        and contract_identity == contract_sha256
        and all(
            inventory["contract"]["sha256"] == contract_sha256
            and candidate_documents[platform_name] == expected_document
            and inventory["identity"]["candidate_id"] == expected_candidate["candidate_id"]
            and inventory["identity"]["release_version"]
            == expected_candidate["release_version"]
            and inventory["runtime_configuration"]["corpus_version"]
            == expected_candidate["corpus_version"]
            and inventory["runtime_configuration"]["embedding_model"]
            == expected_candidate["embedding_model"]
            and inventory["runtime_configuration"]["retrieval_text_strategy"]
            == expected_candidate["retrieval_text_strategy"]
            and inventory["runtime_configuration"]["rerank_model"]
            == expected_candidate["rerank_model"]
            and inventory["runtime_configuration"]["generation_model"]
            == expected_candidate["generation_model"]
            and inventory["runtime_configuration"]["require_zdr"]
            == expected_candidate["require_zdr"]
            for platform_name, inventory in inventories.items()
        )
    )

    required = set(contract["required_files"])
    conditional = contract["conditional_files"][0]
    if expected_candidate["retrieval_text_strategy"] == conditional["required_value"]:
        required.add(conditional["logical_path"])
    missing_required_count = 0
    prohibited_count = 0
    for inventory in inventories.values():
        logical_paths = {entry["logical_path"] for entry in inventory["files"]}
        missing_required_count += len(required - logical_paths)
        prohibited_count += sum(
            _runtime_prohibited_reason(logical_path, contract) is not None
            for logical_path in logical_paths
        )

    capture_sequence = section["capture_sequence"]
    expected_inventory_hashes = {
        platform_name: inventory["inventory_sha256"]
        for platform_name, inventory in inventories.items()
    }
    expected_sequence = {
        "pre_command_inventory_sha256": expected_inventory_hashes,
        "post_command_inventory_sha256": expected_inventory_hashes,
        "unchanged": True,
    }
    if capture_sequence != expected_sequence:
        raise ValueError("runtime artifacts changed during benchmark capture")

    retained_artifacts = snapshot.get("artifacts")
    if not isinstance(retained_artifacts, dict):
        raise ValueError("runtime artifact snapshot has no retained artifact commitments")
    expected_artifact_hashes = {
        "runtime_artifact_vercel_inventory": _rendered_json_sha256(inventories["vercel"]),
        "runtime_artifact_docker_inventory": _rendered_json_sha256(inventories["docker"]),
        "runtime_artifact_comparison": _rendered_json_sha256(recomputed_comparison),
        "runtime_artifact_vercel_candidate": candidate_evidence["vercel"]["sha256"],
        "runtime_artifact_docker_candidate": candidate_evidence["docker"]["sha256"],
    }
    for name, expected_sha256 in expected_artifact_hashes.items():
        commitment = retained_artifacts.get(name)
        if (
            not isinstance(commitment, dict)
            or set(commitment) != {"path", "sha256"}
            or not isinstance(commitment["path"], str)
            or not commitment["path"]
            or commitment["sha256"] != expected_sha256
        ):
            raise ValueError(
                f"runtime artifact retained commitment is missing or mismatched: {name}"
            )
    qualified = (
        identity_match
        and candidate_commit_match
        and missing_required_count == 0
        and prohibited_count == 0
    )
    return {
        "runtime_artifact_qualified": qualified,
        "runtime_artifact_missing_required_count": missing_required_count,
        "runtime_artifact_prohibited_count": prohibited_count,
        "runtime_artifact_identity_match": identity_match,
        "runtime_artifact_candidate_commit_match": candidate_commit_match,
    }


def _write_runtime_artifact_evidence(
    output_dir: Path, section: dict[str, Any]
) -> dict[str, Path]:
    runtime_dir = output_dir / "runtime_artifacts"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "vercel_inventory": section["inventories"]["vercel"],
        "docker_inventory": section["inventories"]["docker"],
        "comparison": section["comparison"],
    }
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = runtime_dir / f"{name}.json"
        with atomic_text_writer(path) as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        paths[name] = path
    for platform_name in ("vercel", "docker"):
        path = runtime_dir / f"{platform_name}_runtime_candidate.v1.json"
        with atomic_text_writer(path) as stream:
            stream.write(section["candidate_configurations"][platform_name]["raw_json"])
        paths[f"{platform_name}_runtime_candidate"] = path
    return paths
