from __future__ import annotations

import subprocess
from pathlib import Path

from firelens.config import DEFAULT_RELEASE_VERSION
from firelens.evaluation.common import file_sha256
from firelens.evaluation.release_promotion import (
    ALLOWED_PROMOTION_PATHS,
    FROM_VERSION,
    MANIFEST_RELATIVE,
    TO_VERSION,
    normalize_release_version,
    public_contract_surface,
    validate_release_promotion,
    version_surfaces,
)
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE, load_v1_6_standard

ROOT = Path(__file__).resolve().parents[1]


def test_public_claim_support_and_proof_surfaces_are_frozen() -> None:
    surface = public_contract_surface()
    assert surface["public_claim_fields"] == (
        "claim_id",
        "evidence_status",
        "publication",
        "supports",
        "text",
        "trust",
    )
    assert surface["claim_support_fields"] == ("evidence_id", "quote")
    assert "publication" in surface["proof_card_fields"]
    assert "derivation" in surface["proof_card_fields"]
    assert surface["evidence_status_values"] == (
        "general_background",
        "verified_corpus",
    )
    assert "live" in surface["response_mode_values"]
    assert "mixed" in surface["response_mode_values"]
    assert "structured_reviewed" in surface["publication_kind_values"]
    assert "official_live_typed" in surface["publication_kind_values"]
    assert "structured_reviewed" in surface["support_state_values"]


def test_frozen_standard_release_target_remains_rc1() -> None:
    standard = load_v1_6_standard(ROOT)
    assert standard.release_target == FROM_VERSION
    assert STANDARD_RELATIVE == "data/evaluation/firelens_v1_6_upgrade_standard.yaml"


def test_promotion_allowlist_is_version_identity_paths_only() -> None:
    assert MANIFEST_RELATIVE in ALLOWED_PROMOTION_PATHS
    assert "data/evaluation/firelens_v1_6_upgrade_standard.yaml" not in ALLOWED_PROMOTION_PATHS
    assert "data/evaluation/hard_probe.v1.yaml" not in ALLOWED_PROMOTION_PATHS
    assert "data/typed_claims/high_risk_v1.yaml" not in ALLOWED_PROMOTION_PATHS
    assert (
        "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml"
        not in ALLOWED_PROMOTION_PATHS
    )


def test_current_version_surfaces_are_internally_consistent() -> None:
    surfaces = version_surfaces(ROOT)
    normalized = {
        name: normalize_release_version(value, label=name) for name, value in surfaces.items()
    }
    assert len(set(normalized.values())) == 1
    assert next(iter(normalized.values())) in {"1.6.0rc1", TO_VERSION}


def test_promoted_checkout_binds_the_internal_manifest() -> None:
    if DEFAULT_RELEASE_VERSION != TO_VERSION:
        return
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    report = validate_release_promotion(
        ROOT, commit=commit, tree=tree, release_version=TO_VERSION
    )
    assert report["to_version"] == TO_VERSION
    assert report["frozen_standard_sha256"] == file_sha256(ROOT / STANDARD_RELATIVE)
    assert set(report["version_surfaces"].values()) == {TO_VERSION}
