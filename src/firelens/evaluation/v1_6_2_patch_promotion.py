"""V1.6.2 patch-promotion binding. This is not a deployment or release-GO claim."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from firelens.evaluation.candidate_evidence_common import file_record
from firelens.evaluation.common import file_sha256
from firelens.evaluation.release_promotion import (
    normalize_release_version,
    public_contract_surface,
    version_surfaces,
)
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE

SCHEMA_VERSION = "firelens.v1_6_2_patch_promotion.v1"
MANIFEST_RELATIVE = "config/firelens.v1_6_2_patch_promotion.v1.json"
FROM_VERSION = "1.6.0"
TO_VERSION = "1.6.2"
FROZEN_STANDARD_RELEASE_TARGET = "1.6.0-rc.1"
FROZEN_STANDARD_SHA256 = "55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef"
FROZEN_PATCH_MANIFEST_SHA256 = (
    "c579bb38a1f97e52a65a69d40ffc262eec1154e5b52b3df29d1440a40c36ae25"
)
BASE_COMMIT = "b09e0402143f4c4a0602f542504507d40786fdc0"
BASE_TREE = "dc22981a24bf4648ee850b56a801f3bf43eee6eb"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
STATIC_QUALIFICATION_REASON = (
    "Static tracked manifest deliberately does not self-bind a mutable Git HEAD; "
    "exact qualification is bound by external current candidate evidence after execution."
)

HISTORICAL_PROMOTION_PATHS: tuple[str, ...] = (
    "src/firelens/evaluation/release_promotion.py",
    "config/firelens.v1_6_release_promotion.v1.json",
)
HISTORICAL_PROMOTION_SHA256: tuple[str, ...] = (
    "31bb68474dd6dfbe220b51a600ea2668fe4dc2ef4c2b8166a03f3de40de2c5de",
    "f90259567010edc1d31167f0ccb0e9284616b3550c9012c07dbc1955ee6292db",
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
)

_MANIFEST_FIELDS = {
    "schema_version",
    "from_version",
    "to_version",
    "base_commit",
    "base_tree",
    "frozen_standard_path",
    "frozen_standard_sha256",
    "historical_promotion_materials",
    "governed_materials",
    "public_claim_fields",
    "claim_support_fields",
    "proof_card_fields",
    "evidence_status_values",
    "response_mode_values",
    "publication_kind_values",
    "support_state_values",
    "qualification",
}


def patch_promotion_manifest_document(root: Path) -> dict[str, Any]:
    """Return the immutable V1.6.2 snapshot without rebinding current artifacts.

    ``governed_materials`` records what V1.6.2 evaluated.  Newer corpus or vector
    artifacts are intentionally not compared to those historical hashes; their
    identity belongs to their own candidate evidence.
    """

    return load_patch_promotion_manifest(root)


def load_patch_promotion_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V1.6.2 patch-promotion manifest is missing or invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _MANIFEST_FIELDS:
        raise ValueError("V1.6.2 patch-promotion manifest fields are invalid")
    return payload


def _patch_version_surfaces(root: Path) -> dict[str, str]:
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


def validate_patch_manifest(root: Path, *, release_version: str) -> dict[str, Any]:
    """Validate static patch identity without claiming exact-commit qualification."""

    manifest = load_patch_promotion_manifest(root)
    if file_sha256(root / MANIFEST_RELATIVE) != FROZEN_PATCH_MANIFEST_SHA256:
        raise ValueError("frozen V1.6.2 patch-promotion manifest hash changed")
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["from_version"] != FROM_VERSION
        or manifest["to_version"] != TO_VERSION
        or manifest["base_commit"] != BASE_COMMIT
        or manifest["base_tree"] != BASE_TREE
        or manifest["frozen_standard_path"] != STANDARD_RELATIVE
        or manifest["frozen_standard_sha256"] != FROZEN_STANDARD_SHA256
    ):
        raise ValueError("frozen V1.6.2 patch-promotion manifest constants changed")
    governed = manifest["governed_materials"]
    if (
        not isinstance(governed, list)
        or [record.get("name") for record in governed if isinstance(record, dict)]
        != list(GOVERNED_MATERIAL_PATHS)
        or any(
            not isinstance(record, dict)
            or set(record) != {"name", "sha256", "size_bytes"}
            or not isinstance(record["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
            or not isinstance(record["size_bytes"], int)
            or record["size_bytes"] < 0
            for record in governed
        )
    ):
        raise ValueError("frozen V1.6.2 governed-material snapshot is invalid")
    if file_sha256(root / STANDARD_RELATIVE) != FROZEN_STANDARD_SHA256:
        raise ValueError("frozen V1.6 standard hash changed")
    standard_text = (root / STANDARD_RELATIVE).read_text(encoding="utf-8")
    if f"release_target: {FROZEN_STANDARD_RELEASE_TARGET}" not in standard_text:
        raise ValueError("frozen V1.6 standard release target changed")
    historical_hashes = tuple(
        str(record["sha256"])
        for record in manifest["historical_promotion_materials"]
        if isinstance(record, dict)
    )
    if historical_hashes != HISTORICAL_PROMOTION_SHA256:
        raise ValueError("historical V1.6.0 promotion material changed")
    try:
        historical_manifest = json.loads(
            (root / HISTORICAL_PROMOTION_PATHS[1]).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("historical V1.6.0 promotion manifest is invalid") from exc
    if not isinstance(historical_manifest, dict):
        raise ValueError("historical V1.6.0 promotion manifest is invalid")
    current_surface = public_contract_surface()
    for field, current_values in current_surface.items():
        historical_values = historical_manifest.get(field)
        patch_values = manifest.get(field)
        if (
            not isinstance(historical_values, list)
            or not isinstance(patch_values, list)
            or tuple(historical_values) != current_values
            or patch_values != historical_values
        ):
            raise ValueError(f"V1.6.2 public contract field {field} drifted")
    if (
        normalize_release_version(release_version, label="requested release version")
        != TO_VERSION
    ):
        raise ValueError("requested release version is not the V1.6.2 patch identity")
    surfaces = _patch_version_surfaces(root)
    normalized = {
        normalize_release_version(value, label=name) for name, value in surfaces.items()
    }
    if normalized != {TO_VERSION} or any(value != TO_VERSION for value in surfaces.values()):
        raise ValueError("Python/web/runtime/Docker/Render/OpenAPI/workflow versions drifted")
    return {
        "schema_version": SCHEMA_VERSION,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "frozen_standard_sha256": FROZEN_STANDARD_SHA256,
        "historical_promotion_materials": manifest["historical_promotion_materials"],
        "governed_materials": manifest["governed_materials"],
        "version_surfaces": surfaces,
        "qualification": manifest["qualification"],
    }


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return env


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "-c", "core.commitGraph=false", *args],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if completed.returncode != 0:
        raise ValueError(f"V1.6.2 patch-promotion git command failed: git {' '.join(args)}")
    return completed.stdout.strip()


def validate_patch_promotion(
    root: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
    clean_starting_state_bound: bool = False,
) -> dict[str, Any]:
    """Bind an eventual clean exact V1.6.2 commit; never infer a dirty identity."""

    report = validate_patch_manifest(root, release_version=release_version)
    if COMMIT_RE.fullmatch(commit) is None or COMMIT_RE.fullmatch(tree) is None:
        raise ValueError("V1.6.2 candidate commit/tree must be full lowercase Git SHAs")
    if not ((root / ".git").exists() or (root / ".git").is_file()):
        raise ValueError("V1.6.2 exact commit/tree qualification was not executed")
    head = _git(root, "rev-parse", "HEAD")
    head_tree = _git(root, "rev-parse", "HEAD^{tree}")
    if head != commit or head_tree != tree:
        raise ValueError("V1.6.2 checkout does not match candidate identity")
    if not clean_starting_state_bound and _git(
        root, "status", "--porcelain", "--untracked-files=all"
    ):
        raise ValueError("V1.6.2 exact commit/tree qualification requires a clean checkout")
    observed_base_tree = _git(root, "rev-parse", f"{BASE_COMMIT}^{{tree}}")
    if observed_base_tree != BASE_TREE:
        raise ValueError("V1.6.2 base tree does not match the patch manifest")
    if commit == BASE_COMMIT:
        raise ValueError("V1.6.2 candidate must descend from the V1.6.0 base")
    leftover = _git(root, "rev-list", "--max-count=1", BASE_COMMIT, "--not", commit)
    if leftover:
        raise ValueError("V1.6.2 base commit is not an ancestor of the candidate")
    return {
        **report,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "qualification": {
            "status": "EXECUTED",
            "candidate_commit": commit,
            "candidate_tree": tree,
        },
    }


def patch_promotion_material_record(root: Path) -> dict[str, object]:
    return file_record(root, MANIFEST_RELATIVE)
