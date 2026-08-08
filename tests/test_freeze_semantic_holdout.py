from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.freeze_semantic_holdout as freeze
import scripts.upgrade_benchmark as benchmark_harness

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _development_request() -> dict:
    sources = sorted(
        hashlib.sha256(f"development-source-{index}".encode()).hexdigest() for index in range(2)
    )
    return {
        "request_version": "firelens_semantic_development_exposure_freeze_request.v1",
        "registry_id": "firelens-v1.5-2-semantic-development",
        "frozen_at": "2026-08-06T16:00:00+00:00",
        "review": {
            "attestation": "I reviewed canonical source and question-family identities.",
            "question_family_roster_canonicalized": True,
            "reviewed_at": "2026-08-06T15:55:00+00:00",
            "reviewer_id": "semantic-owner-001",
            "source_roster_canonicalized": True,
        },
        "datasets": [
            {
                "dataset_id": "semantic-development-v1",
                "dataset_sha256": "a" * 64,
                "source_id_sha256s": sources,
                "question_family_ids": [
                    "development-adjacent",
                    "development-capability",
                    "development-followup",
                    "development-safety",
                    "development-tangent",
                ],
            }
        ],
    }


def _private_payload(*, canary: str = "PRIVATE-PROMPT-CANARY") -> dict:
    families = ["evidence", "evacuation", "limitations", "location", "status"]
    cases = []
    for index in range(1, 26):
        source = hashlib.sha256(f"holdout-source-{((index - 1) % 5) + 1}".encode()).hexdigest()
        cases.append(
            {
                "case_id": f"SH{index:03d}",
                "input_payload": {
                    "history": [],
                    "input_version": "firelens_semantic_holdout_review_input.v1",
                    "question": f"{canary}-{index}",
                    "rubric": {
                        "expected_route": "static",
                        "expected_status": "answer",
                        "forbidden_claims": ["invented current incident status"],
                        "required_concepts": ["evidence-bound answer"],
                        "required_limitations": [],
                    },
                    "source_context": [
                        {
                            "context_id": f"context-{index:03d}",
                            "locator": f"owner-private-locator-{index}",
                            "source_id_sha256": source,
                            "text": f"PRIVATE-SOURCE-CONTEXT-{index}",
                        }
                    ],
                },
                "question_family_id": families[(index - 1) % len(families)],
                "risk_labels": ["high-risk" if index % 5 == 0 else "ordinary"],
                "source_id_sha256s": [source],
            }
        )
    return {
        "payload_version": "firelens_semantic_holdout_private_payload.v1",
        "dataset_id": "firelens-v1.5-2-semantic-holdout",
        "cases": cases,
    }


def _freeze_registry(tmp_path: Path) -> tuple[Path, Path, dict]:
    request_path = tmp_path / "development-request.json"
    registry_path = tmp_path / "development-registry.json"
    request = _development_request()
    _write_json(request_path, request)
    registry = freeze.freeze_development_registry(
        request_path,
        registry_path,
        attest_no_candidate=True,
        candidate_created_at=None,
    )
    return request_path, registry_path, registry


def _freeze_manifest(tmp_path: Path) -> tuple[Path, Path, Path, dict, dict]:
    request_path, registry_path, _ = _freeze_registry(tmp_path)
    private_path = tmp_path / "semantic-private.json"
    manifest_path = tmp_path / "semantic-manifest.json"
    private_payload = _private_payload()
    _write_json(private_path, private_payload)
    manifest = freeze.freeze_holdout_manifest(
        private_path,
        registry_path,
        manifest_path,
        audited_at="2026-08-06T17:00:00+00:00",
        frozen_at="2026-08-06T17:05:00+00:00",
        attest_no_candidate=True,
        candidate_created_at=None,
    )
    return request_path, registry_path, private_path, manifest_path, manifest


def test_freezes_and_recomputes_exact_public_contracts_without_private_values(
    tmp_path: Path,
) -> None:
    request_path, registry_path, private_path, manifest_path, manifest = _freeze_manifest(
        tmp_path
    )
    registry = freeze.validate_development_registry(request_path, registry_path)
    validated = freeze.validate_holdout_manifest(private_path, registry_path, manifest_path)

    registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    benchmark_harness._semantic_development_registry_payload(registry)
    benchmark_harness._semantic_holdout_manifest_payload(
        validated,
        development_registry=registry,
        development_registry_sha256=registry_sha256,
    )
    private_payload = json.loads(private_path.read_text(encoding="utf-8"))
    assert manifest["dataset_sha256"] == benchmark_harness._sha256_json(private_payload)
    assert manifest["case_roster"][0]["input_sha256"] == benchmark_harness._sha256_json(
        private_payload["cases"][0]["input_payload"]
    )
    public_text = manifest_path.read_text(encoding="utf-8")
    assert "PRIVATE-PROMPT-CANARY" not in public_text
    assert "PRIVATE-SOURCE-CONTEXT" not in public_text
    assert "input_payload" not in public_text
    assert "risk_labels" not in public_text
    assert manifest["question_family_distribution"] == {
        "evidence": 5,
        "evacuation": 5,
        "limitations": 5,
        "location": 5,
        "status": 5,
    }

    review_input = private_payload["cases"][0]["input_payload"]
    mutations = []
    changed_question = deepcopy(review_input)
    changed_question["question"] = "different private question"
    mutations.append(changed_question)
    changed_history = deepcopy(review_input)
    changed_history["history"] = [{"content": "prior user turn", "role": "user"}]
    mutations.append(changed_history)
    changed_rubric = deepcopy(review_input)
    changed_rubric["rubric"]["required_concepts"] = ["different private rubric"]
    mutations.append(changed_rubric)
    changed_context = deepcopy(review_input)
    changed_context["source_context"][0]["text"] = "different private source context"
    mutations.append(changed_context)
    assert all(
        benchmark_harness._sha256_json(changed) != manifest["case_roster"][0]["input_sha256"]
        for changed in mutations
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda payload: payload.update(cases=payload["cases"][:24]),
            "holdout_case_count_too_small",
        ),
        (
            lambda payload: [
                row.update(question_family_id="evidence") for row in payload["cases"]
            ],
            "holdout_family_count_too_small",
        ),
        (
            lambda payload: payload["cases"].append(deepcopy(payload["cases"][-1])),
            "private_case_roster_noncanonical",
        ),
        (
            lambda payload: payload["cases"][0].update(risk_labels=["ordinary", "ordinary"]),
            "private_risk_labels_noncanonical",
        ),
    ],
)
def test_refuses_small_or_duplicate_private_data(
    tmp_path: Path, mutation: object, reason: str
) -> None:
    _, registry_path, _ = _freeze_registry(tmp_path)
    payload = _private_payload()
    mutation(payload)  # type: ignore[operator]
    private_path = tmp_path / "private.json"
    _write_json(private_path, payload)

    with pytest.raises(freeze.FreezeRefusal, match=reason):
        freeze.freeze_holdout_manifest(
            private_path,
            registry_path,
            tmp_path / "manifest.json",
            audited_at="2026-08-06T17:00:00+00:00",
            frozen_at="2026-08-06T17:05:00+00:00",
            attest_no_candidate=True,
            candidate_created_at=None,
        )


@pytest.mark.parametrize("overlap_kind", ["source", "family"])
def test_refuses_exact_development_overlap(tmp_path: Path, overlap_kind: str) -> None:
    _, registry_path, registry = _freeze_registry(tmp_path)
    payload = _private_payload()
    if overlap_kind == "source":
        payload["cases"][0]["source_id_sha256s"] = [registry["source_id_sha256s"][0]]
        payload["cases"][0]["input_payload"]["source_context"][0]["source_id_sha256"] = (
            registry["source_id_sha256s"][0]
        )
        reason = "development_source_overlap"
    else:
        payload["cases"][0]["question_family_id"] = registry["question_family_ids"][0]
        payload["cases"] = sorted(payload["cases"], key=lambda row: row["case_id"])
        reason = "development_question_family_overlap"
    private_path = tmp_path / "private.json"
    _write_json(private_path, payload)

    with pytest.raises(freeze.FreezeRefusal, match=reason):
        freeze.freeze_holdout_manifest(
            private_path,
            registry_path,
            tmp_path / "manifest.json",
            audited_at="2026-08-06T17:00:00+00:00",
            frozen_at="2026-08-06T17:05:00+00:00",
            attest_no_candidate=True,
            candidate_created_at=None,
        )


def test_refuses_existing_output_and_symlink_paths(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_json(request_path, _development_request())
    output = tmp_path / "registry.json"
    output.write_text("owner data\n", encoding="utf-8")
    with pytest.raises(freeze.FreezeRefusal, match="output_exists"):
        freeze.freeze_development_registry(
            request_path,
            output,
            attest_no_candidate=True,
            candidate_created_at=None,
        )
    assert output.read_text(encoding="utf-8") == "owner data\n"

    linked_request = tmp_path / "linked-request.json"
    linked_request.symlink_to(request_path)
    with pytest.raises(freeze.FreezeRefusal, match="symlink_path_refused"):
        freeze.freeze_development_registry(
            linked_request,
            tmp_path / "other-registry.json",
            attest_no_candidate=True,
            candidate_created_at=None,
        )


def test_refuses_noncanonical_and_duplicate_json(tmp_path: Path) -> None:
    request = _development_request()
    request["datasets"][0]["question_family_ids"].reverse()
    request_path = tmp_path / "noncanonical.json"
    _write_json(request_path, request)
    with pytest.raises(freeze.FreezeRefusal, match="development_family_roster_noncanonical"):
        freeze.freeze_development_registry(
            request_path,
            tmp_path / "registry.json",
            attest_no_candidate=True,
            candidate_created_at=None,
        )

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(
        '{"request_version":"x","request_version":"y"}\n', encoding="utf-8"
    )
    with pytest.raises(freeze.FreezeRefusal, match="duplicate_json_key"):
        freeze.freeze_development_registry(
            duplicate_path,
            tmp_path / "other.json",
            attest_no_candidate=True,
            candidate_created_at=None,
        )


def test_refuses_freeze_after_candidate_started(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_json(request_path, _development_request())
    with pytest.raises(freeze.FreezeRefusal, match="candidate_already_started"):
        freeze.freeze_development_registry(
            request_path,
            tmp_path / "registry.json",
            attest_no_candidate=False,
            candidate_created_at="2026-08-06T16:05:00+00:00",
        )


def test_validation_detects_private_payload_change(tmp_path: Path) -> None:
    _, registry_path, private_path, manifest_path, _ = _freeze_manifest(tmp_path)
    payload = json.loads(private_path.read_text(encoding="utf-8"))
    payload["cases"][0]["input_payload"]["question"] = "changed private question"
    _write_json(private_path, payload)
    with pytest.raises(freeze.FreezeRefusal, match="holdout_manifest_recomputation_mismatch"):
        freeze.validate_holdout_manifest(private_path, registry_path, manifest_path)


def test_refuses_source_commitments_that_do_not_match_review_context(tmp_path: Path) -> None:
    _, registry_path, _ = _freeze_registry(tmp_path)
    payload = _private_payload()
    payload["cases"][0]["source_id_sha256s"] = ["f" * 64]
    private_path = tmp_path / "private.json"
    _write_json(private_path, payload)
    with pytest.raises(freeze.FreezeRefusal, match="private_source_context_roster_mismatch"):
        freeze.freeze_holdout_manifest(
            private_path,
            registry_path,
            tmp_path / "manifest.json",
            audited_at="2026-08-06T17:00:00+00:00",
            frozen_at="2026-08-06T17:05:00+00:00",
            attest_no_candidate=True,
            candidate_created_at=None,
        )


def test_cli_refusal_never_prints_private_values(tmp_path: Path) -> None:
    _, registry_path, _ = _freeze_registry(tmp_path)
    canary = "NEVER-PRINT-THIS-PRIVATE-PROMPT"
    payload = _private_payload(canary=canary)
    payload["cases"] = payload["cases"][:24]
    private_path = tmp_path / "private.json"
    _write_json(private_path, payload)
    completed = subprocess.run(
        [
            str(PYTHON),
            "scripts/freeze_semantic_holdout.py",
            "freeze-manifest",
            "--private-payload",
            str(private_path),
            "--development-registry",
            str(registry_path),
            "--output",
            str(tmp_path / "manifest.json"),
            "--audited-at",
            "2026-08-06T17:00:00+00:00",
            "--frozen-at",
            "2026-08-06T17:05:00+00:00",
            "--attest-no-candidate",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "holdout_case_count_too_small" in completed.stderr
    assert canary not in completed.stdout
    assert canary not in completed.stderr
