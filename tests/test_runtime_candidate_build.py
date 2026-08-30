from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from firelens.config import FireLensConfig
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from scripts.prepare_vercel_build import (
    BuildIdentityError,
    _build_candidate,
    _resolve_build_benchmark_id,
    _resolve_build_commit,
)
from scripts.write_runtime_candidate import (
    DEFAULT_BENCHMARK_ID,
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
        "corpus_manifest_path": (ROOT / "data/processed/firelens_static_corpus.manifest.json"),
        "vector_manifest_path": ROOT / "data/index/firelens_vectors.manifest.json",
    }
    values.update(overrides)
    return build_runtime_candidate(**values)


def test_runtime_candidate_is_exactly_bound_to_commit_and_shipped_manifests() -> None:
    assert _candidate() == {
        "schema_version": "firelens.runtime_candidate.v4",
        "candidate_id": f"firelens-v1-5-2:{COMMIT}",
        "release_version": FireLensConfig.model_fields["release_version"].default,
        "build_commit": COMMIT,
        "corpus_version": "firelens_static_corpus.v1",
        "corpus_sha256": hashlib.sha256(
            (ROOT / "data/processed/firelens_static_corpus.chunks.jsonl").read_bytes()
        ).hexdigest(),
        "corpus_manifest_sha256": hashlib.sha256(
            (ROOT / "data/processed/firelens_static_corpus.manifest.json").read_bytes()
        ).hexdigest(),
        "vector_matrix_sha256": hashlib.sha256(
            (ROOT / "data/index/firelens_vectors.npy").read_bytes()
        ).hexdigest(),
        "vector_manifest_sha256": hashlib.sha256(
            (ROOT / "data/index/firelens_vectors.manifest.json").read_bytes()
        ).hexdigest(),
        "embedding_model": "openai/text-embedding-3-small",
        "retrieval_text_strategy": "metadata_context_v1",
        "rerank_model": "cohere/rerank-4-pro",
        "generation_model": "openai/gpt-5.6-luna",
        **APPROVED_PRODUCTION_PRIVACY.candidate_fields(),
    }


def test_runtime_candidate_identity_changes_with_exact_retrieval_artifact_bytes(
    tmp_path: Path,
) -> None:
    candidates = []
    for label in ("a", "b"):
        root = tmp_path / label
        processed = root / "data/processed"
        index = root / "data/index"
        processed.mkdir(parents=True)
        index.mkdir(parents=True)
        corpus = processed / "firelens_static_corpus.chunks.jsonl"
        matrix = index / "firelens_vectors.npy"
        corpus.write_text(f"different corpus bytes {label}\n", encoding="utf-8")
        matrix.write_bytes(f"different vector bytes {label}".encode())
        corpus_manifest = processed / "firelens_static_corpus.manifest.json"
        corpus_manifest.write_text(
            json.dumps(
                {
                    "corpus_version": "same.v1",
                    "fixture_label": label,
                    "combined_chunk_file": (
                        "data/processed/firelens_static_corpus.chunks.jsonl"
                    ),
                }
            ),
            encoding="utf-8",
        )
        vector_manifest = index / "firelens_vectors.manifest.json"
        vector_manifest.write_text(
            json.dumps(
                {
                    "corpus_version": "same.v1",
                    "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                    "embedding_model": "openai/text-embedding-3-small",
                    "retrieval_text_strategy": "metadata_context_v1",
                    "matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        candidates.append(
            build_runtime_candidate(
                commit=COMMIT,
                benchmark_id="artifact_identity_probe",
                corpus_manifest_path=corpus_manifest,
                vector_manifest_path=vector_manifest,
            )
        )

    assert candidates[0]["candidate_id"] == candidates[1]["candidate_id"]
    assert candidates[0]["corpus_version"] == candidates[1]["corpus_version"]
    assert candidates[0]["corpus_sha256"] != candidates[1]["corpus_sha256"]
    assert candidates[0]["corpus_manifest_sha256"] != candidates[1]["corpus_manifest_sha256"]
    assert candidates[0]["vector_matrix_sha256"] != candidates[1]["vector_matrix_sha256"]
    assert candidates[0]["vector_manifest_sha256"] != candidates[1]["vector_manifest_sha256"]


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


def test_runtime_candidate_cli_defaults_to_current_rc2_identity(tmp_path: Path) -> None:
    output = tmp_path / "candidate.json"
    assert main(["--output", str(output), "--commit", COMMIT]) == 0
    candidate = json.loads(output.read_text(encoding="utf-8"))
    assert DEFAULT_BENCHMARK_ID == "firelens_v1_6_rc2"
    assert candidate["candidate_id"] == f"firelens-v1-6-rc2:{COMMIT}"


def test_vercel_build_accepts_explicit_local_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("FIRELENS_BUILD_COMMIT", COMMIT)
    assert _resolve_build_commit(tmp_path) == COMMIT


def test_vercel_build_uses_deploy_bound_benchmark_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRELENS_BENCHMARK_ID", "firelens_v1_6_2")
    assert _resolve_build_benchmark_id() == "firelens_v1_6_2"


def test_vercel_build_binds_the_deploy_benchmark_id_into_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRELENS_BENCHMARK_ID", "firelens_v1_6_2")
    candidate = _build_candidate(
        ROOT,
        commit=COMMIT,
        benchmark_id=_resolve_build_benchmark_id(),
    )
    assert candidate["candidate_id"] == f"firelens-v1-6-2:{COMMIT}"


def test_vercel_build_preserves_legacy_benchmark_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIRELENS_BENCHMARK_ID", raising=False)
    assert _resolve_build_benchmark_id() == DEFAULT_BENCHMARK_ID


def test_vercel_build_rejects_invalid_deploy_bound_benchmark_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRELENS_BENCHMARK_ID", "firelens v1.6.2")
    with pytest.raises(BuildIdentityError, match="benchmark ID"):
        _resolve_build_benchmark_id()


def test_vercel_build_falls_back_to_git_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("FIRELENS_BUILD_COMMIT", raising=False)

    def fake_run(args, **kwargs):
        assert args == ["git", "rev-parse", "HEAD"]
        return subprocess.CompletedProcess(args, 0, stdout=f"{COMMIT}\n", stderr="")

    monkeypatch.setattr("scripts.prepare_vercel_build.subprocess.run", fake_run)
    assert _resolve_build_commit(tmp_path) == COMMIT


def test_vercel_build_fails_closed_without_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("FIRELENS_BUILD_COMMIT", raising=False)

    def fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(128, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr("scripts.prepare_vercel_build.subprocess.run", fake_run)
    with pytest.raises(BuildIdentityError, match="build commit is missing"):
        _resolve_build_commit(tmp_path)


def test_vercel_build_rejects_short_environment_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("FIRELENS_BUILD_COMMIT", "deadbeef")
    with pytest.raises(BuildIdentityError, match="40-character"):
        _resolve_build_commit(tmp_path)


def test_deployment_packaging_includes_governance_and_narrows_vercel_data() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for required in (
        "app.py",
        "config/runtime_artifact_allowlist.v1.json",
        "COPY data/repairs/",
        "COPY data/typed_claims/",
        "scripts/write_runtime_candidate.py",
        "RENDER_GIT_COMMIT",
        "FIRELENS_EMBEDDING_ZDR=required",
        "FIRELENS_RERANKING_ZDR=optional",
        "FIRELENS_GENERATION_ZDR=required",
        "FIRELENS_RERANK_MODEL",
        "FIRELENS_GENERATION_MODEL",
        "ARG FIRELENS_RELEASE_VERSION=1.6.2",
        "ARG FIRELENS_BENCHMARK_ID=firelens_v1_6_2",
        "--benchmark-id \"$FIRELENS_BENCHMARK_ID\"",
    ):
        assert required in dockerfile
    assert (ROOT / "data/repairs/text_overrides.yaml").is_file()
    assert "1.5.0-rc.1" not in dockerfile
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "FIRELENS_RELEASE_VERSION" in render
    assert 'value: "1.6.2"' in render
    assert "1.5.0-rc.1" not in render
    writer = (ROOT / "scripts/write_runtime_candidate.py").read_text(encoding="utf-8")
    vercel_prep = (ROOT / "scripts/prepare_vercel_build.py").read_text(encoding="utf-8")
    assert "1.5.0-rc.1" not in writer
    assert "1.5.0-rc.1" not in vercel_prep
    assert "DEFAULT_RELEASE_VERSION" in writer
    assert "DEFAULT_RELEASE_VERSION" in vercel_prep
    assert "DEFAULT_BENCHMARK_ID" in vercel_prep
    assert "FIRELENS_BENCHMARK_ID" in vercel_prep
    assert "FIRELENS_BUILD_COMMIT" in vercel_prep
    assert FireLensConfig.model_fields["release_version"].default == "1.6.2"
    vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    include = vercel["services"]["firelens"]["functions"]["**/*.py"]["includeFiles"]
    assert include != "data/**"
    assert "data/evaluation" not in include
    assert "data/repairs/text_overrides.yaml" in include
    assert "data/typed_claims/high_risk_v1.yaml" in include
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
