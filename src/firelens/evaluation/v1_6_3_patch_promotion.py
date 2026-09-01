"""V1.6.3 patch-promotion binding. This is not a deployment or release-GO claim."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from firelens.evaluation.candidate_evidence_common import file_record
from firelens.evaluation.common import file_sha256
from firelens.evaluation.release_promotion import (
    bind_functional_parent,
    normalize_release_version,
    public_contract_surface,
    unique_promotion_commit,
    version_surfaces,
)
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE

SCHEMA_VERSION = "firelens.v1_6_3_patch_promotion.v1"
MANIFEST_RELATIVE = "config/firelens.v1_6_3_patch_promotion.v1.json"
FROM_VERSION = "1.6.2"
TO_VERSION = "1.6.3"
FUNCTIONAL_PARENT_COMMIT = "d2900401ca240dd97b898b9b2b8e35f78b7de199"
FUNCTIONAL_PARENT_TREE = "e28beec1d74a64bf98259a6d42dbc0a471ad8b54"
FROZEN_STANDARD_RELEASE_TARGET = "1.6.0-rc.1"
FROZEN_STANDARD_SHA256 = "55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
STATIC_QUALIFICATION_REASON = (
    "Static tracked manifest deliberately does not self-bind a mutable Git HEAD; "
    "exact qualification is bound by external current candidate evidence after execution."
)

HISTORICAL_PROMOTION_PATHS: tuple[str, ...] = (
    "src/firelens/evaluation/v1_6_2_patch_promotion.py",
    "config/firelens.v1_6_2_patch_promotion.v1.json",
)
HISTORICAL_PROMOTION_SHA256: tuple[str, ...] = (
    "31da48ee560ba4544f139ee17163e5354c6cedd8596bb3155e411945b6e0bcaf",
    "c579bb38a1f97e52a65a69d40ffc262eec1154e5b52b3df29d1440a40c36ae25",
)

GOVERNED_MATERIAL_PATHS: tuple[str, ...] = (
    "data/processed/firelens_static_corpus.manifest.json",
    "data/processed/firelens_static_corpus.chunks.jsonl",
    "data/index/firelens_vectors.manifest.json",
    "data/index/firelens_vectors.npy",
    "data/typed_claims/high_risk_v1.yaml",
    "data/typed_claims/candidates_pending_v1.yaml",
    "data/typed_claims/candidate_preparation_seed_v2.yaml",
    "data/typed_claims/prepared_candidates_v2.yaml",
    "data/typed_claims/source_repair_scope_template_v1.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_PREPARATION_MANIFEST.json",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_1_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_3_DECISIONS.yaml",
    "docs/reports/V1_6_SOURCE_REPAIR_SCOPE_DECISIONS.yaml",
    "data/evaluation/hard_probe.v1.yaml",
    "data/evaluation/hard_probe.v1.manifest.json",
    "data/evaluation/hard_probe_rc2_expectations.v1.yaml",
    "data/evaluation/hard_probe_rc2_expectations.v1.manifest.json",
    "data/evaluation/hard_probe_rc2_1_expectations.v1.yaml",
    "data/evaluation/hard_probe_rc2_1_expectations.v1.manifest.json",
    "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml",
    "data/evaluation/hard_probe_rc2_2_expectations.v1.manifest.json",
    "data/evaluation/v1_6_user_end_questions_50.json",
    "data/evaluation/v1_6_user_end_questions_50.manifest.json",
    "docs/reports/V1_6_STRUCTURED_PUBLICATION_HARD_PROBE.json",
    "data/capabilities/guided_questions.v1.json",
    "data/capabilities/guided_questions.v1.manifest.json",
    "data/capabilities/firelens.guidance_capabilities.v1.json",
    "src/firelens/guidance_capabilities.py",
    "src/firelens/source_requirements.py",
    "data/evaluation/source_aware_conversation.v1.yaml",
    "data/evaluation/source_aware_conversation.v1.manifest.json",
    "src/firelens/evaluation/source_aware_conversation.py",
    "scripts/run_source_aware_conversation.py",
)

ALLOWED_PROMOTION_PATHS: tuple[str, ...] = (
    MANIFEST_RELATIVE,
    "src/firelens/evaluation/v1_6_3_patch_promotion.py",
    "src/firelens/evaluation/candidate_evidence_documents.py",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "src/firelens/config.py",
    "Dockerfile",
    "render.yaml",
    "docs/openapi.v1.json",
    "apps/web/src/shared/api/api-schema.d.ts",
    ".github/workflows/candidate.yml",
    "README.md",
    "CHANGELOG.md",
    "docs/ARCHITECTURE_V1_6.md",
    "docs/releases/V1_6_RUNBOOK.md",
    "tests/test_v1_6_3_patch_promotion.py",
    "tests/test_v1_6_2_patch_promotion.py",
    "tests/test_candidate_evidence.py",
    "tests/test_documentation_consistency.py",
    "tests/test_runtime_candidate_build.py",
    "tests/test_deploy_vercel.py",
)

_MANIFEST_FIELDS = {
    "schema_version",
    "from_version",
    "to_version",
    "functional_parent_commit",
    "functional_parent_tree",
    "frozen_standard_path",
    "frozen_standard_sha256",
    "historical_promotion_materials",
    "governed_materials",
    "allowed_paths",
    "public_claim_fields",
    "claim_support_fields",
    "proof_card_fields",
    "evidence_status_values",
    "response_mode_values",
    "publication_kind_values",
    "support_state_values",
    "qualification",
}


def load_patch_promotion_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V1.6.3 patch-promotion manifest is missing or invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _MANIFEST_FIELDS:
        raise ValueError("V1.6.3 patch-promotion manifest fields are invalid")
    return payload


def patch_promotion_manifest_document(root: Path) -> dict[str, Any]:
    """Return the static V1.6.3 snapshot without rebinding an eventual HEAD."""

    return load_patch_promotion_manifest(root)


def _version_surfaces(root: Path) -> dict[str, str]:
    surfaces = version_surfaces(root)
    try:
        lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("web package-lock version surfaces cannot be read") from exc
    packages = lock.get("packages") if isinstance(lock, dict) else None
    root_package = packages.get("") if isinstance(packages, dict) else None
    root_version = root_package.get("version") if isinstance(root_package, dict) else None
    if not isinstance(root_version, str):
        raise ValueError("web package-lock root package version is missing")
    return {**surfaces, "web_lock_root_package": root_version}


def _validate_records(
    records: Any, *, paths: tuple[str, ...], label: str, root: Path
) -> list[dict[str, object]]:
    if not isinstance(records, list) or [
        record.get("name") for record in records if isinstance(record, dict)
    ] != list(paths):
        raise ValueError(f"V1.6.3 {label} snapshot is invalid")
    if any(
        not isinstance(record, dict)
        or set(record) != {"name", "sha256", "size_bytes"}
        or not isinstance(record["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        or not isinstance(record["size_bytes"], int)
        or record["size_bytes"] < 0
        for record in records
    ):
        raise ValueError(f"V1.6.3 {label} snapshot is invalid")
    expected = [file_record(root, path) for path in paths]
    if records != expected:
        raise ValueError(f"V1.6.3 {label} material changed")
    return records


def validate_patch_manifest(root: Path, *, release_version: str) -> dict[str, Any]:
    """Validate V1.6.3's static inputs without claiming exact qualification."""

    manifest = load_patch_promotion_manifest(root)
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["from_version"] != FROM_VERSION
        or manifest["to_version"] != TO_VERSION
        or manifest["functional_parent_commit"] != FUNCTIONAL_PARENT_COMMIT
        or manifest["functional_parent_tree"] != FUNCTIONAL_PARENT_TREE
        or manifest["frozen_standard_path"] != STANDARD_RELATIVE
        or manifest["frozen_standard_sha256"] != FROZEN_STANDARD_SHA256
    ):
        raise ValueError("V1.6.3 patch-promotion manifest constants changed")
    historical = _validate_records(
        manifest["historical_promotion_materials"],
        paths=HISTORICAL_PROMOTION_PATHS,
        label="historical promotion",
        root=root,
    )
    if tuple(record["sha256"] for record in historical) != HISTORICAL_PROMOTION_SHA256:
        raise ValueError("historical V1.6.2 promotion material changed")
    governed = _validate_records(
        manifest["governed_materials"],
        paths=GOVERNED_MATERIAL_PATHS,
        label="governed",
        root=root,
    )
    if file_sha256(root / STANDARD_RELATIVE) != FROZEN_STANDARD_SHA256:
        raise ValueError("frozen V1.6 standard hash changed")
    standard_text = (root / STANDARD_RELATIVE).read_text(encoding="utf-8")
    if f"release_target: {FROZEN_STANDARD_RELEASE_TARGET}" not in standard_text:
        raise ValueError("frozen V1.6 standard release target changed")
    if manifest["allowed_paths"] != list(ALLOWED_PROMOTION_PATHS):
        raise ValueError("V1.6.3 promotion allowlist is invalid")
    try:
        historical_manifest = json.loads(
            (root / HISTORICAL_PROMOTION_PATHS[1]).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("historical V1.6.2 promotion manifest is invalid") from exc
    surface = public_contract_surface()
    for field, expected in surface.items():
        if manifest.get(field) != list(expected) or historical_manifest.get(field) != list(
            expected
        ):
            raise ValueError(f"V1.6.3 public contract field {field} drifted")
    if (
        normalize_release_version(release_version, label="requested release version")
        != TO_VERSION
    ):
        raise ValueError("requested release version is not the V1.6.3 patch identity")
    surfaces = _version_surfaces(root)
    if set(surfaces.values()) != {TO_VERSION}:
        raise ValueError("Python/web/runtime/Docker/Render/OpenAPI/workflow versions drifted")
    qualification = manifest["qualification"]
    if qualification != {
        "status": "NOT_EXECUTED",
        "candidate_commit": None,
        "candidate_tree": None,
        "reason": STATIC_QUALIFICATION_REASON,
    }:
        raise ValueError("V1.6.3 static qualification state is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "functional_parent_commit": FUNCTIONAL_PARENT_COMMIT,
        "functional_parent_tree": FUNCTIONAL_PARENT_TREE,
        "frozen_standard_sha256": FROZEN_STANDARD_SHA256,
        "historical_promotion_materials": historical,
        "governed_materials": governed,
        "allowed_paths": list(ALLOWED_PROMOTION_PATHS),
        "version_surfaces": surfaces,
        "qualification": qualification,
    }


def _git(root: Path, *args: str) -> str:
    from firelens.evaluation.release_promotion import _git as promotion_git

    return promotion_git(root, *args)


def validate_patch_promotion(
    root: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
    clean_starting_state_bound: bool = False,
) -> dict[str, Any]:
    """Bind a clean exact V1.6.3 candidate and reject any extra patch paths."""

    report = validate_patch_manifest(root, release_version=release_version)
    if COMMIT_RE.fullmatch(commit) is None or COMMIT_RE.fullmatch(tree) is None:
        raise ValueError("V1.6.3 candidate commit/tree must be full lowercase Git SHAs")
    if not ((root / ".git").exists() or (root / ".git").is_file()):
        raise ValueError("V1.6.3 exact commit/tree qualification was not executed")
    if (
        _git(root, "rev-parse", "HEAD") != commit
        or _git(root, "rev-parse", "HEAD^{tree}") != tree
    ):
        raise ValueError("V1.6.3 checkout does not match candidate identity")
    if not clean_starting_state_bound and _git(
        root, "status", "--porcelain", "--untracked-files=all"
    ):
        raise ValueError("V1.6.3 exact commit/tree qualification requires a clean checkout")
    bind_functional_parent(
        root,
        parent_commit=FUNCTIONAL_PARENT_COMMIT,
        parent_tree=FUNCTIONAL_PARENT_TREE,
        commit=commit,
    )
    promotion_commit = unique_promotion_commit(
        root, parent_commit=FUNCTIONAL_PARENT_COMMIT, commit=commit
    )
    changed = [
        path
        for path in _git(
            root, "diff", "--name-only", FUNCTIONAL_PARENT_COMMIT, promotion_commit
        ).splitlines()
        if path
    ]
    extra = [path for path in changed if path not in ALLOWED_PROMOTION_PATHS]
    if extra:
        raise ValueError("V1.6.3 promotion diff contains non-allowlisted paths")
    return {
        **report,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "promotion_commit": promotion_commit,
        "qualification": {
            "status": "EXECUTED",
            "candidate_commit": commit,
            "candidate_tree": tree,
        },
    }


def patch_promotion_material_record(root: Path) -> dict[str, object]:
    return file_record(root, MANIFEST_RELATIVE)
