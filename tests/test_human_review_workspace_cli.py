from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import scripts.human_review_workspace as review_cli


def _manual_args(workspace: Path) -> list[str]:
    return [
        "prepare-frontend-manual",
        "--workspace",
        str(workspace),
        "--commit",
        "a" * 40,
        "--target-url",
        "https://candidate.example.test/",
        "--accessibility-reviewer-id",
        "a11y-001",
        "--accessibility-reviewer-name",
        "Alex Morgan",
        "--accessibility-credentials",
        "WCAG 2.2 and VoiceOver specialist",
        "--safety-reviewer-id",
        "safety-001",
        "--safety-reviewer-name",
        "Jordan Chen",
        "--safety-credentials",
        "Wildfire public-information safety specialist",
        "--release-adjudicator-id",
        "release-001",
        "--release-adjudicator-name",
        "Taylor Singh",
        "--release-adjudicator-credentials",
        "Independent release adjudicator",
    ]


def test_prepare_frontend_manual_builds_complete_blank_rosters(tmp_path: Path) -> None:
    workspace = tmp_path / "frontend-review"

    assert review_cli.main(_manual_args(workspace)) == 0

    bundle_path = workspace / "frontend_manual_review.template.yaml"
    payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    checks = [
        check for criterion in payload["criteria"] for check in criterion["atomic_checks"]
    ]
    assert payload["candidate"]["commit"] == "a" * 40
    assert payload["candidate"]["target_url"] == "https://candidate.example.test"
    assert len(payload["role_assignments"]) == 3
    assert len(payload["test_environments"]) == 5
    assert len(payload["coverage"]) == 50
    assert len(checks) == 30
    assert all(row["status"] is None for row in payload["coverage"])
    assert all(row["status"] is None for row in checks)
    assert payload["adjudication"]["decision"] is None
    assert payload["evidence"] == []
    assert stat.S_IMODE(bundle_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((workspace / "INSTRUCTIONS.md").stat().st_mode) == 0o600
    assert stat.S_IMODE((workspace / "evidence").stat().st_mode) == 0o700


def test_prepare_frontend_manual_rejects_placeholder_human(tmp_path: Path) -> None:
    args = _manual_args(tmp_path / "frontend-review")
    name_index = args.index("--accessibility-reviewer-name") + 1
    args[name_index] = "Accessibility Specialist"

    assert review_cli.main(args) == 2
    assert not (tmp_path / "frontend-review").exists()


def test_prepare_ux_template_builds_blank_complete_attempt_matrix(tmp_path: Path) -> None:
    output = tmp_path / "ux-before.yaml"

    assert (
        review_cli.main(
            [
                "prepare-ux-template",
                "--output",
                str(output),
                "--label",
                "before",
            ]
        )
        == 0
    )

    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert payload["label"] == "before"
    assert payload["participant_count"] == 12
    assert len(payload["participants"]) == 12
    assert len(payload["attempts"]) == 60
    assert all(
        all(value is None for value in row["criterion_results"].values())
        for row in payload["attempts"]
    )
    assert all(row["critical_error_codes"] == [] for row in payload["attempts"])
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_verify_ux_report_recomputes_completed_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "ux-before.yaml"
    assert (
        review_cli.main(["prepare-ux-template", "--output", str(output), "--label", "before"])
        == 0
    )
    capsys.readouterr()
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    payload.update(
        {
            "commit": "a" * 40,
            "deployment_id": "local-before",
            "moderator": "Morgan Lee",
            "observed_at": "2026-08-08T12:00:00+00:00",
        }
    )
    for row in payload["attempts"]:
        row["criterion_results"] = {key: True for key in row["criterion_results"]}
        row["duration_seconds"] = 30.0
        row["seq_score"] = 6
        row["confidence"] = 6
        row["observed_outcome"] = "Completed under direct observation."
    output.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert review_cli.main(["verify-ux-report", "--report", str(output)]) == 0
    captured = capsys.readouterr().out
    assert '"status": "verified_ux_report"' in captured
    assert '"task_completion_rate": 1.0' in captured
    assert '"qualification_eligible": false' in captured


def test_verify_frontend_manual_dispatches_strict_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "manual.yaml"
    bundle.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        review_cli,
        "validate_frontend_manual_review",
        lambda _path, *, expected_commit: {
            "qualified": True,
            "accessibility_qualified": True,
            "product_safety_qualified": True,
            "open_finding_count": 0,
            "commit": expected_commit,
        },
    )

    assert (
        review_cli.main(
            ["verify-frontend-manual", "--bundle", str(bundle), "--commit", "a" * 40]
        )
        == 0
    )


def test_session_status_rechecks_workspace_without_exposing_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "private-review"
    workspace.mkdir(mode=0o700)
    actors = (
        SimpleNamespace(actor_id="reviewer-a", role="reviewer"),
        SimpleNamespace(actor_id="reviewer-b", role="reviewer"),
        SimpleNamespace(actor_id="adjudicator", role="adjudicator"),
    )
    launch = SimpleNamespace(
        session=SimpleNamespace(session_id="semantic-001", actors=actors),
        input_recipe=SimpleNamespace(suite_kind="conversation"),
        allowed_origin="http://127.0.0.1:8765",
    )
    coordinator = SimpleNamespace(
        suite=SimpleNamespace(suite_sha256="a" * 64),
        progress=lambda actor_id: SimpleNamespace(
            session_state="independent_review",
            actor_state=(
                "blocked_on_reviewer_locks"
                if actor_id == "adjudicator"
                else "awaiting_presentation"
            ),
            completed_case_count=0,
            case_count=50,
            next_case_position=(None if actor_id == "adjudicator" else 1),
        ),
    )
    monkeypatch.setattr(
        review_cli,
        "resume_prepared_review",
        lambda _workspace: (coordinator, launch, {"reviewer-a": "secret-token"}),
    )

    assert review_cli.main(["session-status", "--workspace", str(workspace)]) == 0
    output = capsys.readouterr().out
    payload = review_cli.json.loads(output)
    assert payload["input_integrity_rechecked"] is True
    assert payload["session_state"] == "independent_review"
    assert payload["actors"][2]["actor_state"] == "blocked_on_reviewer_locks"
    assert "secret-token" not in output
