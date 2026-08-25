from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import firelens.review_workspace.qualification as qualification
from firelens.review_workspace.analysis import write_review_analysis
from firelens.review_workspace.exports import write_finalized_evidence_export
from firelens.review_workspace.inputs import (
    BlindCasePayload,
    BlindClaim,
    BlindRubric,
    ImportedReviewCase,
    InputFileIdentity,
    _build_suite,
    canonical_sha256,
)
from firelens.review_workspace.models import ReviewActor, ReviewSession
from firelens.review_workspace.session import (
    BlindReviewSession,
    ClaimAssessment,
    ReviewDecision,
)

START = datetime(2026, 8, 8, 19, 0, tzinfo=UTC)


def _report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "report_version": "firelens_conversation_benchmark_report.v1_1",
                "execution_mode": "live_provider",
                "commit": "a" * 40,
                "dataset_version": "test.v1",
                "dataset_sha256": "1" * 64,
                "corpus_version": "corpus.v1",
                "corpus_sha256": "2" * 64,
                "corpus_manifest_sha256": "3" * 64,
                "vector_matrix_sha256": "4" * 64,
                "vector_manifest_sha256": "5" * 64,
                "configuration_sha256": "6" * 64,
                "case_count": 2,
                "complete": True,
                "cost_budget_exceeded": False,
                "cases": [
                    {
                        "id": f"case-{index + 1:03d}",
                        "claims": [
                            {
                                "claim_id": f"claim-{index}",
                                "evidence_status": "verified_corpus",
                            }
                        ],
                    }
                    for index in range(2)
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _workspace(tmp_path: Path) -> tuple[Path, Path, BlindReviewSession, object]:
    report = tmp_path / "conversation-report.json"
    _report(report)
    metadata = report.stat()
    identity = InputFileIdentity(
        label="conversation_report",
        absolute_path=str(report.resolve()),
        sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
        size=metadata.st_size,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    cases = []
    for index in range(2):
        payload = BlindCasePayload(
            question=f"PRIVATE QUESTION {index}",
            history=(),
            rubric=BlindRubric(
                required_concepts=("scope",),
                forbidden_claims=("certainty",),
                required_limitations=("investigative only",),
            ),
            answer=f"PRIVATE ANSWER {index}",
            claims=(BlindClaim(claim_id=f"claim-{index}", text="PRIVATE CLAIM"),),
            supports=(),
            local_source_context=(),
        )
        cases.append(
            ImportedReviewCase(
                case_id=f"case-{index + 1:03d}",
                payload=payload,
                payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
                source_id_sha256s=(),
            )
        )
    suite = _build_suite(
        suite_kind="conversation",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256="1" * 64,
        input_files=(identity,),
        cases=tuple(cases),
    )
    session = ReviewSession(
        session_version="firelens_review_session.v1",
        session_id="semantic-qualification-001",
        review_kind="semantic",
        artifact_sha256=suite.suite_sha256,
        protocol_sha256="b" * 64,
        created_at=START,
        case_ids=tuple(case.case_id for case in cases),
        actors=(
            ReviewActor(actor_id="reviewer-a", display_name="Alice Rivers", role="reviewer"),
            ReviewActor(actor_id="reviewer-b", display_name="Benoit Lake", role="reviewer"),
            ReviewActor(
                actor_id="adjudicator",
                display_name="Casey Forest",
                role="adjudicator",
            ),
        ),
    )
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 100))
    workspace = tmp_path / "workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=session,
        suite=suite,
        clock=lambda: next(ticks),
    )
    decision_by_case = {
        f"case-{index + 1:03d}": ReviewDecision(
            disposition="approve",
            required_concepts_present=True,
            forbidden_claims_absent=True,
            required_limitations_present=True,
            claims=(ClaimAssessment(claim_id=f"claim-{index}", decision="supported"),),
        )
        for index in range(2)
    }
    for actor_id in ("reviewer-a", "reviewer-b"):
        while coordinator.progress(actor_id).actor_state != "complete_pending_lock":
            presentation = coordinator.present_next(actor_id)
            coordinator.acknowledge_display(actor_id, presentation.presentation_id)
            coordinator.record_decision(
                actor_id,
                presentation.presentation_id,
                decision_by_case[presentation.case_id],
            )
        coordinator.lock_reviewer(actor_id)
    while coordinator.progress("adjudicator").actor_state != "complete_pending_lock":
        presentation = coordinator.present_next("adjudicator")
        coordinator.acknowledge_display("adjudicator", presentation.presentation_id)
        coordinator.record_decision(
            "adjudicator",
            presentation.presentation_id,
            decision_by_case[presentation.case_id],
        )
    coordinator.finalize_adjudication("adjudicator")
    write_finalized_evidence_export(
        coordinator,
        clock=lambda: START + timedelta(minutes=5),
    )
    write_review_analysis(
        workspace,
        clock=lambda: START + timedelta(minutes=6),
    )
    launch = SimpleNamespace(
        session=session,
        input_recipe=SimpleNamespace(
            suite_kind="conversation",
            conversation_report=str(report),
            retrieval_dataset=None,
        ),
    )
    return workspace, report, coordinator, launch


def _approved_attestation(template: dict[str, object]) -> dict[str, object]:
    template.update(
        {
            "reviewer_id": "storage-001",
            "reviewer_name": "Dana Cedar",
            "reviewed_at": (START + timedelta(minutes=7)).isoformat(),
            "external_anchor_reference": "owner-vault://firelens/final-head/001",
            "decision": "approve",
        }
    )
    template["checks"] = {key: True for key in template["checks"]}  # type: ignore[index]
    return template


def test_independent_attestation_builds_closed_qualification_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, report, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(
        yaml.safe_dump(
            _approved_attestation(qualification.storage_attestation_template(workspace)),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    output = tmp_path / "qualification"

    manifest = qualification.build_review_qualification(
        workspace,
        attestation,
        output,
    )

    assert manifest.qualified is True
    assert manifest.case_count == 2
    assert manifest.adjudicated_finding_case_count == 0
    assert manifest.independent_storage_reviewer_name == "Dana Cedar"
    assert manifest.storage_checks.no_open_storage_findings is True
    assert len(manifest.actors) == 3
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())
    qualification.verify_review_qualification_package(
        output / "review-qualification.json",
        source_path=report,
        sidecar_path=output / "review-sidecar.yaml",
        summary_path=output / "review-summary.json",
        attestation_path=attestation,
        expected_suite_kind="conversation",
        expected_case_count=2,
    )


def test_qualification_verifier_requires_private_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, report, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(
        yaml.safe_dump(
            _approved_attestation(qualification.storage_attestation_template(workspace)),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    output = tmp_path / "qualification"
    qualification.build_review_qualification(workspace, attestation, output)

    with pytest.raises(ValueError, match="attestation.*required"):
        qualification.verify_review_qualification_package(
            output / "review-qualification.json",
            source_path=report,
            sidecar_path=output / "review-sidecar.yaml",
            summary_path=output / "review-summary.json",
        )


def test_session_actor_cannot_supply_independent_storage_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _report_path, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    payload = _approved_attestation(qualification.storage_attestation_template(workspace))
    payload["reviewer_name"] = "Alice Rivers"
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    attestation.chmod(0o600)

    with pytest.raises(ValueError, match="independent"):
        qualification.build_review_qualification(
            workspace,
            attestation,
            tmp_path / "qualification",
        )


def test_session_actor_id_cannot_be_reused_by_storage_reviewer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _report_path, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    payload = _approved_attestation(qualification.storage_attestation_template(workspace))
    payload["reviewer_id"] = "REVIEWER-A"
    payload["reviewer_name"] = "Dana Cedar"
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    attestation.chmod(0o600)

    with pytest.raises(ValueError, match="independent"):
        qualification.build_review_qualification(
            workspace,
            attestation,
            tmp_path / "qualification",
        )


def test_qualification_manifest_rejects_sidecar_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, report, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(
        yaml.safe_dump(
            _approved_attestation(qualification.storage_attestation_template(workspace)),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    output = tmp_path / "qualification"
    qualification.build_review_qualification(workspace, attestation, output)
    sidecar = output / "review-sidecar.yaml"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="review_sidecar_sha256"):
        qualification.verify_review_qualification_package(
            output / "review-qualification.json",
            source_path=report,
            sidecar_path=sidecar,
            summary_path=output / "review-summary.json",
            attestation_path=attestation,
        )


def test_qualification_verifier_recomputes_hash_consistent_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, report, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(
        yaml.safe_dump(
            _approved_attestation(qualification.storage_attestation_template(workspace)),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    output = tmp_path / "qualification"
    qualification.build_review_qualification(workspace, attestation, output)

    summary_path = output / "review-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["qualified"] = False
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest_path = output / "review-qualification.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["review_summary_sha256"] = qualification.file_sha256(summary_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="differs from validated evidence"):
        qualification.verify_review_qualification_package(
            manifest_path,
            source_path=report,
            sidecar_path=output / "review-sidecar.yaml",
            summary_path=summary_path,
            attestation_path=attestation,
        )


def test_storage_attestation_rejects_hardlinks(
    tmp_path: Path,
) -> None:
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text("not: relevant\n", encoding="utf-8")
    attestation.chmod(0o600)
    (tmp_path / "second-name.yaml").hardlink_to(attestation)

    with pytest.raises(ValueError, match="one private 0600 regular file"):
        qualification._load_private_attestation(attestation)


def test_failed_conversion_leaves_no_partial_qualification_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _report_path, coordinator, launch = _workspace(tmp_path)
    monkeypatch.setattr(
        qualification,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {}),
    )
    attestation = tmp_path / "storage-attestation.yaml"
    attestation.write_text(
        yaml.safe_dump(
            _approved_attestation(qualification.storage_attestation_template(workspace)),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    monkeypatch.setattr(
        qualification,
        "validate_owner_review",
        lambda *args, **kwargs: {"qualified": False},
    )
    output = tmp_path / "qualification"

    with pytest.raises(ValueError, match="does not satisfy"):
        qualification.build_review_qualification(workspace, attestation, output)

    assert not output.exists()
    assert not list(tmp_path.glob(".qualification.staging-*"))
