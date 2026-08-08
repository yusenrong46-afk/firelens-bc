from __future__ import annotations

import hashlib
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

import firelens.review_workspace.preparation as preparation
from firelens.review_workspace.api import create_review_workspace_app
from firelens.review_workspace.inputs import (
    BlindCasePayload,
    BlindClaim,
    BlindRubric,
    ImportedReviewCase,
    InputFileIdentity,
    _build_suite,
    canonical_sha256,
)
from firelens.review_workspace.preparation import (
    ReviewInputRecipe,
    prepare_review_session,
    resume_prepared_review,
)

START = datetime(2026, 8, 8, 18, 0, tzinfo=UTC)


def _suite(tmp_path: Path):
    source = tmp_path / "input.json"
    source.write_text('{"fixture":true}\n', encoding="utf-8")
    metadata = source.stat()
    identity = InputFileIdentity(
        label="fixture",
        absolute_path=str(source.resolve()),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        size=metadata.st_size,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    payload = BlindCasePayload(
        question="What is supported?",
        history=(),
        rubric=BlindRubric(
            required_concepts=("scope",),
            forbidden_claims=("certainty",),
            required_limitations=("investigative only",),
        ),
        answer="A scoped conclusion.",
        claims=(BlindClaim(claim_id="claim-1", text="Scoped conclusion"),),
        supports=(),
        local_source_context=(),
    )
    case = ImportedReviewCase(
        case_id="case-001",
        payload=payload,
        payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
        source_id_sha256s=(),
    )
    return _build_suite(
        suite_kind="semantic_holdout",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256="d" * 64,
        input_files=(identity,),
        cases=(case,),
    )


def _recipe(tmp_path: Path) -> ReviewInputRecipe:
    return ReviewInputRecipe(
        suite_kind="semantic_holdout",
        private_holdout_payload=str((tmp_path / "private.json").absolute()),
        holdout_manifest=str((tmp_path / "manifest.json").absolute()),
        holdout_candidate_report=str((tmp_path / "candidate.json").absolute()),
    )


def test_prepare_and_resume_keep_capabilities_private_and_actor_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _suite(tmp_path)
    monkeypatch.setattr(preparation, "import_review_suite", lambda _recipe: suite)
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text("protocol: frozen\n", encoding="utf-8")
    workspace = tmp_path / "workspace"

    coordinator, paths = prepare_review_session(
        workspace,
        session_id="prepared-session-001",
        review_kind="semantic",
        input_recipe=_recipe(tmp_path),
        protocol_path=protocol,
        reviewer_a_name="Alice Reviewer",
        reviewer_b_name="Bob Reviewer",
        adjudicator_name="Casey Adjudicator",
        allowed_origin="http://127.0.0.1:8765",
        clock=lambda: START,
    )

    assert coordinator.progress("reviewer-a").actor_id == "reviewer-a"
    assert set(paths) == {"reviewer-a", "reviewer-b", "adjudicator"}
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths.values())
    assert all("token" not in path.name for path in paths.values())

    resumed, launch, tokens = resume_prepared_review(workspace)
    assert resumed.session == coordinator.session
    assert launch.qualification_eligible is False
    assert len(set(tokens.values())) == 3
    assert all(len(value) >= 43 for value in tokens.values())
    create_review_workspace_app(
        resumed,
        actor_tokens=tokens,
        allowed_origins=(launch.allowed_origin,),
    )


def test_resume_rejects_altered_actor_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _suite(tmp_path)
    monkeypatch.setattr(preparation, "import_review_suite", lambda _recipe: suite)
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text("protocol: frozen\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    _, paths = prepare_review_session(
        workspace,
        session_id="prepared-session-002",
        review_kind="semantic",
        input_recipe=_recipe(tmp_path),
        protocol_path=protocol,
        reviewer_a_name="Alice Reviewer",
        reviewer_b_name="Bob Reviewer",
        adjudicator_name="Casey Adjudicator",
        allowed_origin="http://127.0.0.1:8765",
        clock=lambda: START,
    )
    paths["reviewer-a"].write_bytes(paths["reviewer-a"].read_bytes() + b" ")

    with pytest.raises(ValueError, match="canonical"):
        resume_prepared_review(workspace)


def test_recipe_refuses_cross_kind_and_relative_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="paths"):
        ReviewInputRecipe(
            suite_kind="retrieval",
            conversation_report=str((tmp_path / "report.json").absolute()),
        )
    with pytest.raises(ValueError, match="absolute"):
        ReviewInputRecipe(
            suite_kind="conversation",
            conversation_report="relative-report.json",
        )


@pytest.mark.parametrize("invalid_name", ["Reviewer A", "ChatGPT", "GPT-5.6"])
def test_prepare_refuses_placeholder_or_model_reviewer_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_name: str,
) -> None:
    suite = _suite(tmp_path)
    monkeypatch.setattr(preparation, "import_review_suite", lambda _recipe: suite)
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text("protocol: frozen\n", encoding="utf-8")

    with pytest.raises(ValueError, match="named human"):
        prepare_review_session(
            tmp_path / "workspace",
            session_id="prepared-session-invalid-name",
            review_kind="semantic",
            input_recipe=_recipe(tmp_path),
            protocol_path=protocol,
            reviewer_a_name=invalid_name,
            reviewer_b_name="Bob Reviewer",
            adjudicator_name="Casey Adjudicator",
            allowed_origin="http://127.0.0.1:8765",
            clock=lambda: START,
        )


def test_prepare_requires_three_distinct_humans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _suite(tmp_path)
    monkeypatch.setattr(preparation, "import_review_suite", lambda _recipe: suite)
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text("protocol: frozen\n", encoding="utf-8")

    with pytest.raises(ValueError, match="three distinct"):
        prepare_review_session(
            tmp_path / "workspace",
            session_id="prepared-session-duplicate-name",
            review_kind="semantic",
            input_recipe=_recipe(tmp_path),
            protocol_path=protocol,
            reviewer_a_name="Alice Reviewer",
            reviewer_b_name="alice reviewer",
            adjudicator_name="Casey Adjudicator",
            allowed_origin="http://127.0.0.1:8765",
            clock=lambda: START,
        )
