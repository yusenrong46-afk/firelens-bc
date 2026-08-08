from __future__ import annotations

import json
from pathlib import Path

import pytest

from firelens.config import FireLensConfig
from scripts.write_runtime_candidate import (
    build_runtime_candidate,
    main,
    write_runtime_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b00544c1927ffa12d98689f6a4b0b44b6c7de7e1"


def _candidate(**overrides):
    values = {
        "commit": COMMIT,
        "benchmark_id": "firelens_v1_5_2",
        "release_version": "1.5.0-rc.1",
        "corpus_manifest_path": (ROOT / "data/processed/firelens_static_corpus.manifest.json"),
        "vector_manifest_path": ROOT / "data/index/firelens_vectors.manifest.json",
    }
    values.update(overrides)
    return build_runtime_candidate(**values)


def test_runtime_candidate_is_exactly_bound_to_commit_and_shipped_manifests() -> None:
    assert _candidate() == {
        "schema_version": "firelens.runtime_candidate.v1",
        "candidate_id": f"firelens-v1-5-2:{COMMIT}",
        "release_version": "1.5.0-rc.1",
        "build_commit": COMMIT,
        "corpus_version": "firelens_static_corpus.v1",
        "embedding_model": "openai/text-embedding-3-small",
        "retrieval_text_strategy": "metadata_context_v1",
    }


def test_runtime_candidate_refuses_invalid_commit_and_manifest_mismatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="full lowercase"):
        _candidate(commit="unknown")

    vector = json.loads(
        (ROOT / "data/index/firelens_vectors.manifest.json").read_text(encoding="utf-8")
    )
    vector["corpus_version"] = "different"
    vector_path = tmp_path / "vector.json"
    vector_path.write_text(json.dumps(vector), encoding="utf-8")
    with pytest.raises(ValueError, match="different corpus"):
        _candidate(vector_manifest_path=vector_path)


def test_runtime_candidate_writer_is_atomic_and_refuses_symlink(tmp_path: Path) -> None:
    output = tmp_path / "config/runtime_candidate.v1.json"
    write_runtime_candidate(output, _candidate())
    assert json.loads(output.read_text(encoding="utf-8"))["build_commit"] == COMMIT
    assert output.read_text(encoding="utf-8").endswith("\n")

    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        write_runtime_candidate(linked, _candidate())


def test_runtime_candidate_cli_fails_closed_without_commit(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path / "candidate.json"), "--commit", ""]) == 2


def test_deployment_packaging_includes_governance_and_narrows_vercel_data() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for required in (
        "app.py",
        "config/runtime_artifact_allowlist.v1.json",
        "data/repairs/text_overrides.yaml",
        "scripts/write_runtime_candidate.py",
        "RENDER_GIT_COMMIT",
    ):
        assert required in dockerfile
    vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    include = vercel["services"]["firelens"]["functions"]["**/*.py"]["includeFiles"]
    assert include != "data/**"
    assert "data/evaluation" not in include
    assert "data/repairs/text_overrides.yaml" in include
    assert "config/runtime_*.json" in include
    assert len(include) <= 256


def test_render_identity_is_exposed_by_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("FIRELENS_REQUIRE_ZDR", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", COMMIT)
    monkeypatch.setenv("RENDER_INSTANCE_ID", "instance-123")
    config = FireLensConfig.from_env(tmp_path)
    assert config.build_commit == COMMIT
    assert config.deployment_id == "instance-123"
    assert config.deployment_environment == "production"
