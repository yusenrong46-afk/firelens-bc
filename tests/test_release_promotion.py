from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from firelens.config import DEFAULT_RELEASE_VERSION
from firelens.evaluation.common import file_sha256
from firelens.evaluation.release_promotion import (
    ALLOWED_PROMOTION_PATHS,
    FROM_VERSION,
    MANIFEST_RELATIVE,
    TO_VERSION,
    bind_functional_parent,
    normalize_release_version,
    public_contract_surface,
    unique_promotion_commit,
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
    assert report["promotion_commit"] == "1702db85ae32871c7bd9d5a9b27c3116a6a26176"


def test_promoted_merge_commit_binds_functional_parent_as_ancestor() -> None:
    if DEFAULT_RELEASE_VERSION != TO_VERSION:
        return
    second = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "HEAD^2"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if second.returncode != 0:
        pytest.skip("checkout is not a merge commit")
    first = subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=ROOT, text=True).strip()
    manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    assert first != manifest["functional_parent_commit"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    report = validate_release_promotion(
        ROOT, commit=commit, tree=tree, release_version=TO_VERSION
    )
    assert report["functional_parent_commit"] == manifest["functional_parent_commit"]
    assert report["functional_parent_tree"] == manifest["functional_parent_tree"]
    assert report["promotion_commit"] == "1702db85ae32871c7bd9d5a9b27c3116a6a26176"
    reachable = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "-c",
            "core.commitGraph=false",
            "rev-list",
            "--max-count=1",
            report["promotion_commit"],
            "--not",
            commit,
        ],
        text=True,
    ).strip()
    assert reachable == ""


def test_promotion_validator_rejects_a_non_head_commit() -> None:
    if DEFAULT_RELEASE_VERSION != TO_VERSION:
        return
    head_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    parent = subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=ROOT, text=True).strip()
    with pytest.raises(ValueError, match="checkout does not match candidate identity"):
        validate_release_promotion(
            ROOT, commit=parent, tree=head_tree, release_version=TO_VERSION
        )


def _empty_git_commit(repo: Path, message: str, env: dict[str, str]) -> str:
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", message],
        cwd=repo,
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def test_functional_parent_binding_uses_ancestry_not_first_parent(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Thomas",
        "GIT_AUTHOR_EMAIL": "yusenrong46@gmail.com",
        "GIT_COMMITTER_NAME": "Thomas",
        "GIT_COMMITTER_EMAIL": "yusenrong46@gmail.com",
    }
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    shared = _empty_git_commit(repo, "shared root", env)
    functional = _empty_git_commit(repo, "functional parent", env)
    functional_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True
    ).strip()
    promotion = _empty_git_commit(repo, "promotion", env)
    subprocess.run(
        ["git", "checkout", "-b", "previous-main", shared],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    main_tip = _empty_git_commit(repo, "previous main", env)
    subprocess.run(
        ["git", "merge", "--no-ff", promotion, "-m", "merge promotion"],
        cwd=repo,
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    merge = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    first = subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=repo, text=True).strip()
    assert first == main_tip
    assert first != functional
    bind_functional_parent(
        repo, parent_commit=functional, parent_tree=functional_tree, commit=merge
    )
    assert unique_promotion_commit(repo, parent_commit=functional, commit=merge) == promotion
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    subprocess.run(["git", "init"], cwd=decoy, check=True, capture_output=True, text=True)
    _empty_git_commit(decoy, "decoy", env)
    previous_git_dir = os.environ.get("GIT_DIR")
    os.environ["GIT_DIR"] = str(decoy / ".git")
    try:
        bind_functional_parent(
            repo, parent_commit=functional, parent_tree=functional_tree, commit=merge
        )
        assert (
            unique_promotion_commit(repo, parent_commit=functional, commit=merge) == promotion
        )
    finally:
        if previous_git_dir is None:
            os.environ.pop("GIT_DIR", None)
        else:
            os.environ["GIT_DIR"] = previous_git_dir
    later = _empty_git_commit(repo, "later main fix", env)
    assert unique_promotion_commit(repo, parent_commit=functional, commit=later) == promotion
    first_after_later = subprocess.check_output(
        ["git", "rev-parse", "HEAD^"], cwd=repo, text=True
    ).strip()
    assert first_after_later == merge
    with pytest.raises(ValueError, match="tree does not match"):
        bind_functional_parent(
            repo, parent_commit=functional, parent_tree="0" * 40, commit=merge
        )
    subprocess.run(
        ["git", "checkout", "--orphan", "unrelated"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    stray = _empty_git_commit(repo, "unrelated history", env)
    with pytest.raises(ValueError, match="does not precede"):
        bind_functional_parent(
            repo, parent_commit=functional, parent_tree=functional_tree, commit=stray
        )
