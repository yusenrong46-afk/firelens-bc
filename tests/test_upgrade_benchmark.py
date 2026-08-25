from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_v3_authoring_protocol_freezes_required_case_mix() -> None:
    protocol = yaml.safe_load(V3_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert protocol["status"] == "authoring_not_started"
    assert protocol["case_count"] == 47
    assert protocol["composition"] == {
        "single_source": 24,
        "multi_source_or_aspect": 8,
        "negation_or_false_premise": 5,
        "authority_temporal_or_freshness": 5,
        "paraphrase_quantity_or_condition": 5,
    }
    assert sum(protocol["composition"].values()) == protocol["case_count"]
    assert protocol["minimum_safety_sensitive_cases"] == 16
    assert len(protocol["required_source_families"]) == 6
    assert protocol["review"] == {
        "independent_reviewers": 2,
        "adjudicator_required": True,
        "review_must_finish_before_ranking": True,
        "external_hash_anchor_required": True,
    }
    assert protocol["qualification"]["repetitions"] == 3


def test_spec_is_v2_provisional_and_registry_roles_are_valid() -> None:
    spec = load_spec(SPEC_PATH)
    registry = load_dataset_role_registry(ROOT / spec.dataset_role_registry)

    assert spec.schema_version == "firelens_upgrade_benchmark_spec.v2"
    assert spec.frozen_before_upgrade is False
    assert spec.dataset_role_registry in spec.identity_inputs
    assert "data/evaluation/frontend_surface.v1.yaml" in spec.identity_inputs
    assert "data/evaluation/frontend_manual_review.v1.yaml" in spec.identity_inputs
    assert "config/runtime_artifact_allowlist.v1.json" in spec.identity_inputs
    assert "scripts/upgrade_benchmark.py" in spec.harness_inputs
    assert {
        "src/firelens/evaluation/capture.py",
        "src/firelens/evaluation/common.py",
        "src/firelens/evaluation/comparison.py",
        "src/firelens/evaluation/environment.py",
        "src/firelens/evaluation/frontend_browser.py",
        "src/firelens/evaluation/frontend_map.py",
        "src/firelens/evaluation/frontend_manual_protocol.py",
        "src/firelens/evaluation/frontend_manual_review.py",
        "src/firelens/evaluation/frontend_manual_setup.py",
        "src/firelens/evaluation/frontend_privacy.py",
        "src/firelens/evaluation/frontend_protocol.py",
        "src/firelens/evaluation/frontend_qualification.py",
        "src/firelens/evaluation/frontend_surface.py",
        "src/firelens/evaluation/git_evidence.py",
        "src/firelens/evaluation/hard_probe_cli.py",
        "src/firelens/evaluation/live_qualification_cli.py",
        "src/firelens/evaluation/live_slo_evidence_cli.py",
        "src/firelens/evaluation/limitation_cases.py",
        "src/firelens/evaluation/limitation_cli.py",
        "src/firelens/evaluation/limitation_runtime.py",
        "src/firelens/evaluation/preview_qualification_cli.py",
        "src/firelens/evaluation/preview_raw_evidence.py",
        "src/firelens/evaluation/qualification_reports.py",
        "src/firelens/evaluation/release_surfaces.py",
        "src/firelens/evaluation/retrieval.py",
        "src/firelens/evaluation/runtime_artifact.py",
        "src/firelens/evaluation/semantic_holdout.py",
        "src/firelens/evaluation/semantic_holdout_freeze_cli.py",
        "src/firelens/evaluation/semantic_holdout_freeze_support.py",
        "src/firelens/evaluation/semantic_inputs.py",
        "src/firelens/evaluation/semantic_review.py",
        "src/firelens/evaluation/seal.py",
        "src/firelens/evaluation/snapshot.py",
        "src/firelens/evaluation/specification.py",
        "src/firelens/evaluation/ux.py",
        "src/firelens/evaluation/upgrade_cli.py",
    }.issubset(spec.harness_inputs)
    assert {
        "src/firelens/benchmark.py",
        "src/firelens/benchmark_contracts.py",
        "src/firelens/benchmark_retrieval.py",
        "src/firelens/benchmark_support.py",
    }.issubset(spec.harness_inputs)
    assert "src/firelens/review_workspace/input_common.py" in spec.harness_inputs
    assert "src/firelens/review_workspace/input_semantic.py" in spec.harness_inputs
    assert "src/firelens/git_identity.py" in spec.harness_inputs
    assert "src/firelens/document_context.py" in spec.harness_inputs
    assert {
        "src/firelens/review_workspace/cli.py",
        "src/firelens/review_workspace/session.py",
        "src/firelens/review_workspace/session_common.py",
        "src/firelens/review_workspace/session_evidence.py",
        "src/firelens/review_workspace/session_journal.py",
    }.issubset(spec.harness_inputs)
    assert "src/firelens/runtime_artifact.py" in spec.harness_inputs
    assert {
        "src/firelens/runtime_artifact_closure.py",
        "src/firelens/runtime_artifact_common.py",
        "src/firelens/runtime_artifact_comparison.py",
        "src/firelens/runtime_artifact_files.py",
        "src/firelens/runtime_artifact_candidate.py",
    }.issubset(spec.harness_inputs)
    assert "tests/test_runtime_artifact.py" in spec.harness_inputs
    assert "tests/test_limitation_probe.py" in spec.harness_inputs
    assert "tests/test_upgrade_benchmark.py" in spec.harness_inputs
    assert "apps/web/scripts/qualify-frontend-surface.mjs" in spec.harness_inputs
    assert len(spec.comparison_metrics) == len(
        {metric.key for metric in spec.comparison_metrics}
    )
    assert {task.id for task in spec.ux_tasks} == {
        "UX01",
        "UX02",
        "UX03",
        "UX04",
        "UX05",
    }
    manual_metrics = {
        metric.key: metric
        for metric in spec.comparison_metrics
        if metric.key.startswith("frontend_manual_")
    }
    assert set(manual_metrics) == {
        "frontend_manual_accessibility_qualified",
        "frontend_manual_product_safety_qualified",
        "frontend_manual_open_findings",
    }
    assert all(metric.comparison_mode == "after_only" for metric in manual_metrics.values())
    runtime_metrics = {
        metric.key: metric
        for metric in spec.comparison_metrics
        if metric.key.startswith("runtime_artifact_")
    }
    assert set(runtime_metrics) == {
        "runtime_artifact_qualified",
        "runtime_artifact_missing_required_count",
        "runtime_artifact_prohibited_count",
        "runtime_artifact_identity_match",
        "runtime_artifact_candidate_commit_match",
    }
    assert all(metric.comparison_mode == "after_only" for metric in runtime_metrics.values())

    sealed = [
        dataset
        for dataset in registry.datasets
        if dataset.role == "sealed_release_qualification"
    ]
    assert sealed == []
    v2 = next(dataset for dataset in registry.datasets if dataset.id.endswith("v2"))
    assert v2.role == "permanent_regression"
    assert v2.baseline_policy == "paired"
    v3 = next(dataset for dataset in registry.datasets if dataset.id.endswith("v3"))
    assert v3.role == "planned_sealed_qualification"
    assert v3.status == "planned"
    assert all(
        (ROOT / relative).is_file()
        for dataset in registry.datasets
        if dataset.status == "available"
        for relative in dataset.inputs
    )


def test_registry_rejects_unsafe_sealed_policy(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    sealed = next(
        dataset
        for dataset in source["datasets"]
        if dataset["id"] == "benchmark_v1_5_2_sealed_retrieval_v3"
    )
    sealed["role"] = "sealed_release_qualification"
    sealed["status"] = "available"
    sealed["inputs"] = [
        "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
        "data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json",
    ]
    sealed["prohibited_uses"].remove("tuning")
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required prohibitions"):
        load_dataset_role_registry(path)


def test_registry_rejects_planned_sealed_status_only_promotion(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    planned = next(
        dataset
        for dataset in source["datasets"]
        if dataset["role"] == "planned_sealed_qualification"
    )
    planned["status"] = "available"
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot become available without role conversion"):
        load_dataset_role_registry(path)


def test_registry_rejects_after_only_data_disguised_as_development(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    sealed = next(
        dataset
        for dataset in source["datasets"]
        if dataset["id"] == "benchmark_v1_5_2_sealed_retrieval_v3"
    )
    sealed["status"] = "available"
    sealed["role"] = "development"
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="must use the sealed release role"):
        load_dataset_role_registry(path)


def test_spec_requires_registry_in_frozen_identity(tmp_path: Path) -> None:
    source = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    source["identity_inputs"].remove(source["dataset_role_registry"])
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a frozen identity input"):
        load_spec(path)


def test_spec_rejects_missing_harness_input(tmp_path: Path) -> None:
    source = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    source["harness_inputs"].append("scripts/does_not_exist.py")
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="benchmark input does not exist"):
        load_spec(path)


def test_passing_v2_snapshots_pass_the_benchmark_gate() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()

    comparison = compare_snapshots(before, after, spec)

    assert comparison["schema_version"] == "firelens_upgrade_benchmark_comparison.v2"
    assert comparison["summary"]["benchmark_gate_passed"] is True
    assert comparison["summary"]["missing_required_before"] == []
    assert comparison["summary"]["missing_required_after"] == []
    assert comparison["summary"]["comparability_failures"] == []
    assert comparison["comparability"]["execution_environment"]["passed"] is True
    assert comparison["comparability"]["ux_sampling"]["passed"] is True


def test_compare_recomputes_and_records_before_seal_ancestry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    before, after = _passing_snapshots()
    before["identity"]["spec_sha256"] = upgrade_benchmark.file_sha256(SPEC_PATH)
    before["identity"]["identity_input_sha256"] = {
        relative: upgrade_benchmark.file_sha256(ROOT / relative)
        for relative in spec.identity_inputs
    }
    before["identity"]["harness_input_sha256"] = {
        relative: upgrade_benchmark.file_sha256(ROOT / relative)
        for relative in spec.harness_inputs
    }
    after["identity"] = {
        **before["identity"],
        "commit": "c" * 40,
        "candidate_id": f"firelens-v1-5-2:{'c' * 40}",
    }
    after["runtime_artifact"] = _runtime_artifact_snapshot_fixture(after["identity"])
    _sync_runtime_artifact_commitments(after)
    ancestry = {
        "status": "verified",
        "seal_path": spec.before_snapshot_seal,
        "seal_sha256": "d" * 64,
        "before_candidate_commit": "a" * 40,
        "seal_introducing_commit": "b" * 40,
        "after_candidate_commit": "c" * 40,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }
    after["before_snapshot_ancestry"] = ancestry
    after_path = tmp_path / "after.json"
    output_json = tmp_path / "comparison.json"
    output_markdown = tmp_path / "comparison.md"
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: spec)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: before,
    )
    monkeypatch.setattr(upgrade_benchmark, "_read_report", lambda path: after)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: ancestry,
    )

    result = upgrade_benchmark.compare(
        SimpleNamespace(
            spec=SPEC_PATH,
            before=tmp_path / "before.json",
            after=after_path,
            output_json=output_json,
            output_markdown=output_markdown,
        )
    )

    assert result == 0
    persisted = json.loads(output_json.read_text(encoding="utf-8"))
    assert persisted["before_snapshot_ancestry"] == ancestry
    assert ancestry["seal_introducing_commit"] in output_markdown.read_text(encoding="utf-8")


def test_compare_rejects_tampered_after_ancestry_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = load_spec(SPEC_PATH).model_copy(update={"frozen_before_upgrade": True})
    before, after = _passing_snapshots()
    after["before_snapshot_ancestry"] = {"seal_introducing_commit": "wrong"}
    recomputed = {"seal_introducing_commit": "b" * 40}
    monkeypatch.setattr(upgrade_benchmark, "load_spec", lambda path: spec)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_verify_tracked_before_snapshot_seal",
        lambda **kwargs: before,
    )
    monkeypatch.setattr(upgrade_benchmark, "_read_report", lambda path: after)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_resolve_before_snapshot_ancestry",
        lambda **kwargs: recomputed,
    )

    with pytest.raises(ValueError, match="differs from recomputed Git history"):
        upgrade_benchmark.compare(
            SimpleNamespace(
                spec=SPEC_PATH,
                before=tmp_path / "before.json",
                after=tmp_path / "after.json",
                output_json=tmp_path / "comparison.json",
                output_markdown=tmp_path / "comparison.md",
            )
        )


def test_paired_tolerance_boundary_is_inclusive_and_beyond_is_regression() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "frontend_initial_route_js_gzip_bytes"
    _set_snapshot_metric(before, key, 70_000)
    _set_snapshot_metric(after, key, 72_100)

    at_boundary = compare_snapshots(before, after, spec)
    boundary_row = next(row for row in at_boundary["metrics"] if row["key"] == key)
    assert boundary_row["verdict"] == "within_tolerance"
    assert boundary_row["comparison_requirement_passed"] is True

    _set_snapshot_metric(after, key, 72_101)
    beyond = compare_snapshots(before, after, spec)
    beyond_row = next(row for row in beyond["metrics"] if row["key"] == key)
    assert beyond_row["verdict"] == "regressed"
    assert beyond_row["comparison_requirement_passed"] is False
    assert key in beyond["summary"]["regressions"]
    assert beyond["summary"]["benchmark_gate_passed"] is False


def test_exact_ratified_required_improvement_counts_as_improved() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "ux_near_me_median_seconds"
    _set_snapshot_metric(before, key, 40.0)
    _set_snapshot_metric(after, key, 30.0)

    comparison = compare_snapshots(before, after, spec)
    row = next(row for row in comparison["metrics"] if row["key"] == key)

    assert row["verdict"] == "improved"
    assert row["comparison_requirement_passed"] is True
    assert key not in comparison["summary"]["insufficient_improvement"]


def test_missing_paired_before_value_fails_closed() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    key = "development_retrieval_recall_at_5"
    _set_snapshot_metric(before, key, None)

    comparison = compare_snapshots(before, after, spec)
    row = next(row for row in comparison["metrics"] if row["key"] == key)

    assert row["verdict"] == "not_measured"
    assert row["comparison_requirement_passed"] is False
    assert comparison["summary"]["missing_required_before"] == [key]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_after_only_metric_forbids_any_before_value() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(before, "sealed_retrieval_qualified", False)

    with pytest.raises(
        ValueError,
        match="after-only metric sealed_retrieval_qualified must not have a before value",
    ):
        compare_snapshots(before, after, spec)


@pytest.mark.parametrize(
    ("key", "invalid", "message"),
    [
        ("verification_passed", 1, "strict boolean"),
        ("offline_hard_probe_critical_failures", 0.0, "must be an integer"),
        ("offline_hard_probe_pass_rate", "1.0", "must be numeric"),
        ("offline_hard_probe_pass_rate", math.nan, "must be finite"),
    ],
)
def test_metric_values_are_strictly_typed(key: str, invalid: object, message: str) -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["metrics"][key] = invalid

    with pytest.raises(ValueError, match=message):
        compare_snapshots(before, after, spec)


def test_comparison_recomputes_metrics_and_rejects_stored_divergence() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["metrics"]["offline_hard_probe_pass_rate"] = 0.5

    with pytest.raises(ValueError, match="diverges from its detailed evidence"):
        compare_snapshots(before, after, spec)


def test_missing_review_is_not_misreported_as_zero_approval() -> None:
    summary = _review(
        None,
        expected_cases=50,
        expected_summary_version="firelens_owner_semantic_review_summary.v1",
    )

    assert summary == {
        "status": "missing",
        "case_count": 50,
        "approved_case_count": None,
        "approval_rate": None,
        "qualified": None,
    }


def test_recomputed_review_summary_rejects_aggregate_substitution() -> None:
    recomputed = {
        "summary_version": "firelens_owner_semantic_review_summary.v1",
        "generated_at": "2026-08-06T01:00:00+00:00",
        "case_count": 50,
        "approved_case_count": 49,
        "qualified": False,
        "cases": [{"case_id": "case-1", "approved": False}],
    }
    submitted = {
        **recomputed,
        "generated_at": "2026-08-06T02:00:00+00:00",
        "approved_case_count": 50,
        "qualified": True,
    }

    with pytest.raises(ValueError, match="differs from raw validated evidence"):
        _assert_recomputed_summary_matches(submitted, recomputed, context="semantic review")

    submitted = {**recomputed, "generated_at": "2026-08-06T02:00:00+00:00"}
    _assert_recomputed_summary_matches(submitted, recomputed, context="semantic review")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("summary_version", "wrong.v1", "unsupported summary_version"),
        ("case_count", 49, "exactly 50 cases"),
        ("expected_case_count_present", False, "exactly 50 cases"),
        ("reviewer_present", False, "named reviewer and review timestamp"),
        ("reviewed_at_present", False, "named reviewer and review timestamp"),
        ("qualified", 1, "strict boolean"),
    ],
)
def test_partial_review_summary_is_rejected(field: str, value: object, message: str) -> None:
    report = {
        "summary_version": "firelens_owner_semantic_review_summary.v1",
        "case_count": 50,
        "approved_case_count": 50,
        "expected_case_count_present": True,
        "reviewer_present": True,
        "reviewed_at_present": True,
        "qualified": True,
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
    }
    report[field] = value

    with pytest.raises(ValueError, match=message):
        _review(
            report,
            expected_cases=50,
            expected_summary_version="firelens_owner_semantic_review_summary.v1",
        )


def test_cpu_identity_prefers_the_same_node_source_as_frontend_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upgrade_benchmark.platform, "processor", lambda: "arm")
    monkeypatch.setattr(
        upgrade_benchmark,
        "_command_version",
        lambda command: "Apple M5" if command[0] == "node" else "unavailable",
    )

    assert upgrade_benchmark._cpu_model() == "Apple M5"


def test_comparison_fails_closed_on_changed_frozen_inputs() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["identity"]["identity_input_sha256"] = {"dataset.yaml": "d" * 64}

    with pytest.raises(ValueError, match="different frozen evaluation inputs"):
        compare_snapshots(before, after, spec)


def test_comparison_fails_closed_on_changed_harness_hashes() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after["identity"]["harness_input_sha256"] = {"harness.py": "d" * 64}

    with pytest.raises(ValueError, match="different benchmark harnesses"):
        compare_snapshots(before, after, spec)


def test_comparison_gate_requires_the_same_execution_environment() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    after_environment = dict(after["identity"]["execution_environment"])
    after_environment["node_version"] = "v24.0.0"
    after["identity"]["execution_environment"] = after_environment

    comparison = compare_snapshots(before, after, spec)

    environment = comparison["comparability"]["execution_environment"]
    assert environment["passed"] is False
    assert environment["differing_fields"] == ["node_version"]
    assert comparison["summary"]["comparability_failures"] == ["execution_environment"]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_comparison_gate_requires_complete_environment_identity() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    before["identity"].pop("execution_environment")

    comparison = compare_snapshots(before, after, spec)

    assert comparison["comparability"]["execution_environment"]["passed"] is False
    assert "execution_environment" in comparison["summary"]["comparability_failures"]


def test_comparison_gate_rejects_placeholder_environment_identity() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    for snapshot in (before, after):
        environment = dict(snapshot["identity"]["execution_environment"])
        environment["npm_version"] = "unavailable"
        snapshot["identity"]["execution_environment"] = environment

    comparison = compare_snapshots(before, after, spec)

    environment = comparison["comparability"]["execution_environment"]
    assert environment["passed"] is False
    assert environment["differing_fields"] == []
    assert any("invalid" in issue for issue in environment["issues"])
