from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from firelens.retrieval_review import (
    RetrievalOwnerReview,
    build_retrieval_review_template,
    validate_retrieval_owner_review,
)


def _dataset(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "dataset_version": "test.v1",
                "frozen_at": "2026-07-28T00:00:00Z",
                "cases": [
                    {
                        "id": "V1-HOLD-101",
                        "split": "holdout",
                        "category": "single_source",
                        "risk_level": "ordinary",
                        "question": "What does being held mean?",
                        "expected_route": "static",
                        "expected_status": "answer",
                        "acceptable_evidence": [{"source_id": "source-a"}],
                    },
                    {
                        "id": "V1-HOLD-102",
                        "split": "holdout",
                        "category": "single_source",
                        "risk_level": "ordinary",
                        "question": "What does under control mean?",
                        "expected_route": "static",
                        "expected_status": "answer",
                        "acceptable_evidence": [{"source_id": "source-b"}],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write(path: Path, review: RetrievalOwnerReview) -> None:
    path.write_text(
        yaml.safe_dump(review.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )


def test_pending_retrieval_review_is_not_qualified(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.yaml"
    review_path = tmp_path / "review.yaml"
    _dataset(dataset_path)
    _write(review_path, build_retrieval_review_template(dataset_path))

    summary = validate_retrieval_owner_review(dataset_path, review_path, expected_case_count=2)

    assert summary["case_count"] == 2
    assert summary["approved_case_count"] == 0
    assert not summary["qualified"]


def test_complete_retrieval_review_qualifies(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.yaml"
    review_path = tmp_path / "review.yaml"
    _dataset(dataset_path)
    review = build_retrieval_review_template(dataset_path)
    review = review.model_copy(
        update={
            "reviewer": "Owner",
            "reviewed_at": datetime.now(UTC),
            "cases": [
                case.model_copy(
                    update={
                        "question_is_independent": True,
                        "answerability_correct": True,
                        "acceptable_evidence_correct": True,
                        "decision": "approve",
                    }
                )
                for case in review.cases
            ],
        }
    )
    _write(review_path, review)

    summary = validate_retrieval_owner_review(dataset_path, review_path, expected_case_count=2)

    assert summary["approved_case_count"] == 2
    assert summary["qualified"]


def test_review_is_bound_to_dataset_hash(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.yaml"
    review_path = tmp_path / "review.yaml"
    _dataset(dataset_path)
    _write(review_path, build_retrieval_review_template(dataset_path))
    dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dataset hash"):
        validate_retrieval_owner_review(dataset_path, review_path, expected_case_count=2)


def test_blank_reviewer_is_rejected(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.yaml"
    _dataset(dataset_path)
    payload = build_retrieval_review_template(dataset_path).model_dump(mode="json")
    payload["reviewer"] = "  "

    with pytest.raises(ValueError, match="reviewer must not be blank"):
        RetrievalOwnerReview.model_validate(payload)
