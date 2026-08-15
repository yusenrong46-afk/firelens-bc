from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from firelens.runtime_artifact import (
    ArtifactIdentity,
    RuntimeArtifactError,
    build_runtime_inventory,
    compare_runtime_inventories,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/runtime_artifact_allowlist.v1.json"
COMMIT = "a" * 40


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _identity(platform: str) -> ArtifactIdentity:
    return ArtifactIdentity(
        platform=platform,
        platform_root="/var/task" if platform == "vercel" else "/app",
        artifact_id=f"{platform}-artifact-1",
        candidate_id="candidate-1",
        release_version="1.5.2-test.1",
        build_commit=COMMIT,
    )


def _artifact(root: Path, *, strategy: str = "metadata_context_v1") -> Path:
    (root / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTRACT, root / "config/runtime_artifact_allowlist.v1.json")
    _write(
        root / "config/runtime_candidate.v1.json",
        json.dumps(
            {
                "schema_version": "firelens.runtime_candidate.v3",
                "candidate_id": "candidate-1",
                "release_version": "1.5.2-test.1",
                "build_commit": COMMIT,
                "corpus_version": "corpus.test.v1",
                "embedding_model": "provider/embedding-test",
                "retrieval_text_strategy": strategy,
                "rerank_model": "provider/rerank-test",
                "generation_model": "provider/generation-test",
                "data_collection": "deny",
                "allow_fallbacks": "false",
                "require_parameters": "true",
                "embedding_zdr": "required",
                "reranking_zdr": "optional",
                "generation_zdr": "required",
            },
            sort_keys=True,
        ),
    )
    _write(root / "app.py", "from firelens.api import create_app\napp = create_app()\n")
    _write(root / "src/firelens/__init__.py", "\n")
    _write(root / "src/firelens/api.py", "def create_app():\n    return object()\n")
    _write(
        root / "pyproject.toml",
        '[project]\nname = "firelens-bc"\nversion = "1.5.2"\n',
    )
    _write(root / "requirements.lock", "fastapi==1.0.0\n")

    document_sha = "b" * 64
    chunk = {
        "schema_version": "chunk_record.v2",
        "chunk_id": "source:page:1:chunk:1",
        "parent_record_id": "source:page:1",
        "source_id": "source",
        "title": "Synthetic source",
        "publisher": "Synthetic publisher",
        "canonical_url": "https://example.test/source",
        "temporal_class": "stable_guidance",
        "authority_class": "provincial_government",
        "document_sha256": document_sha,
        "page_number": 1,
        "chunk_index": 1,
        "section_title": None,
        "review_provenance": "human_verified_repair",
        "text": "Approved repaired text.",
        "char_count": len("Approved repaired text."),
        "retrieved_at": "2026-08-06T00:00:00+00:00",
        "source_type": "pdf",
        "section_id": None,
        "locator": "page:1",
    }
    corpus_bytes = (json.dumps(chunk, sort_keys=True) + "\n").encode()
    _write(root / "data/processed/firelens_static_corpus.chunks.jsonl", corpus_bytes)
    _write(
        root / "data/processed/firelens_static_corpus.manifest.json",
        json.dumps(
            {
                "combined_chunk_file": ("data/processed/firelens_static_corpus.chunks.jsonl"),
                "combined_chunk_count": 1,
                "corpus_version": "corpus.test.v1",
                "registry_version": "repairs.test.v1",
                "repair_provenance_policy": "human_verified_only.v1",
            },
            sort_keys=True,
        ),
    )
    matrix_stream = io.BytesIO()
    np.save(matrix_stream, np.array([[0.25, 0.75]], dtype=np.float32), allow_pickle=False)
    matrix = matrix_stream.getvalue()
    _write(root / "data/index/firelens_vectors.npy", matrix)
    _write(
        root / "data/index/firelens_vectors.manifest.json",
        json.dumps(
            {
                "schema_version": "firelens_vector_index.v1",
                "corpus_version": "corpus.test.v1",
                "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
                "matrix_sha256": hashlib.sha256(matrix).hexdigest(),
                "embedding_model": "provider/embedding-test",
                "retrieval_text_strategy": strategy,
                "dimensions": 2,
                "chunk_ids": [chunk["chunk_id"]],
                "created_at": "2026-08-06T00:00:00+00:00",
            },
            sort_keys=True,
        ),
    )
    _write(
        root / "data/repairs/text_overrides.yaml",
        yaml.safe_dump(
            {
                "repair_registry_version": "repairs.test.v1",
                "reviewed_on": "2026-08-06",
                "repairs": [
                    {
                        "source_id": "source",
                        "page_number": 1,
                        "document_sha256": document_sha,
                        "review_status": "human_verified",
                        "reason": "Human reviewer confirmed the repaired text.",
                        "replacement_text": "Approved repaired text.",
                    }
                ],
            },
            sort_keys=True,
        ),
    )

    frontend = root / "apps/web/dist/client"
    _write(
        frontend / "index.html",
        (
            '<!doctype html><script type="module" src="/assets/app.js"></script>'
            '<link rel="stylesheet" href="/assets/app.css">'
            '<img src="/assets/logo.png" alt="">'
        ),
    )
    _write(frontend / "assets/app.js", 'import("./chunk.js");\n')
    _write(frontend / "assets/chunk.js", "export const value = 1;\n")
    _write(frontend / "assets/app.css", 'body{background:url("./logo.png")}\n')
    _write(frontend / "assets/logo.png", b"synthetic-png")
    _write(
        frontend / ".vite/manifest.json",
        json.dumps(
            {
                "index.html": {
                    "file": "assets/app.js",
                    "isEntry": True,
                    "css": ["assets/app.css"],
                    "assets": ["assets/logo.png"],
                    "dynamicImports": ["src/chunk.ts"],
                },
                "src/chunk.ts": {
                    "file": "assets/chunk.js",
                    "isDynamicEntry": True,
                },
            },
            sort_keys=True,
        ),
    )
    return root


def _inventory(root: Path, platform: str = "vercel") -> dict:
    return build_runtime_inventory(
        artifact_root=root,
        contract_path=CONTRACT,
        identity=_identity(platform),
    )


def test_build_inventory_retains_normalized_paths_hashes_and_identity(tmp_path: Path) -> None:
    report = _inventory(_artifact(tmp_path / "artifact"))

    assert report["schema_version"] == "firelens.runtime_artifact_inventory.v3"
    assert report["runtime_configuration"]["rerank_model"] == "provider/rerank-test"
    assert report["runtime_configuration"]["generation_model"] == "provider/generation-test"
    assert report["runtime_configuration"]["reranking_zdr"] == "optional"
    assert report["runtime_configuration"]["embedding_zdr"] == "required"
    assert report["assurance"] == {
        "scope": "staged_logical_bundle",
        "platform_export_provenance_verified": False,
        "runtime_candidate_identity_observed": False,
    }
    assert report["contract"]["sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert report["identity"] == {
        "platform": "vercel",
        "platform_root": "/var/task",
        "artifact_id": "vercel-artifact-1",
        "candidate_id": "candidate-1",
        "release_version": "1.5.2-test.1",
        "build_commit": COMMIT,
    }
    logical_paths = [entry["logical_path"] for entry in report["files"]]
    assert logical_paths == sorted(logical_paths)
    assert len(logical_paths) == len(set(logical_paths)) == report["file_count"]
    assert all(
        entry["platform_path"] == f"/var/task/{entry['logical_path']}"
        for entry in report["files"]
    )
    assert all(len(entry["sha256"]) == 64 for entry in report["files"])


@pytest.mark.parametrize(
    "logical_path",
    [
        "data/evaluation/case.yaml",
        "sealed_cases.json",
        "semantic_holdout.json",
        "output/report.json",
        "reviews/journal.jsonl",
        "ux/session.json",
        "adjudication/decision.json",
        "data/raw/source.pdf",
        "data/sources/registry.yaml",
        "intermediates/chunks.jsonl",
        "data/index/embedding_cache.jsonl",
        "state.lock",
        ".env.local",
        ".git/config",
        "docs/readme.md",
        "tests/test_app.py",
        "browser/profile.json",
        "node_modules/package/index.js",
        "src/firelens/owner_review.py",
    ],
)
def test_rejects_every_prohibited_artifact_class(tmp_path: Path, logical_path: str) -> None:
    root = _artifact(tmp_path / "artifact")
    _write(root / logical_path, "must not ship")

    with pytest.raises(RuntimeArtifactError, match="prohibited"):
        _inventory(root)


def test_rejects_missing_required_and_unallowlisted_files(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    (root / "requirements.lock").unlink()
    with pytest.raises(RuntimeArtifactError, match="missing required"):
        _inventory(root)

    _write(root / "requirements.lock", "fastapi==1.0.0\n")
    _write(root / "unexpected.txt", "extra")
    with pytest.raises(RuntimeArtifactError, match="unallowlisted"):
        _inventory(root)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_rejects_symlink_root_and_descendant(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    linked_root = tmp_path / "linked-artifact"
    linked_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(RuntimeArtifactError, match="symlink"):
        _inventory(linked_root)

    target = tmp_path / "external.js"
    target.write_text("external", encoding="utf-8")
    (root / "apps/web/dist/client/assets/app.js").unlink()
    (root / "apps/web/dist/client/assets/app.js").symlink_to(target)
    with pytest.raises(RuntimeArtifactError, match="symlink"):
        _inventory(root)


def test_rejects_hardlinked_artifact_input(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    entrypoint = root / "app.py"
    os.link(entrypoint, tmp_path / "external-app.py")

    with pytest.raises(RuntimeArtifactError, match="single-link"):
        _inventory(root)


@pytest.mark.parametrize(
    "reference,match",
    [
        ("https://cdn.example.test/app.js", "must be local"),
        ("../../../../secret.js", "path traversal"),
    ],
)
def test_rejects_external_and_traversing_frontend_inputs(
    tmp_path: Path, reference: str, match: str
) -> None:
    root = _artifact(tmp_path / "artifact")
    _write(
        root / "apps/web/dist/client/index.html",
        f'<script type="module" src="{reference}"></script>',
    )
    with pytest.raises(RuntimeArtifactError, match=match):
        _inventory(root)


def test_requires_complete_vite_reference_closure_and_rejects_orphans(
    tmp_path: Path,
) -> None:
    missing_root = _artifact(tmp_path / "missing")
    (missing_root / "apps/web/dist/client/assets/chunk.js").unlink()
    with pytest.raises(RuntimeArtifactError, match="missing files"):
        _inventory(missing_root)

    orphan_root = _artifact(tmp_path / "orphan")
    _write(
        orphan_root / "apps/web/dist/client/assets/orphan.js",
        "export const orphan = true;",
    )
    with pytest.raises(RuntimeArtifactError, match="unreferenced"):
        _inventory(orphan_root)

    laundered_root = _artifact(tmp_path / "laundered")
    _write(
        laundered_root / "apps/web/dist/client/assets/orphan.js",
        "export const orphan = true;",
    )
    manifest_path = laundered_root / "apps/web/dist/client/.vite/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["src/orphan.ts"] = {"file": "assets/orphan.js"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="unreachable entries"):
        _inventory(laundered_root)


def test_side_effect_and_worker_references_are_in_the_frontend_closure(
    tmp_path: Path,
) -> None:
    root = _artifact(tmp_path / "artifact")
    _write(
        root / "apps/web/dist/client/assets/app.js",
        'import "./missing-side-effect.js";\n'
        'new Worker(new URL("./missing-worker.js", import.meta.url));\n',
    )

    with pytest.raises(RuntimeArtifactError, match="missing files"):
        _inventory(root)


def test_rejects_non_runtime_python_modules(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    _write(root / "src/firelens/offline_experiment.py", "value = 1\n")

    with pytest.raises(RuntimeArtifactError, match="unallowlisted"):
        _inventory(root)


def test_rejects_non_application_entrypoint_and_invalid_vector_bytes(
    tmp_path: Path,
) -> None:
    no_app = _artifact(tmp_path / "no-app")
    _write(no_app / "app.py", "value = object()\n")
    with pytest.raises(RuntimeArtifactError, match="does not export app"):
        _inventory(no_app)

    invalid_vector = _artifact(tmp_path / "invalid-vector")
    matrix_path = invalid_vector / "data/index/firelens_vectors.npy"
    matrix_path.write_bytes(b"not-an-npy")
    manifest_path = invalid_vector / "data/index/firelens_vectors.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="valid non-pickled NPY"):
        _inventory(invalid_vector)


def test_requires_exact_approved_repair_provenance(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    registry_path = root / "data/repairs/text_overrides.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["repairs"][0]["review_status"] = "pending_owner_review"
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    with pytest.raises(RuntimeArtifactError, match="not approved"):
        _inventory(root)


def test_document_context_is_conditional_on_candidate_and_vector_manifest(
    tmp_path: Path,
) -> None:
    missing = _artifact(tmp_path / "missing", strategy="document_context_v2")
    with pytest.raises(RuntimeArtifactError, match="document_context_v2 is required"):
        _inventory(missing)

    mismatch = _artifact(tmp_path / "mismatch")
    vector_path = mismatch / "data/index/firelens_vectors.manifest.json"
    vector = json.loads(vector_path.read_text(encoding="utf-8"))
    vector["retrieval_text_strategy"] = "document_context_v2"
    vector_path.write_text(json.dumps(vector), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="retrieval_text_strategy differs"):
        _inventory(mismatch)

    complete = _artifact(tmp_path / "complete", strategy="document_context_v2")
    context_record = {
        "schema_version": "firelens_document_context.v2",
        "document_sha256": "b" * 64,
        "chunk_id": "source:page:1:chunk:1",
        "model_id": "provider/context-test",
        "prompt_sha256": "c" * 64,
        "context": "A synthetic retrieval context for the only test chunk.",
    }
    _write(
        complete / "data/index/document_context_v2.jsonl",
        json.dumps(context_record, sort_keys=True) + "\n",
    )
    report = _inventory(complete)
    assert report["runtime_configuration"]["retrieval_text_strategy"] == "document_context_v2"


def test_identity_must_match_frozen_candidate_configuration(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    wrong = copy.copy(_identity("vercel"))
    wrong = ArtifactIdentity(
        platform=wrong.platform,
        platform_root=wrong.platform_root,
        artifact_id=wrong.artifact_id,
        candidate_id="other-candidate",
        release_version=wrong.release_version,
        build_commit=wrong.build_commit,
    )
    with pytest.raises(RuntimeArtifactError, match="candidate_id differs"):
        build_runtime_inventory(
            artifact_root=root,
            contract_path=CONTRACT,
            identity=wrong,
        )


def test_compare_requires_same_logical_identity_across_vercel_and_docker(
    tmp_path: Path,
) -> None:
    vercel_root = _artifact(tmp_path / "vercel")
    docker_root = tmp_path / "docker"
    shutil.copytree(vercel_root, docker_root)
    vercel = _inventory(vercel_root, "vercel")
    docker = _inventory(docker_root, "docker")

    comparison = compare_runtime_inventories(vercel, docker)
    assert comparison["qualified"] is True
    assert comparison["release_qualified"] is False
    assert comparison["staged_logical_parity"] is True
    assert comparison["qualification_blockers"] == [
        "platform_export_provenance_unverified",
        "runtime_candidate_identity_not_observed",
    ]
    assert comparison["mismatches"] == []
    assert comparison["vercel_artifact_id"] != comparison["docker_artifact_id"]

    _write(
        docker_root / "apps/web/dist/client/assets/logo.png",
        b"different-synthetic-png",
    )
    changed = _inventory(docker_root, "docker")
    comparison = compare_runtime_inventories(vercel, changed)
    assert comparison["qualified"] is False
    assert comparison["mismatches"] == [
        {
            "kind": "logical_identity_mismatch",
            "logical_path": "apps/web/dist/client/assets/logo.png",
            "vercel": comparison["mismatches"][0]["vercel"],
            "docker": comparison["mismatches"][0]["docker"],
        }
    ]


def test_compare_fails_closed_when_rerank_or_zdr_policy_differs(tmp_path: Path) -> None:
    vercel_root = _artifact(tmp_path / "vercel")
    docker_root = tmp_path / "docker"
    shutil.copytree(vercel_root, docker_root)
    vercel = _inventory(vercel_root, "vercel")
    docker_candidate = json.loads(
        (docker_root / "config/runtime_candidate.v1.json").read_text(encoding="utf-8")
    )
    docker_candidate["rerank_model"] = "provider/other-rerank"
    docker_candidate["reranking_zdr"] = "required"
    _write(
        docker_root / "config/runtime_candidate.v1.json",
        json.dumps(docker_candidate, sort_keys=True),
    )
    docker = _inventory(docker_root, "docker")
    comparison = compare_runtime_inventories(vercel, docker)
    assert comparison["qualified"] is False
    assert {"kind": "runtime_configuration_mismatch"} in comparison["mismatches"]


def test_compare_rejects_tampered_inventory(tmp_path: Path) -> None:
    root = _artifact(tmp_path / "artifact")
    vercel = _inventory(root, "vercel")
    docker = _inventory(root, "docker")
    docker["files"][0]["size_bytes"] += 1

    with pytest.raises(RuntimeArtifactError, match="inventory_sha256"):
        compare_runtime_inventories(vercel, docker)


def test_cli_writes_inventory_and_returns_nonzero_for_mismatch(tmp_path: Path) -> None:
    vercel_root = _artifact(tmp_path / "vercel")
    docker_root = tmp_path / "docker"
    shutil.copytree(vercel_root, docker_root)
    vercel_output = tmp_path / "vercel.json"
    docker_output = tmp_path / "docker.json"
    comparison_output = tmp_path / "comparison.json"

    common = [
        "--contract",
        str(CONTRACT),
        "--candidate-id",
        "candidate-1",
        "--release-version",
        "1.5.2-test.1",
        "--build-commit",
        COMMIT,
    ]
    assert (
        main(
            [
                "inventory",
                "--artifact-root",
                str(vercel_root),
                "--platform",
                "vercel",
                "--platform-root",
                "/var/task",
                "--artifact-id",
                "vercel-artifact-1",
                "--output",
                str(vercel_output),
                *common,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "inventory",
                "--artifact-root",
                str(docker_root),
                "--platform",
                "docker",
                "--platform-root",
                "/app",
                "--artifact-id",
                "docker-artifact-1",
                "--output",
                str(docker_output),
                *common,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "compare",
                "--vercel-inventory",
                str(vercel_output),
                "--docker-inventory",
                str(docker_output),
                "--output",
                str(comparison_output),
            ]
        )
        == 0
    )
    comparison = json.loads(comparison_output.read_text(encoding="utf-8"))
    assert comparison["qualified"] is True
    assert comparison["release_qualified"] is False
    assert comparison["staged_logical_parity"] is True
