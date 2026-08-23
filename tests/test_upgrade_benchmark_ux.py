from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_ux_sampling_share_delta_boundary_is_inclusive() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(before, "ux_participant_count", 20)
    _set_snapshot_metric(after, "ux_participant_count", 20)
    common = {
        "status": "complete",
        "participant_count": 20,
        "access_method_counts": {
            "keyboard": 1,
            "pointer": 18,
            "screen_reader": 1,
        },
        "access_method_shares": {
            "keyboard": 0.05,
            "pointer": 0.9,
            "screen_reader": 0.05,
        },
    }
    before["ux"] = {
        **before["ux"],
        **common,
        "cohort_counts": {"novice_bc_resident": 10, "wildfire_aware": 10},
        "cohort_shares": {"novice_bc_resident": 0.5, "wildfire_aware": 0.5},
        "device_class_counts": {"desktop": 10, "mobile": 10},
        "device_class_shares": {"desktop": 0.5, "mobile": 0.5},
    }
    after["ux"] = {
        **after["ux"],
        **common,
        "cohort_counts": {"novice_bc_resident": 13, "wildfire_aware": 7},
        "cohort_shares": {"novice_bc_resident": 0.65, "wildfire_aware": 0.35},
        "device_class_counts": {"desktop": 7, "mobile": 13},
        "device_class_shares": {"desktop": 0.35, "mobile": 0.65},
    }

    comparison = compare_snapshots(before, after, spec)

    sampling = comparison["comparability"]["ux_sampling"]
    assert sampling["maximum_observed_share_delta"] == pytest.approx(0.15)
    assert sampling["passed"] is True
    assert comparison["summary"]["benchmark_gate_passed"] is True


def test_ux_sampling_distribution_shift_fails_the_comparison_gate() -> None:
    spec = load_spec(SPEC_PATH)
    before, after = _passing_snapshots()
    _set_snapshot_metric(after, "ux_participant_count", 12)
    after["ux"] = {
        **after["ux"],
        "cohort_counts": {"novice_bc_resident": 4, "wildfire_aware": 8},
        "cohort_shares": {"novice_bc_resident": 1 / 3, "wildfire_aware": 2 / 3},
        "device_class_counts": {"desktop": 6, "mobile": 6},
        "device_class_shares": {"desktop": 0.5, "mobile": 0.5},
        "access_method_counts": {
            "keyboard": 1,
            "pointer": 10,
            "screen_reader": 1,
        },
        "access_method_shares": {
            "keyboard": 1 / 12,
            "pointer": 10 / 12,
            "screen_reader": 1 / 12,
        },
        "participant_count": 12,
    }

    comparison = compare_snapshots(before, after, spec)

    sampling = comparison["comparability"]["ux_sampling"]
    assert sampling["passed"] is False
    assert sampling["maximum_observed_share_delta"] == pytest.approx(1 / 6)
    assert comparison["summary"]["comparability_failures"] == ["ux_sampling"]
    assert comparison["summary"]["benchmark_gate_passed"] is False


def test_ux_parser_accepts_complete_accessible_task_coverage() -> None:
    parsed = _ux(_ux_report(), load_spec(SPEC_PATH))

    assert parsed["status"] == "complete"
    assert parsed["participant_count"] == 12
    assert parsed["attempts"] == 60
    assert parsed["task_completion_rate"] == 1.0
    assert parsed["accessibility_coverage"] is True
    assert parsed["cohort_counts"] == {
        "novice_bc_resident": 4,
        "wildfire_aware": 8,
    }
    assert parsed["device_class_shares"] == {"desktop": 0.5, "mobile": 0.5}
    assert parsed["access_method_counts"] == {
        "keyboard": 1,
        "pointer": 6,
        "screen_reader": 1,
        "touch": 6,
    }
    assert parsed["completion_by_cohort"] == {
        "novice_bc_resident": 1.0,
        "wildfire_aware": 1.0,
    }
    assert parsed["completion_by_device_class"] == {"desktop": 1.0, "mobile": 1.0}
    assert parsed["completion_by_access_method"] == {
        "keyboard": 1.0,
        "pointer": 1.0,
        "screen_reader": 1.0,
        "touch": 1.0,
    }
    assert parsed["worst_core_cohort_completion_rate"] == 1.0
    assert parsed["worst_device_class_completion_rate"] == 1.0
    assert parsed["completion_wilson_95ci"]["lower"] < 1.0
    assert parsed["bootstrap"]["resamples"] == 2_000


def test_ux_template_is_reviewer_ready_without_fabricated_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "ux.template.yaml"
    upgrade_benchmark._write_ux_template(path, "before", load_spec(SPEC_PATH))
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert payload["participant_count"] == 12
    assert len(payload["participants"]) == 12
    assert len(payload["attempts"]) == 60
    assert {row["cohort"] for row in payload["participants"]} == {
        "novice_bc_resident",
        "wildfire_aware",
    }
    assert {row["device_class"] for row in payload["participants"]} == {
        "desktop",
        "mobile",
    }
    assert {"keyboard", "screen_reader"}.issubset(
        {method for row in payload["participants"] for method in row["access_methods"]}
    )
    assert all(
        all(value is None for value in row["criterion_results"].values())
        for row in payload["attempts"]
    )
    assert all(row["observed_outcome"] == "" for row in payload["attempts"])

    payload["commit"] = "a" * 40
    payload["deployment_id"] = "local-before"
    payload["moderator"] = "Morgan Lee"
    payload["observed_at"] = "2026-08-08T12:00:00+00:00"
    with pytest.raises(ValueError, match="strict booleans"):
        _ux(payload, load_spec(SPEC_PATH))


def test_ux_parser_rejects_an_eleven_person_pilot_even_with_a_constraint_note() -> None:
    report = _ux_report()
    removed_id = report["participants"].pop()["participant_id"]
    report["attempts"] = [
        row for row in report["attempts"] if row["participant_id"] != removed_id
    ]
    report["participant_count"] = 11
    report["recruitment_constraint"] = "One participant was unavailable."

    with pytest.raises(ValueError, match="at least 12"):
        _ux(report, load_spec(SPEC_PATH))

    participant_metric = next(
        metric
        for metric in load_spec(SPEC_PATH).comparison_metrics
        if metric.key == "ux_participant_count"
    )
    assert participant_metric.gate_value == 12


def test_ux_parser_requires_every_participant_task_pair() -> None:
    report = _ux_report()
    report["attempts"].pop()

    with pytest.raises(ValueError, match="every UX participant"):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_binds_the_report_to_the_frozen_task_wording() -> None:
    report = _ux_report()
    report["task_reference"][0]["name"] = "A substituted task"

    with pytest.raises(ValueError, match="task reference|frozen task"):
        _ux(report, load_spec(SPEC_PATH))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("moderator", "UX Researcher", "named human"),
        ("commit", "short-sha", "full lowercase Git SHA"),
        ("deployment_id", "", "deployment ID"),
        ("observed_at", "not-a-timestamp", "timestamp"),
    ],
)
def test_ux_parser_requires_attributable_exact_candidate_evidence(
    field: str, value: str, message: str
) -> None:
    report = _ux_report()
    report[field] = value

    with pytest.raises(ValueError, match=message):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_rejects_hidden_or_task_inapplicable_fields() -> None:
    report = _ux_report()
    report["copied_summary"] = {"task_completion_rate": 1.0}
    with pytest.raises(ValueError, match="canonical schema"):
        _ux(report, load_spec(SPEC_PATH))

    report = _ux_report()
    report["attempts"][2]["copied_completion"] = True
    with pytest.raises(ValueError, match="canonical schema"):
        _ux(report, load_spec(SPEC_PATH))


@pytest.mark.parametrize(
    ("participant_index", "field", "value", "message"),
    [
        (3, "cohort", "wildfire_aware", "four participants"),
        (0, "access_methods", ["touch"], "keyboard and screen-reader"),
    ],
)
def test_ux_parser_rejects_inadequate_sampling_coverage(
    participant_index: int, field: str, value: str, message: str
) -> None:
    report = _ux_report()
    report["participants"][participant_index][field] = value

    with pytest.raises(ValueError, match=message):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_parser_requires_three_participants_per_core_device_class() -> None:
    report = _ux_report()
    report["participants"][4]["device_class"] = "desktop"
    report["participants"][6]["device_class"] = "desktop"
    report["participants"][8]["device_class"] = "desktop"
    report["participants"][10]["device_class"] = "desktop"

    with pytest.raises(ValueError, match="three mobile"):
        _ux(report, load_spec(SPEC_PATH))


def test_ux_completion_is_derived_and_unsuccessful_near_me_uses_task_cap() -> None:
    report = _ux_report()
    for row in report["attempts"]:
        if row["task_id"] == "UX02":
            row["criterion_results"]["UX02-C01"] = False
            row["duration_seconds"] = 1.0

    parsed = _ux(report, load_spec(SPEC_PATH))

    assert parsed["completed"] == 48
    assert parsed["task_completion_rate"] == 0.8
    assert parsed["completion_by_task"]["UX02"] == 0.0
    assert parsed["near_me_median_seconds"] == 120.0


def test_ux_critical_error_codes_override_completed_criteria() -> None:
    report = _ux_report()
    row = report["attempts"][0]
    row["critical_error_codes"] = ["UX01-E01"]
    row["critical_error_notes"] = {
        "UX01-E01": "Participant treated unsupported wording as source-backed."
    }

    parsed = _ux(report, load_spec(SPEC_PATH))

    assert parsed["critical_error_count"] == 1
    assert parsed["completed"] == 59


def test_ux_comparison_reports_seeded_independent_cohort_effect_intervals() -> None:
    spec = load_spec(SPEC_PATH)
    before = _ux(_ux_report(), spec)
    after_report = _ux_report()
    after_report["label"] = "after"
    after_report["commit"] = "b" * 40
    for row in after_report["attempts"]:
        if row["task_id"] == "UX02":
            row["duration_seconds"] = 15.0
    after = _ux(after_report, spec)

    comparison = upgrade_benchmark._ux_distribution_comparability(before, after)
    effects = comparison["effect_intervals"]

    assert comparison["passed"] is True
    assert effects["status"] == "complete"
    assert effects["resamples"] == 5_000
    assert effects["near_me_improvement_established"] is True
    assert effects["near_me_seconds_improvement_95ci"] == {"lower": 15.0, "upper": 15.0}
