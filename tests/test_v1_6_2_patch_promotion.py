from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from firelens.evaluation import v1_6_2_patch_promotion
from firelens.evaluation.candidate_evidence_documents import evidence_materials
from firelens.evaluation.common import file_sha256
from firelens.evaluation.v1_6_2_patch_promotion import (
    BASE_COMMIT,
    BASE_TREE,
    FROM_VERSION,
    FROZEN_PATCH_MANIFEST_SHA256,
    FROZEN_STANDARD_RELEASE_TARGET,
    FROZEN_STANDARD_SHA256,
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
from scripts.export_openapi import build_export_config

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
    for relative in VERSION_SURFACE_PATHS:
        path = root / relative
        path.write_text(
            path.read_text(encoding="utf-8").replace("1.6.4", TO_VERSION),
            encoding="utf-8",
        )
    return root


def test_patch_manifest_binds_base_standard_governed_and_historical_materials() -> None:
    manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))

    assert manifest == patch_promotion_manifest_document(ROOT)
    assert file_sha256(ROOT / MANIFEST_RELATIVE) == FROZEN_PATCH_MANIFEST_SHA256
    assert manifest["from_version"] == FROM_VERSION == "1.6.0"
    assert manifest["to_version"] == TO_VERSION == "1.6.2"
    assert manifest["base_commit"] == BASE_COMMIT
    assert manifest["base_tree"] == BASE_TREE
    assert manifest["frozen_standard_sha256"] == FROZEN_STANDARD_SHA256
    assert manifest["qualification"] == {
        "status": "NOT_EXECUTED",
        "candidate_commit": None,
        "candidate_tree": None,
        "reason": STATIC_QUALIFICATION_REASON,
    }
    assert [item["name"] for item in manifest["governed_materials"]] == list(
        GOVERNED_MATERIAL_PATHS
    )
    assert (
        tuple(item["sha256"] for item in manifest["historical_promotion_materials"])
        == HISTORICAL_PROMOTION_SHA256
    )


def test_historical_v1_6_0_promotion_files_remain_byte_unchanged() -> None:
    assert tuple(file_sha256(ROOT / path) for path in HISTORICAL_PROMOTION_PATHS) == (
        HISTORICAL_PROMOTION_SHA256
    )
    standard = load_v1_6_standard(ROOT)
    assert standard.release_target == FROZEN_STANDARD_RELEASE_TARGET
    assert file_sha256(ROOT / STANDARD_RELATIVE) == FROZEN_STANDARD_SHA256


def test_patch_static_validator_accepts_current_bound_materials(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    report = validate_patch_manifest(root, release_version=TO_VERSION)

    assert report["qualification"]["status"] == "NOT_EXECUTED"
    assert set(report["version_surfaces"].values()) == {TO_VERSION}


def test_patch_static_validator_allows_newer_governed_artifacts_but_rejects_version_drift(
    tmp_path: Path,
) -> None:
    governed = _fixture_root(tmp_path / "governed")
    path = governed / GOVERNED_MATERIAL_PATHS[0]
    path.write_bytes(path.read_bytes() + b"\n")
    assert (
        validate_patch_manifest(governed, release_version=TO_VERSION)["to_version"]
        == TO_VERSION
    )

    version = _fixture_root(tmp_path / "version")
    package_path = version / "apps/web/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = "1.6.1"
    package_path.write_text(json.dumps(package) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="versions drifted"):
        validate_patch_manifest(version, release_version=TO_VERSION)

    lock_version = _fixture_root(tmp_path / "lock-version")
    lock_path = lock_version / "apps/web/package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["packages"][""]["version"] = "1.6.1"
    lock_path.write_text(json.dumps(lock) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="versions drifted"):
        validate_patch_manifest(lock_version, release_version=TO_VERSION)

    requested = _fixture_root(tmp_path / "requested")
    with pytest.raises(ValueError, match="requested release version"):
        validate_patch_manifest(requested, release_version="1.6.1")


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("base_commit", "a" * 40),
        ("base_tree", "b" * 40),
        ("frozen_standard_sha256", "c" * 64),
    ),
)
def test_patch_static_validator_rejects_base_or_standard_binding_drift(
    tmp_path: Path, field: str, replacement: str
) -> None:
    root = _fixture_root(tmp_path)
    manifest_path = root / MANIFEST_RELATIVE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = replacement
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="frozen V1.6.2 patch-promotion manifest hash changed"):
        validate_patch_manifest(root, release_version=TO_VERSION)


def test_patch_static_validator_rejects_coordinated_public_contract_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    original = v1_6_2_patch_promotion.public_contract_surface()
    drifted = {
        **original,
        "response_mode_values": (*original["response_mode_values"], "invented_mode"),
    }
    monkeypatch.setattr(
        v1_6_2_patch_promotion,
        "public_contract_surface",
        lambda: drifted,
    )
    with pytest.raises(ValueError, match="public contract field response_mode_values drifted"):
        validate_patch_manifest(root, release_version=TO_VERSION)


def test_patch_exact_qualification_refuses_a_non_git_fixture(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    with pytest.raises(ValueError, match="not executed"):
        validate_patch_promotion(
            root,
            commit="a" * 40,
            tree="b" * 40,
            release_version=TO_VERSION,
        )


def test_candidate_material_selection_is_version_specific() -> None:
    historical = {item["name"] for item in evidence_materials(ROOT, release_version="1.6.0")}
    patch = {item["name"] for item in evidence_materials(ROOT, release_version=TO_VERSION)}

    assert "config/firelens.v1_6_release_promotion.v1.json" in historical
    assert MANIFEST_RELATIVE not in historical
    assert MANIFEST_RELATIVE in patch
    assert "config/firelens.v1_6_release_promotion.v1.json" not in patch


def test_openapi_export_ignores_local_release_version_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "FIRELENS_RELEASE_VERSION=1.6.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRELENS_RELEASE_VERSION", "1.5.3-rc.1")

    config = build_export_config(tmp_path)

    assert config.release_version == "1.6.4"
