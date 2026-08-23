from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_prerequisites_do_not_require_before_measurement_but_gate_after() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    prerequisite_keys = {
        metric.key
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "prerequisite"
    }
    for key in prerequisite_keys:
        _set_snapshot_metric(before, key, None)

    passing = compare_snapshots(before, after, spec)
    prerequisite_rows = [row for row in passing["metrics"] if row["key"] in prerequisite_keys]
    assert prerequisite_keys
    assert all(row["verdict"] == "prerequisite" for row in prerequisite_rows)
    assert passing["summary"]["missing_required_before"] == []
    assert passing["summary"]["benchmark_gate_passed"] is True

    missing_key = next(iter(prerequisite_keys))
    _set_snapshot_metric(after, missing_key, None)
    missing = compare_snapshots(before, after, spec)
    assert missing_key in missing["summary"]["missing_required_after"]
    assert missing["summary"]["benchmark_gate_passed"] is False


def test_relevant_untracked_paths_ignore_only_ephemeral_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade_benchmark,
        "_git",
        lambda *args: "\n".join(
            [
                ".agents/local-note.md",
                "output/benchmark.json",
                "scripts/untracked_runtime.py",
                "data/evaluation/untracked.yaml",
            ]
        ),
    )

    assert _relevant_untracked_paths() == [
        "data/evaluation/untracked.yaml",
        "scripts/untracked_runtime.py",
    ]


def test_before_snapshot_seal_binds_snapshot_and_all_frozen_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )

    assert seal["before_snapshot"]["sha256"] == upgrade_benchmark.file_sha256(before_path)
    assert seal["candidate_identity"]["commit"] == "baseline-commit"
    assert seal["spec_identity"]["sha256"] == upgrade_benchmark.file_sha256(spec_path)
    assert (
        seal["dataset_identity"]["identity_input_sha256"]
        == before["identity"]["identity_input_sha256"]
    )
    assert (
        seal["harness_identity"]["harness_input_sha256"]
        == before["identity"]["harness_input_sha256"]
    )
    _verify_before_snapshot_seal_payload(
        seal=seal,
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
    )


def test_before_snapshot_seal_rejects_metric_or_snapshot_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )
    before["metrics"]["offline_hard_probe_pass_rate"] = 0.5
    with pytest.raises(ValueError, match="diverges from its detailed evidence"):
        _verify_before_snapshot_seal_payload(
            seal=seal,
            before=before,
            before_path=before_path,
            spec=spec,
            spec_path=spec_path,
        )

    before["metrics"]["offline_hard_probe_pass_rate"] = before["hard_probe_offline"][
        "pass_rate"
    ]
    before_path.write_text(json.dumps({**before, "tampered": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the supplied snapshot"):
        _verify_before_snapshot_seal_payload(
            seal=seal,
            before=before,
            before_path=before_path,
            spec=spec,
            spec_path=spec_path,
        )


def test_before_snapshot_seal_must_be_tracked_and_unmodified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, spec_path, before, before_path = _seal_test_inputs(tmp_path, monkeypatch)
    seal = _build_before_snapshot_seal(
        before=before,
        before_path=before_path,
        spec=spec,
        spec_path=spec_path,
        owner="Thomas Lee",
        sealed_at="2026-08-06T12:00:00+00:00",
    )
    seal_path = tmp_path / spec.before_snapshot_seal
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    monkeypatch.setattr(
        upgrade_benchmark, "_path_is_tracked_and_unmodified", lambda path: False
    )

    with pytest.raises(ValueError, match="must be tracked and unmodified"):
        upgrade_benchmark._verify_tracked_before_snapshot_seal(
            spec=spec,
            spec_path=spec_path,
            before_path=before_path,
        )


def test_before_snapshot_ancestry_accepts_exact_committed_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    seal_commit = _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)

    evidence = upgrade_benchmark._resolve_before_snapshot_ancestry(
        spec=spec,
        before={"identity": {"commit": before_commit}},
        after_commit=after_commit,
    )

    assert evidence == {
        "status": "verified",
        "seal_path": "data/before-seal.json",
        "seal_sha256": upgrade_benchmark.file_sha256(tmp_path / "data/before-seal.json"),
        "before_candidate_commit": before_commit,
        "seal_introducing_commit": seal_commit,
        "after_candidate_commit": after_commit,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }


def test_before_snapshot_ancestry_rejects_unrelated_before_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, baseline_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    baseline_tree = _repo_git(tmp_path, "rev-parse", f"{baseline_commit}^{{tree}}")
    unrelated_before = _repo_git(
        tmp_path,
        "commit-tree",
        baseline_tree,
        "-m",
        "unrelated baseline",
    )
    _commit_test_seal(tmp_path, unrelated_before)
    after_commit = _commit_after_candidate(tmp_path)

    with pytest.raises(ValueError, match="before snapshot candidate is not an ancestor"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": unrelated_before}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_abbreviated_commit_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    abbreviated = before_commit[:12]
    _commit_test_seal(tmp_path, abbreviated)
    after_commit = _commit_after_candidate(tmp_path)

    with pytest.raises(ValueError, match="exact full Git commit ID"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": abbreviated}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_seal_on_side_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _repo_git(tmp_path, "switch", "--quiet", "-c", "seal-side")
    _commit_test_seal(tmp_path, before_commit)
    _repo_git(tmp_path, "switch", "--quiet", "-c", "after-side", before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    _repo_git(tmp_path, "switch", "--quiet", "seal-side")

    with pytest.raises(ValueError, match="after candidate does not contain"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )


def test_before_snapshot_ancestry_rejects_after_candidate_before_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)

    with pytest.raises(ValueError, match="after candidate does not contain"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=before_commit,
        )


def test_before_snapshot_ancestry_rejects_missing_or_untracked_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    before = {"identity": {"commit": before_commit}}

    with pytest.raises(ValueError, match="seal is missing"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before=before,
            after_commit=before_commit,
        )

    seal_path = tmp_path / "data/before-seal.json"
    seal_path.parent.mkdir(parents=True)
    seal_path.write_text(
        json.dumps({"candidate_identity": {"commit": before_commit}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="is untracked"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before=before,
            after_commit=before_commit,
        )


def test_before_snapshot_ancestry_rejects_mutable_or_ambiguous_seal_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    seal_path = tmp_path / "data/before-seal.json"
    seal_path.write_text(
        json.dumps({"candidate_identity": {"commit": before_commit}, "tampered": True}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unstaged modifications"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    _repo_git(tmp_path, "add", "data/before-seal.json")
    with pytest.raises(ValueError, match="staged modifications"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    _repo_git(tmp_path, "commit", "--quiet", "-m", "rewrite seal")
    rewritten_after = _repo_git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="ambiguous or mutable history"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=rewritten_after,
        )


def test_before_snapshot_ancestry_rejects_shallow_or_failed_git_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, before_commit = _init_ancestry_repo(tmp_path, monkeypatch)
    _commit_test_seal(tmp_path, before_commit)
    after_commit = _commit_after_candidate(tmp_path)
    real_command = upgrade_benchmark._git_evidence_command

    def shallow_command(args: list[str], **kwargs: object) -> object:
        if args == ["rev-parse", "--is-shallow-repository"]:
            return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")
        return real_command(args, **kwargs)

    monkeypatch.setattr(upgrade_benchmark, "_git_evidence_command", shallow_command)
    with pytest.raises(ValueError, match="shallow repository"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    monkeypatch.setattr(upgrade_benchmark, "_git_evidence_command", real_command)

    real_run = upgrade_benchmark.subprocess.run

    def git_failure(*args: object, **kwargs: object) -> object:
        return subprocess.CompletedProcess(args, 128, stdout="", stderr="fatal: broken repo")

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", git_failure)
    with pytest.raises(ValueError, match="failed with exit 128"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", real_run)

    def git_os_error(*args: object, **kwargs: object) -> object:
        raise OSError("git unavailable")

    monkeypatch.setattr(upgrade_benchmark.subprocess, "run", git_os_error)
    with pytest.raises(ValueError, match="Git could not run"):
        upgrade_benchmark._resolve_before_snapshot_ancestry(
            spec=spec,
            before={"identity": {"commit": before_commit}},
            after_commit=after_commit,
        )


def test_capture_rejects_dirty_worktree_before_running_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: True)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before clean preflight"),
    )

    with pytest.raises(ValueError, match="clean tracked worktree"):
        capture(SimpleNamespace(spec=SPEC_PATH))


def test_after_capture_requires_the_sealed_before_snapshot_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before seal preflight"),
    )

    with pytest.raises(ValueError, match="requires the sealed before snapshot"):
        capture(
            SimpleNamespace(
                spec=SPEC_PATH,
                label="after",
                before_snapshot=None,
                rate_limit_evidence=None,
                rollback_evidence=None,
            )
        )


def test_after_capture_rejects_invalid_seal_ancestry_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: {"identity": {"commit": "a" * 40}},
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "c" * 40)

    def reject_ancestry(**kwargs: object) -> object:
        raise ValueError("seal-introducing commit is not an ancestor")

    monkeypatch.setattr(upgrade_benchmark, "_resolve_before_snapshot_ancestry", reject_ancestry)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before ancestry preflight"),
    )

    with pytest.raises(ValueError, match="seal-introducing commit"):
        capture(
            SimpleNamespace(
                spec=SPEC_PATH,
                label="after",
                before_snapshot=Path("before.json"),
            )
        )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "semantic_holdout_report",
        "semantic_holdout_review_bundle",
        "semantic_holdout_summary",
        "frontend_manual_review_bundle",
        "preview_report",
        "deployment_report",
        "rate_limit_evidence",
        "rollback_evidence",
        "vercel_artifact_root",
        "vercel_artifact_id",
        "vercel_platform_root",
        "docker_artifact_root",
        "docker_artifact_id",
        "docker_platform_root",
    ],
)
def test_before_capture_rejects_required_after_only_evidence(
    forbidden_field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    args = {
        "spec": SPEC_PATH,
        "label": "before",
        "retrieval_qualification": None,
        "semantic_holdout_report": None,
        "semantic_holdout_review_bundle": None,
        "semantic_holdout_summary": None,
        "frontend_manual_review_bundle": None,
        "preview_report": None,
        "deployment_report": None,
        "rate_limit_evidence": None,
        "rollback_evidence": None,
        "vercel_artifact_root": None,
        "vercel_artifact_id": None,
        "vercel_platform_root": None,
        "docker_artifact_root": None,
        "docker_artifact_id": None,
        "docker_platform_root": None,
    }
    args[forbidden_field] = Path("evidence.json")

    with pytest.raises(ValueError, match="required-after-only"):
        capture(SimpleNamespace(**args))


def test_after_capture_requires_frontend_manual_review_before_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail(
            "capture command ran before manual-review preflight"
        ),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=None,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match="requires the frontend manual review bundle"):
        capture(args)


@pytest.mark.parametrize(
    ("review_kind", "message"),
    [
        ("semantic", "blind-review qualification manifest"),
        ("retrieval", "blind-review qualification manifest"),
    ],
)
def test_capture_refuses_legacy_human_review_without_blind_qualification_manifest(
    review_kind: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    semantic = review_kind == "semantic"
    retrieval = review_kind == "retrieval"
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="before",
        before_snapshot=None,
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=None,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        vercel_artifact_root=None,
        vercel_artifact_id=None,
        vercel_platform_root=None,
        docker_artifact_root=None,
        docker_artifact_id=None,
        docker_platform_root=None,
        semantic_report=Path("report.json") if semantic else None,
        semantic_review_sidecar=Path("review.yaml") if semantic else None,
        semantic_review_summary=Path("summary.json") if semantic else None,
        semantic_review_qualification=None,
        retrieval_review_sidecar=Path("review.yaml") if retrieval else None,
        retrieval_review_summary=Path("summary.json") if retrieval else None,
        retrieval_review_qualification=None,
    )

    with pytest.raises(ValueError, match=message):
        capture(args)


def test_after_capture_requires_capture_owned_runtime_artifacts_before_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "validate_frontend_manual_review",
        lambda *args, **kwargs: {"status": "complete"},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail(
            "capture command ran before runtime artifact preflight"
        ),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        output_dir=tmp_path / "capture",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=None,
        semantic_holdout_review_bundle=None,
        semantic_holdout_summary=None,
        frontend_manual_review_bundle=tmp_path / "manual.json",
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match="capture-owned Vercel and Docker"):
        capture(args)


@pytest.mark.parametrize(
    ("holdout_report", "review_bundle", "summary", "message"),
    [
        (Path("report.json"), None, None, "requires both"),
        (None, Path("bundle.json"), None, "requires both"),
        (None, None, Path("summary.json"), "summary requires"),
    ],
)
def test_after_capture_rejects_incomplete_semantic_holdout_artifact_sets(
    holdout_report: Path | None,
    review_bundle: Path | None,
    summary: Path | None,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: frozen)
    monkeypatch.setattr(upgrade_benchmark, "_tracked_dirty", lambda: False)
    monkeypatch.setattr(upgrade_benchmark, "_relevant_untracked_paths", lambda: [])
    monkeypatch.setattr(
        upgrade_benchmark, "_verify_tracked_before_snapshot_seal", lambda **kwargs: {}
    )
    monkeypatch.setattr(upgrade_benchmark, "_current_git_commit", lambda **kwargs: "a" * 40)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: {"seal_introducing_commit": "b" * 40},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_run_logged",
        lambda *args, **kwargs: pytest.fail("capture command ran before artifact preflight"),
    )
    args = SimpleNamespace(
        spec=SPEC_PATH,
        label="after",
        before_snapshot=Path("before.json"),
        retrieval_qualification=None,
        semantic_holdout_report=holdout_report,
        semantic_holdout_review_bundle=review_bundle,
        semantic_holdout_summary=summary,
        preview_report=None,
        deployment_report=None,
        rate_limit_evidence=None,
        rollback_evidence=None,
        semantic_report=None,
        semantic_review_sidecar=None,
        semantic_review_qualification=None,
        semantic_review_summary=None,
        retrieval_review_sidecar=None,
        retrieval_review_qualification=None,
        retrieval_review_summary=None,
    )

    with pytest.raises(ValueError, match=message):
        capture(args)
