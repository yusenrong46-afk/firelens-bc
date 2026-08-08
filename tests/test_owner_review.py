from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from firelens.owner_review import (
    OwnerSemanticReview,
    build_review_template,
    validate_owner_review,
)


def _report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "report_version": "firelens_conversation_benchmark_report.v1_1",
                "execution_mode": "live_provider",
                "commit": "abc123",
                "dataset_version": "test-dataset.v1",
                "dataset_sha256": "a" * 64,
                "corpus_version": "test-corpus.v1",
                "corpus_sha256": "b" * 64,
                "corpus_manifest_sha256": "c" * 64,
                "vector_matrix_sha256": "d" * 64,
                "vector_manifest_sha256": "e" * 64,
                "configuration_sha256": "f" * 64,
                "case_count": 2,
                "complete": True,
                "cost_budget_exceeded": False,
                "cases": [
                    {
                        "id": "V1.1-DEV-001",
                        "claims": [
                            {
                                "claim_id": "C1",
                                "evidence_status": "verified_corpus",
                            }
                        ],
                    },
                    {"id": "V1.1-RED-001", "claims": []},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_review(path: Path, review: OwnerSemanticReview) -> None:
    path.write_text(
        yaml.safe_dump(review.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def test_pending_template_is_hash_bound_but_not_qualified(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    review = build_review_template(report_path)
    _write_review(review_path, review)

    summary = validate_owner_review(report_path, review_path, expected_case_count=2)

    assert summary["case_count"] == 2
    assert summary["approved_case_count"] == 0
    assert not summary["qualified"]


def test_complete_owner_review_qualifies(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    review = build_review_template(report_path)
    approved_cases = []
    for case in review.cases:
        approved_cases.append(
            case.model_copy(
                update={
                    "required_concepts_present": True,
                    "forbidden_claims_absent": True,
                    "required_limitations_present": True,
                    "decision": "approve",
                    "claims": [
                        claim.model_copy(update={"decision": "supported"})
                        for claim in case.claims
                    ],
                }
            )
        )
    review = review.model_copy(
        update={
            "reviewer": "Owner",
            "reviewed_at": datetime.now(UTC),
            "cases": approved_cases,
        }
    )
    _write_review(review_path, review)

    summary = validate_owner_review(report_path, review_path, expected_case_count=2)

    assert summary["approved_case_count"] == 2
    assert summary["unsupported_verified_claim_count"] == 0
    assert summary["commit"] == "abc123"
    assert summary["dataset_sha256"] == "a" * 64
    assert summary["corpus_sha256"] == "b" * 64
    assert summary["vector_matrix_sha256"] == "d" * 64
    assert summary["configuration_sha256"] == "f" * 64
    assert summary["qualified"]


def test_offline_report_cannot_qualify(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["execution_mode"] = "offline_fake"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    review = build_review_template(report_path)
    approved_cases = [
        case.model_copy(
            update={
                "required_concepts_present": True,
                "forbidden_claims_absent": True,
                "required_limitations_present": True,
                "decision": "approve",
                "claims": [
                    claim.model_copy(update={"decision": "supported"}) for claim in case.claims
                ],
            }
        )
        for case in review.cases
    ]
    _write_review(
        review_path,
        review.model_copy(
            update={
                "reviewer": "Owner",
                "reviewed_at": datetime.now(UTC),
                "cases": approved_cases,
            }
        ),
    )

    summary = validate_owner_review(report_path, review_path, expected_case_count=2)

    assert not summary["live_provider_report"]
    assert not summary["qualified"]


def test_wrong_case_count_cannot_qualify(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    _write_review(review_path, build_review_template(report_path))

    summary = validate_owner_review(report_path, review_path)

    assert summary["expected_case_count"] == 50
    assert not summary["expected_case_count_present"]
    assert not summary["qualified"]


def test_blank_reviewer_is_rejected(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    _report(report_path)
    payload = build_review_template(report_path).model_dump(mode="json")
    payload["reviewer"] = "   "

    with pytest.raises(ValueError, match="reviewer must not be blank"):
        OwnerSemanticReview.model_validate(payload)


def test_review_rejects_report_hash_change(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    _write_review(review_path, build_review_template(report_path))
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="report hash"):
        validate_owner_review(report_path, review_path)


def test_review_rejects_missing_claim_decision(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.yaml"
    _report(report_path)
    review = build_review_template(report_path)
    first = review.cases[0].model_copy(update={"claims": []})
    _write_review(review_path, review.model_copy(update={"cases": [first, review.cases[1]]}))

    with pytest.raises(ValueError, match="claim mismatch"):
        validate_owner_review(report_path, review_path)
