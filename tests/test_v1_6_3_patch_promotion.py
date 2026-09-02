from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from firelens.evaluation import v1_6_3_patch_promotion
from firelens.evaluation.candidate_evidence_documents import evidence_materials
from firelens.evaluation.common import file_sha256
from firelens.evaluation.v1_6_3_patch_promotion import (
    ALLOWED_PROMOTION_PATHS,
    FROM_VERSION,
    FROZEN_STANDARD_RELEASE_TARGET,
    FROZEN_STANDARD_SHA256,
    FUNCTIONAL_PARENT_COMMIT,
    FUNCTIONAL_PARENT_TREE,
    GOVERNED_MATERIAL_PATHS,
    HISTORICAL_PROMOTION_PATHS,
    HISTORICAL_PROMOTION_SHA256,
    MANIFEST_RELATIVE,
    STATIC_QUALIFICATION_REASON,
    TO_VERSION,
    patch_promotion_manifest_document,
    validate_patch_manifest,
    validate_patch_promotion,
)
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE, load_v1_6_standard

ROOT = Path(__file__).resolve().parents[1]
VERSION_SURFACE_PATHS = (
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "src/firelens/config.py",
    "Dockerfile",
    "render.yaml",
    "docs/openapi.v1.json",
    ".github/workflows/candidate.yml",
)


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "patch-fixture"
    for relative in (
        STANDARD_RELATIVE,
        MANIFEST_RELATIVE,
        *HISTORICAL_PROMOTION_PATHS,
        *GOVERNED_MATERIAL_PATHS,
        *VERSION_SURFACE_PATHS,
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_manifest_binds_exact_functional_parent_and_governed_materials() -> None:
    manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))

    assert manifest == patch_promotion_manifest_document(ROOT)
    assert manifest["from_version"] == FROM_VERSION == "1.6.2"
    assert manifest["to_version"] == TO_VERSION == "1.6.3"
    assert manifest["functional_parent_commit"] == FUNCTIONAL_PARENT_COMMIT
    assert manifest["functional_parent_tree"] == FUNCTIONAL_PARENT_TREE
    assert [item["name"] for item in manifest["governed_materials"]] == list(
        GOVERNED_MATERIAL_PATHS
    )
    assert manifest["allowed_paths"] == list(ALLOWED_PROMOTION_PATHS)
    assert manifest["qualification"] == {
        "status": "NOT_EXECUTED",
        "candidate_commit": None,
        "candidate_tree": None,
        "reason": STATIC_QUALIFICATION_REASON,
    }


@pytest.mark.skip(
    reason="V1.6.4 changes governed capability-registry files; the V1.6.3 current-tree bind is historical."
)
def test_static_validator_binds_parent_artifacts_and_frozen_contract() -> None:
    report = validate_patch_manifest(ROOT, release_version=TO_VERSION)

    assert report["functional_parent_commit"] == FUNCTIONAL_PARENT_COMMIT
    assert report["functional_parent_tree"] == FUNCTIONAL_PARENT_TREE
    assert set(report["version_surfaces"].values()) == {TO_VERSION}
    assert (
        tuple(item["sha256"] for item in report["historical_promotion_materials"])
        == HISTORICAL_PROMOTION_SHA256
    )
    assert file_sha256(ROOT / STANDARD_RELATIVE) == FROZEN_STANDARD_SHA256
    assert load_v1_6_standard(ROOT).release_target == FROZEN_STANDARD_RELEASE_TARGET


@pytest.mark.skip(
    reason="V1.6.4 changes governed capability-registry files; the V1.6.3 current-tree bind is historical."
)
def test_static_validator_rejects_governed_material_and_contract_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    governed = root / GOVERNED_MATERIAL_PATHS[0]
    governed.write_bytes(governed.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="governed material changed"):
        validate_patch_manifest(root, release_version=TO_VERSION)

    root = _fixture_root(tmp_path / "contract")
    original = v1_6_3_patch_promotion.public_contract_surface()
    monkeypatch.setattr(
        v1_6_3_patch_promotion,
        "public_contract_surface",
        lambda: {**original, "response_mode_values": (*original["response_mode_values"], "x")},
    )
    with pytest.raises(ValueError, match="public contract field response_mode_values drifted"):
        validate_patch_manifest(root, release_version=TO_VERSION)


@pytest.mark.skip(
    reason="V1.6.4 changes governed capability-registry files; the V1.6.3 current-tree bind is historical."
)
def test_exact_qualification_rejects_non_allowlisted_promotion_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    (root / ".git").mkdir()
    candidate = "a" * 40
    tree = "b" * 40
    monkeypatch.setattr(v1_6_3_patch_promotion, "_git", lambda *_args: candidate)
    monkeypatch.setattr(
        v1_6_3_patch_promotion, "bind_functional_parent", lambda _root, **_kw: None
    )
    monkeypatch.setattr(
        v1_6_3_patch_promotion,
        "unique_promotion_commit",
        lambda _root, **_kw: candidate,
    )
    monkeypatch.setattr(
        v1_6_3_patch_promotion,
        "_git",
        lambda _root, *args: (
            ""
            if args == ("status", "--porcelain", "--untracked-files=all")
            else tree
            if args == ("rev-parse", "HEAD^{tree}")
            else "src/firelens/answering/service.py"
            if args == ("diff", "--name-only", FUNCTIONAL_PARENT_COMMIT, candidate)
            else candidate
        ),
    )

    with pytest.raises(ValueError, match="non-allowlisted paths"):
        validate_patch_promotion(root, commit=candidate, tree=tree, release_version=TO_VERSION)


def test_candidate_material_selection_is_specific_to_v1_6_3() -> None:
    selected = {item["name"] for item in evidence_materials(ROOT, release_version=TO_VERSION)}

    assert MANIFEST_RELATIVE in selected
    assert "config/firelens.v1_6_2_patch_promotion.v1.json" not in selected
