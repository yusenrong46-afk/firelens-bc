from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import firelens_eval.lab as eval_lab
from firelens.evaluation.claimbench_v2 import evaluate_v2_catalog, load_claimbench_v2
from firelens.evaluation.common import file_sha256
from firelens.evaluation.hard_probe_expectations import (
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    DEFAULT_RC2_2_EXPECTATIONS,
    DEFAULT_RC2_2_EXPECTATIONS_MANIFEST,
    canonical_json_sha256,
    effective_expectations_payload,
    load_dataset,
    load_expectation_profile,
)
from firelens_eval import (
    SUITES,
    compare_runs,
    diagnose_case,
    evaluation_source_identity,
    inventory,
    run_suite,
    source_identity,
    validate_claimbench_report,
    validate_failure_record,
    validate_hard_probe_report,
    validate_run_envelope,
)
from firelens_eval.lab import (
    FAILURE_SCHEMA_RELATIVE,
    POLICY_RELATIVE,
    REGISTRY_RELATIVE,
    RunContext,
    _artifact_eligibility_issues,
    _new_failure,
    eval_lab_source_identity,
    load_policy,
    load_registry,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual_core_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    run_dir = tmp_path_factory.mktemp("actual-core") / "run"
    envelope, observed_dir = run_suite("core", output_dir=run_dir, repository_root=ROOT)
    envelope_path = observed_dir / "envelope.json"
    assert (
        validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT) == []
    )
    return observed_dir


def _copy_actual_core_run(source: Path, destination: Path) -> tuple[Path, dict[str, object]]:
    shutil.copytree(source, destination)
    envelope_path = destination / "envelope.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    for adapter in envelope["adapters"]:
        raw_relative = adapter.get("raw_artifact")
        if isinstance(raw_relative, str):
            adapter["command"] = adapter["command"].replace(
                str(source / raw_relative), str(destination / raw_relative)
            )
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    return envelope_path, envelope


def _run_core_from_checkout(repository: Path, output: Path) -> None:
    program = """
import sys
from pathlib import Path
from firelens_eval import run_suite

run_suite("core", output_dir=Path(sys.argv[1]), repository_root=Path(sys.argv[2]))
"""
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(repository / "src"), str(repository))),
    }
    completed = subprocess.run(
        [sys.executable, "-c", program, str(output), str(repository)],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.fixture(scope="module")
def two_commit_core_runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, str, str]:
    fixture_root = tmp_path_factory.mktemp("two-commit-core")
    repository = fixture_root / "repository"
    repository.mkdir()
    for relative in ("src", "scripts", "data", "config"):
        shutil.copytree(ROOT / relative, repository / relative)
    schema = Path("evals/eval_lab/schema")
    shutil.copytree(ROOT / schema, repository / schema)
    shutil.copy2(ROOT / ".gitignore", repository / ".gitignore")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Eval Test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "eval@example.test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-qm", "base evaluator"], check=True
    )
    base_sha = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    artifact_root = fixture_root / "artifacts"
    _run_core_from_checkout(repository, artifact_root / "base")

    marker = repository / "comparison_marker.txt"
    marker.write_text("application-only change\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "comparison_marker.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-qm", "candidate application"],
        check=True,
    )
    candidate_sha = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    _run_core_from_checkout(repository, artifact_root / "candidate")
    return repository, artifact_root, base_sha, candidate_sha


def _write_core_envelope(
    directory: Path,
    *,
    commit: str,
    finished_at: str,
    failed_ids: list[str] | None = None,
    dirty: bool = False,
) -> Path:
    """Write a complete synthetic core envelope with real evaluator bindings."""

    failed_ids = failed_ids or []
    directory.mkdir(parents=True, exist_ok=True)
    started_at = "2026-09-04T00:00:00+00:00"
    identity = {
        "commit": commit,
        "tree": "c" * 40,
        "branch": "test",
        "dirty": dirty,
        "application_sha": "f" * 64 if dirty else commit,
        "working_tree_status_sha256": "1" * 64,
        "working_tree_sha256": "2" * 64,
        "final_working_tree_status_sha256": "1" * 64,
        "final_working_tree_sha256": "2" * 64,
        "changed_during_run": False,
        "imported_firelens_path": str((ROOT / "src/firelens/__init__.py").resolve()),
        "python_executable": str(Path(sys.executable).resolve()),
    }
    registry = load_registry(ROOT)
    context = RunContext(
        root=ROOT,
        run_dir=directory,
        run_id=directory.name,
        started_at=started_at,
        identity=identity,
        registry=registry,
        policy=load_policy(ROOT),
    )
    failures = [
        _new_failure(
            context,
            suite="core",
            adapter_id="hard_probe_rc2_2",
            case_id=case_id,
            status="FAIL",
            failure_class="hard_probe_case_failure_within_profile",
            severity="HIGH",
            oracle="deterministic_executable",
            summary=f"synthetic failure for {case_id}",
            expected={"passed": True},
            observed={"passed": False},
            evidence=["raw/hard_probe_rc2_2.json"],
            first_divergent_layer="evaluation_contract",
            reproduction=[f"firelens-eval diagnose {case_id}"],
            lifecycle_status="review",
            first_divergence_owner=("data/evaluation/hard_probe_rc2_2_expectations.v1.yaml"),
            first_divergence_confidence="suspected",
        )
        for case_id in failed_ids
    ]
    hard_probe_report = _valid_hard_probe_report()
    hard_probe_rows = hard_probe_report["results"]
    assert isinstance(hard_probe_rows, list)
    unknown_failed_ids = set(failed_ids) - {
        str(row["id"]) for row in hard_probe_rows if isinstance(row, dict)
    }
    if unknown_failed_ids:
        raise ValueError(f"unknown synthetic hard-probe IDs: {sorted(unknown_failed_ids)}")
    for row in hard_probe_rows:
        if isinstance(row, dict) and row["id"] in failed_ids:
            row["passed"] = False
            row["failure_reason"] = "synthetic deterministic failure"
    hard_probe_summary = hard_probe_report["summary"]
    assert isinstance(hard_probe_summary, dict)
    hard_probe_summary.update(
        {
            "passed": len(hard_probe_rows) - len(failed_ids),
            "failed": len(failed_ids),
        }
    )
    reports = {
        "productbench_offline": _valid_productbench_report(),
        "claimbench_v2": _valid_claimbench_report(),
        "hard_probe_rc2_2": hard_probe_report,
        "source_aware_conversation": _valid_source_aware_report(),
    }
    evaluator = evaluation_source_identity(ROOT)
    adapters: list[dict[str, object]] = []
    definitions = registry["suites"]["core"]["adapters"]
    for definition in definitions:
        adapter_id = str(definition["id"])
        adapter_failures = [
            failure for failure in failures if failure["adapter_id"] == adapter_id
        ]
        raw_relative = f"raw/{adapter_id}.json"
        raw_path = directory / raw_relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        report = reports[adapter_id]
        raw_path.write_text(json.dumps(report), encoding="utf-8")
        if adapter_id == "productbench_offline":
            rows = report["results"]
            passed = sum(row["passed"] is True for row in rows)
            expected = 31
            metrics = {
                "execution_complete": report["execution_complete"],
                "cost": report["cost"],
            }
            materials = report["identity"]
        elif adapter_id == "claimbench_v2":
            rows = report["rows"]
            passed = sum(row["correct"] is True for row in rows)
            expected = 332
            metrics = {
                key: report[key]
                for key in (
                    "unsafe_false_accept_rate",
                    "faithful_false_reject_rate",
                    "critical_field_preservation",
                    "always_abstain",
                )
            }
            materials = report["identity"]
        elif adapter_id == "hard_probe_rc2_2":
            rows = report["results"]
            passed = sum(row["passed"] is True for row in rows)
            expected = 105
            summary = report["summary"]
            metrics = {
                "minimum_passed": summary["minimum_passed"],
                "minimum_passed_met": summary["minimum_passed_met"],
                "cost_usd": summary["cost_usd"],
            }
            materials = report["manifest"]
        else:
            rows = report["results"]
            passed = sum(row["passed"] is True for row in rows)
            expected = 106
            metrics = report["metrics"]
            materials = report["artifact_identity"]
        executed = len(rows)
        command_tail = {
            "productbench_offline": (
                f"scripts/run_productbench.py --mode offline --output {raw_path}"
            ),
            "claimbench_v2": "scripts/claimbench_v2.py evaluate",
            "hard_probe_rc2_2": (
                "scripts/run_hard_probe.py --mode offline "
                f"--expectation-profile rc2.2 --output {raw_path}"
            ),
            "source_aware_conversation": (
                f"scripts/run_source_aware_conversation.py --output {raw_path}"
            ),
        }[adapter_id]
        adapters.append(
            {
                "adapter_id": adapter_id,
                "status": "PASS",
                "classification": definition["classification"],
                "oracle": definition["oracle"],
                "command": f"{sys.executable} {command_tail}",
                "started_at": started_at,
                "finished_at": finished_at,
                "raw_artifact": raw_relative,
                "raw_artifact_sha256": file_sha256(raw_path),
                "evaluator": evaluator,
                "case_counts": {
                    "expected": expected,
                    "executed": executed,
                    "passed": passed,
                    "failed": executed - passed,
                    "not_run": max(0, expected - executed),
                },
                "metrics": metrics,
                "materials": materials,
                "failure_ids": [failure["failure_id"] for failure in adapter_failures],
                "limitations": [],
            }
        )
    adapter_states = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
    envelope = {
        "schema_version": "firelens.eval_lab.run.v1",
        "run_id": directory.name,
        "suite": "core",
        "status": "PASS",
        "qualification_role": "zero_cost_engineering_evidence",
        "started_at": started_at,
        "finished_at": finished_at,
        "identity": identity,
        "bindings": {
            "eval_lab": eval_lab_source_identity(ROOT),
            "evaluation_source": evaluator,
            "registry": {
                "path": str(REGISTRY_RELATIVE),
                "sha256": file_sha256(ROOT / REGISTRY_RELATIVE),
            },
            "policy": {
                "path": str(POLICY_RELATIVE),
                "sha256": file_sha256(ROOT / POLICY_RELATIVE),
            },
            "failure_record_schema": {
                "path": str(FAILURE_SCHEMA_RELATIVE),
                "sha256": file_sha256(ROOT / FAILURE_SCHEMA_RELATIVE),
            },
        },
        "execution": {
            "network_allowed": False,
            "provider_calls_allowed": False,
        },
        "adapters": adapters,
        "summary": {
            "adapter_counts": {
                state: sum(adapter["status"] == state for adapter in adapters)
                for state in adapter_states
            },
            "executed_cases": sum(
                int(adapter["case_counts"]["executed"]) for adapter in adapters
            ),
            "passed_cases": sum(int(adapter["case_counts"]["passed"]) for adapter in adapters),
            "failed_cases": sum(int(adapter["case_counts"]["failed"]) for adapter in adapters),
            "failure_records": len(failures),
        },
        "failures": failures,
        "limitations": [],
    }
    envelope_path = directory / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    return envelope_path


def _valid_claimbench_report() -> dict[str, object]:
    report = evaluate_v2_catalog(load_claimbench_v2(ROOT))
    report["schema_version"] = "firelens.claimbench_v2_report.v1"
    identity = source_identity(ROOT)
    report["identity"] = {
        "catalog": {
            "path": "data/evaluation/claimbench_v1_6_2.yaml",
            "sha256": file_sha256(ROOT / "data/evaluation/claimbench_v1_6_2.yaml"),
        },
        "manifest": {
            "path": "data/evaluation/claimbench_v1_6_2.manifest.json",
            "sha256": file_sha256(ROOT / "data/evaluation/claimbench_v1_6_2.manifest.json"),
        },
        "commit": identity["commit"],
        "tree": identity["tree"],
    }
    return report


def _valid_productbench_report() -> dict[str, object]:
    manifest_path = ROOT / "data/evaluation/productbench_v2.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_ids = manifest["tiers"]["offline_fake"]
    identity = source_identity(ROOT)
    return {
        "schema_version": "firelens.productbench_report.v2",
        "results": [{"id": case_id, "passed": True, "issues": []} for case_id in case_ids],
        "case_count": len(case_ids),
        "passed": len(case_ids),
        "failed": 0,
        "execution_complete": True,
        "identity": {
            "tier": "offline_fake",
            "raw_catalog_sha256": file_sha256(
                ROOT / "data/evaluation/productbench_journeys_50.json"
            ),
            "manifest_sha256": file_sha256(manifest_path),
            "commit": identity["commit"],
            "tree": identity["tree"],
        },
        "cost": {
            "max_cost_usd": 0.0,
            "reported_cost_usd": 0.0,
            "ceiling_exceeded": False,
        },
        "provider_boundary": "offline_fake",
    }


def _valid_source_aware_report() -> dict[str, object]:
    manifest_path = ROOT / "data/evaluation/source_aware_conversation.v1.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total = int(manifest["total_case_count"])
    identity = source_identity(ROOT)
    return {
        "schema_version": "firelens.source_aware_conversation.report.v1",
        "passed": True,
        "case_counts": {"total": total},
        "metrics": {
            "passed": total,
            "failed": 0,
            "tier_a_b_generation_calls": 0,
            "tier_a_b_generation_cost_usd": 0.0,
        },
        "execution": {
            "external_network_calls": 0,
            "external_model_calls": 0,
            "provider_boundary": "fake_provider_only",
        },
        "artifact_identity": {
            "dataset_sha256": file_sha256(
                ROOT / "data/evaluation/source_aware_conversation.v1.yaml"
            ),
            "dataset_manifest_sha256": file_sha256(manifest_path),
            "commit": identity["commit"],
            "tree": identity["tree"],
        },
        "results": [
            {
                "id": f"SA-SYNTHETIC-{index:03d}",
                "passed": True,
                "checks": {"deterministic_fixture": True},
            }
            for index in range(total)
        ],
    }


def _valid_hard_probe_report() -> dict[str, object]:
    dataset = load_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)
    profile = load_expectation_profile("rc2.2", dataset, dataset_path=DEFAULT_DATASET)
    identity = source_identity(ROOT)
    results = [
        {
            "id": case.id,
            "passed": True,
            "priority": case.priority,
            "failure_reason": None,
        }
        for case in dataset.cases
    ]
    return {
        "schema_version": "firelens_hard_probe_report.v2",
        "manifest": {
            "commit": identity["commit"],
            "tree": identity["tree"],
            "expectation_profile": "rc2.2",
            "expectation_overlay_sha256": file_sha256(DEFAULT_RC2_2_EXPECTATIONS),
            "effective_expectations_sha256": canonical_json_sha256(
                effective_expectations_payload(dataset, profile)
            ),
            "dataset_sha256": file_sha256(DEFAULT_DATASET),
            "mode": "offline",
            "provider_boundary": "offline_double",
        },
        "summary": {
            "executed": 105,
            "passed": 105,
            "failed": 0,
            "minimum_passed": profile.minimum_passed,
            "minimum_passed_met": True,
            "cost_usd": 0.0,
        },
        "results": results,
    }


def test_inventory_declares_every_commanded_suite_without_provider_execution() -> None:
    payload = inventory(ROOT)

    assert tuple(payload["suites"]) == SUITES
    assert payload["policy"]["network_allowed"] is False
    assert payload["policy"]["provider_calls_allowed"] is False
    assert payload["suites"]["core"]["availability"] == "executable"
    assert payload["suites"]["rag"]["availability"] == "executable_local"
    assert payload["suites"]["ui"]["availability"] == "executable_local"


def test_source_identity_binds_dirty_file_content_not_only_status_shape(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Eval Test"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "eval@example.test"],
        check=True,
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)

    tracked.write_text("first\n", encoding="utf-8")
    first = source_identity(tmp_path)
    tracked.write_text("other\n", encoding="utf-8")
    second = source_identity(tmp_path)

    assert first["dirty"] is True
    assert first["working_tree_status_sha256"] == second["working_tree_status_sha256"]
    assert first["working_tree_sha256"] != second["working_tree_sha256"]
    assert first["application_sha"] != second["application_sha"]


def test_claimbench_validation_recomputes_complete_raw_rows() -> None:
    report = _valid_claimbench_report()

    assert validate_claimbench_report(report, repository_root=ROOT) == []


def test_claimbench_validation_fails_closed_when_a_raw_row_regresses() -> None:
    report = _valid_claimbench_report()
    rows = report["rows"]
    assert isinstance(rows, list)
    rows[0] = {**rows[0], "correct": False}

    issues = validate_claimbench_report(report, repository_root=ROOT)

    assert "ClaimBench raw rows differ from deterministic recomputation" in issues
    assert "ClaimBench row correctness fields do not match acceptance decisions" in issues


def test_claimbench_validation_rejects_summary_only_evidence() -> None:
    report = _valid_claimbench_report()
    report.pop("rows")

    assert validate_claimbench_report(report, repository_root=ROOT) == [
        "rows are required to recompute ClaimBench outcomes"
    ]


def test_hard_probe_validation_requires_exact_rc2_2_profile() -> None:
    report = _valid_hard_probe_report()
    assert validate_hard_probe_report(report, repository_root=ROOT) == []

    manifest = report["manifest"]
    assert isinstance(manifest, dict)
    manifest["expectation_profile"] = "historical"

    assert "hard-probe expectation profile must be rc2.2" in validate_hard_probe_report(
        report, repository_root=ROOT
    )


def test_hard_probe_validation_recomputes_case_count_and_floor() -> None:
    report = _valid_hard_probe_report()
    results = report["results"]
    assert isinstance(results, list)
    results.pop()

    issues = validate_hard_probe_report(report, repository_root=ROOT)

    assert "hard probe did not execute all 105 cases in canonical order" in issues
    assert "hard-probe executed count must be exactly 105" in issues
    assert "hard-probe summary does not match raw rows" in issues


def test_hard_probe_validation_does_not_average_away_a_critical_failure() -> None:
    report = _valid_hard_probe_report()
    results = report["results"]
    summary = report["summary"]
    assert isinstance(results, list)
    assert isinstance(summary, dict)
    critical_index = next(index for index, row in enumerate(results) if row["id"] == "F06")
    results[critical_index] = {
        **results[critical_index],
        "passed": False,
        "failure_reason": "synthetic critical failure",
    }
    summary.update({"passed": 104, "failed": 1})

    issues = validate_hard_probe_report(report, repository_root=ROOT)

    assert any(
        issue.startswith("hard-probe contains failed CRITICAL cases:") for issue in issues
    )


def test_hard_probe_case_mismatch_fails_gate_but_stays_in_review(tmp_path: Path) -> None:
    context = RunContext(
        root=ROOT,
        run_dir=tmp_path,
        run_id="core-test",
        started_at="2026-09-04T00:00:00+00:00",
        identity=source_identity(ROOT),
        registry=load_registry(ROOT),
        policy=load_policy(ROOT),
    )

    record = _new_failure(
        context,
        suite="core",
        adapter_id="hard_probe_rc2_2",
        case_id="K09",
        status="FAIL",
        failure_class="hard_probe_case_failure_within_profile",
        severity="CRITICAL",
        oracle="deterministic_executable",
        summary="mode 'requires_input' is not allowed",
        expected={"allowed_modes": ["abstention"]},
        observed={"response_mode": "requires_input"},
        evidence=["raw/hard_probe_rc2_2.json"],
        first_divergent_layer="evaluation_contract",
        reproduction=["python scripts/run_hard_probe.py --expectation-profile rc2.2"],
        lifecycle_status="review",
        first_divergence_owner=("data/evaluation/hard_probe_rc2_2_expectations.v1.yaml"),
        first_divergence_confidence="suspected",
    )

    assert record["run_status"] == "FAIL"
    assert record["status"] == "review"
    assert record["fixed_in_sha"] is None
    assert record["first_divergence"] == {
        "layer": "evaluation_contract",
        "owner": "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml",
        "confidence": "suspected",
    }

    fixed_record = _new_failure(
        context,
        suite="core",
        adapter_id="hard_probe_rc2_2",
        case_id="K09",
        status="FAIL",
        failure_class="hard_probe_case_failure_within_profile",
        severity="CRITICAL",
        oracle="deterministic_executable",
        summary="verified on an exact candidate",
        expected={},
        observed={},
        evidence=[],
        first_divergent_layer="evaluation_contract",
        reproduction=[],
        lifecycle_status="fixed",
        fixed_in_sha="a" * 40,
    )
    assert fixed_record["status"] == "fixed"
    assert fixed_record["fixed_in_sha"] == "a" * 40

    with pytest.raises(ValueError, match="fixed FailureRecords require an exact"):
        _new_failure(
            context,
            suite="core",
            adapter_id="hard_probe_rc2_2",
            case_id="K09",
            status="FAIL",
            failure_class="hard_probe_case_failure_within_profile",
            severity="CRITICAL",
            oracle="deterministic_executable",
            summary="not actually bound",
            expected={},
            observed={},
            evidence=[],
            first_divergent_layer="evaluation_contract",
            reproduction=[],
            lifecycle_status="fixed",
        )


def test_rc2_2_profile_manifest_remains_the_bound_authority() -> None:
    manifest = json.loads(DEFAULT_RC2_2_EXPECTATIONS_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["profile"] == "rc2.2"
    assert manifest["expectations_sha256"] == file_sha256(DEFAULT_RC2_2_EXPECTATIONS)
    assert manifest["minimum_passed"] == 86


def test_makefile_hard_probe_target_pins_rc2_2() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("v1-6-hard-probe:", 1)[1].split("\n\n", 1)[0]

    assert "--expectation-profile rc2.2" in target


def test_unavailable_suite_writes_blocked_evidence_not_a_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "rag"

    context = RunContext(
        root=ROOT,
        run_dir=run_dir,
        run_id="blocked-adapter-test",
        started_at="2026-09-04T00:00:00+00:00",
        identity=source_identity(ROOT),
        registry=load_registry(ROOT),
        policy=load_policy(ROOT),
    )
    definition = next(
        row
        for row in context.registry["suites"]["rag"]["adapters"]
        if row["id"] == "rag_qualification_inventory"
    )
    adapter, failures = eval_lab._blocked_adapter(context, suite="rag", definition=definition)
    assert adapter["status"] == "BLOCKED"
    failure = failures[0]
    assert validate_failure_record(failure, repository_root=ROOT) == []
    assert failure["status"] == "review"
    assert failure["run_status"] == "BLOCKED"
    assert failure["family"] == "evidence_not_executed"
    assert failure["first_divergence"] == {
        "layer": "evaluation_availability",
        "owner": "rag_qualification_inventory",
        "confidence": "unknown",
    }
    assert set(failure["pipeline"]) == {
        "understanding",
        "binding",
        "authority",
        "planning",
        "retrieval",
        "reranking",
        "evidence",
        "generation",
        "validation",
        "composition",
        "frontend",
    }
    assert failure["expected"] == {
        "invariants": "an explicitly authorized, identity-bound executable adapter"
    }
    assert failure["observed"] == {"structured_state": "BLOCKED"}
    assert failure["judge_model"] is None
    assert failure["application_sha"] == context.identity["application_sha"]
    assert set(failure["identity"]) >= {
        "application_sha",
        "dataset_sha",
        "evaluator_sha",
        "provider_model",
        "embedding_model",
        "rerank_model",
        "judge_model",
        "judge_prompt_sha",
    }


def test_failure_schema_requires_campaign_fields() -> None:
    schema = json.loads(
        (ROOT / "evals/eval_lab/schema/failure_record.schema.json").read_text(encoding="utf-8")
    )

    assert {
        "family",
        "input",
        "expected",
        "observed",
        "pipeline",
        "first_divergence",
        "fixed_in_sha",
        "judge_model",
        "judge_prompt",
        "judge_prompt_sha256",
        "sampling_settings",
        "rubric_version",
        "application_sha",
    } <= set(schema["required"])
    assert schema["properties"]["status"]["enum"] == [
        "confirmed_fail",
        "review",
        "fixed",
        "cannot_reproduce",
    ]
    assert {
        "application_sha",
        "dataset_sha",
        "evaluator_sha",
        "provider_model",
        "embedding_model",
        "rerank_model",
        "judge_model",
        "judge_prompt_sha",
    } <= set(schema["properties"]["identity"]["required"])


def test_campaign_regressions_are_normalized_unclosed_failure_records() -> None:
    path = ROOT / "evals/eval_lab/core/campaign_failure_records.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert {record["case_id"] for record in records} == {
        "K09",
        "LIVE-CLOSED-STATUS-001",
        "LIVE-CONTRACT-ROW-001",
        "LIVE-GEOMETRY-CONTRACT-001",
        "LIVE-NAMED-PAGINATION-001",
        "LIVE-PAGINATION-COMPLETE-001",
        "LIVE-PUBLISHED-COUNT-001",
        "LIVE-ROSTER-UNION-001",
        "LIVE-SIZE-CONTRACT-001",
        "LIVE-TIMESTAMP-CONTRACT-001",
        "PLACE-CONTEXT-DECLARATION-001",
        "PLACE-FRONTED-ALIAS-001",
        "UI-LIVE-IDENTITY-001",
        "UI-LIVE-MAP-LABEL-001",
        "UI-PROD-AXE-001",
    }
    assert len({record["failure_id"] for record in records}) == len(records)
    for record in records:
        assert validate_failure_record(record, repository_root=ROOT) == []
        assert record["status"] == "confirmed_fail"
        assert record["fixed_in_sha"] is None


def test_not_run_ui_suite_is_never_reported_as_pass(tmp_path: Path) -> None:
    del tmp_path
    adapters = inventory(ROOT)["suites"]["ui"]["adapters"]
    reality = next(row for row in adapters if row["id"] == "ui_reality_inventory")
    assert reality["status"] == "NOT_RUN"


def test_diagnose_reads_actual_raw_case_evidence(tmp_path: Path, actual_core_run: Path) -> None:
    _copy_actual_core_run(actual_core_run, tmp_path / "run")

    payload, status = diagnose_case("F06", artifact_root=tmp_path, repository_root=ROOT)

    assert status == 0
    assert payload["status"] == "FOUND"
    assert payload["matches"][0]["rows"][0]["id"] == "F06"


def test_compare_rejects_nonexistent_commit_selectors(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base SHA does not resolve to a local commit"):
        compare_runs(
            "a" * 40,
            "b" * 40,
            artifact_root=tmp_path,
            repository_root=ROOT,
        )


def test_compare_validates_each_clean_run_against_its_own_commit(
    two_commit_core_runs: tuple[Path, Path, str, str],
) -> None:
    repository, artifact_root, base_sha, candidate_sha = two_commit_core_runs

    payload, status = compare_runs(
        base_sha,
        candidate_sha,
        artifact_root=artifact_root,
        repository_root=repository,
    )

    assert base_sha != candidate_sha
    assert status in {0, 1}
    assert payload["status"] in {"PASS", "FAIL"}
    assert payload["base"]["identity"]["commit"] == base_sha
    assert payload["candidate"]["identity"]["commit"] == candidate_sha


def test_dirty_evidence_is_comparison_ineligible() -> None:
    issues = _artifact_eligibility_issues(
        {
            "identity": {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "dirty": True,
                "changed_during_run": False,
                "application_sha": "f" * 64,
            }
        }
    )

    assert issues == [
        "source tree was dirty",
        "application SHA is not the clean commit",
    ]


def test_envelope_blocks_tampered_material_bindings(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    envelope["adapters"][0]["materials"]["synthetic_marker"] = "0" * 64

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert any("material bindings do not exactly match" in issue for issue in issues)


def test_envelope_rejects_tampered_execution_boundary(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    envelope["execution"]["network_allowed"] = True

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert "run execution boundary disagrees with zero-cost policy" in issues


def test_compare_rejects_malformed_envelope_instead_of_passing(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    envelope["status"] = "UNKNOWN"
    envelope["adapters"] = []
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    commit = envelope["identity"]["commit"]

    payload, status = compare_runs(commit, commit, artifact_root=tmp_path, repository_root=ROOT)

    assert status == 2
    assert payload["status"] == "BLOCKED"
    assert payload["envelope_validation_issues"]["candidate"]


def test_diagnose_rejects_raw_artifact_tampering(tmp_path: Path, actual_core_run: Path) -> None:
    _, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    hard_probe = next(
        item for item in envelope["adapters"] if item["adapter_id"] == "hard_probe_rc2_2"
    )
    (tmp_path / "run" / hard_probe["raw_artifact"]).write_text(
        json.dumps({"results": [{"id": "F06", "passed": True}]}), encoding="utf-8"
    )

    payload, status = diagnose_case("F06", artifact_root=tmp_path, repository_root=ROOT)

    assert status == 2
    assert payload["status"] == "BLOCKED"


def test_envelope_rejects_hash_bound_empty_core_report(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    productbench = next(
        item for item in envelope["adapters"] if item["adapter_id"] == "productbench_offline"
    )
    raw_path = envelope_path.parent / productbench["raw_artifact"]
    raw_path.write_text("{}\n", encoding="utf-8")
    productbench["raw_artifact_sha256"] = file_sha256(raw_path)

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert any("status does not match canonical raw report" in issue for issue in issues)
    assert any("normalized case counts do not match" in issue for issue in issues)
    assert any("report-contract failures do not reconcile" in issue for issue in issues)


def test_envelope_rejects_self_consistent_but_forged_case_counts(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    productbench = next(
        item for item in envelope["adapters"] if item["adapter_id"] == "productbench_offline"
    )
    productbench["case_counts"].update(
        {"expected": 32, "executed": 32, "passed": 32, "failed": 0, "not_run": 0}
    )
    envelope["summary"]["executed_cases"] += 1
    envelope["summary"]["passed_cases"] += 1

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert any("normalized case counts do not match" in issue for issue in issues)


@pytest.mark.parametrize(
    ("adapter_id", "mutate"),
    [
        (
            "productbench_offline",
            lambda report: report["results"][0].update({"contract": {"forged": "contract"}}),
        ),
        (
            "source_aware_conversation",
            lambda report: report["results"][0].update({"id": "SA-INVENTED-999"}),
        ),
    ],
)
def test_envelope_rejects_hash_bound_fabricated_row_semantics(
    tmp_path: Path,
    actual_core_run: Path,
    adapter_id: str,
    mutate: object,
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    adapter = next(item for item in envelope["adapters"] if item["adapter_id"] == adapter_id)
    raw_path = envelope_path.parent / adapter["raw_artifact"]
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(report)
    raw_path.write_text(json.dumps(report), encoding="utf-8")
    adapter["raw_artifact_sha256"] = file_sha256(raw_path)

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert f"adapter {adapter_id} raw semantics differ from deterministic replay" in issues


def test_source_aware_volatile_vector_manifest_is_not_claimed_as_a_material(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    adapter = next(
        item
        for item in envelope["adapters"]
        if item["adapter_id"] == "source_aware_conversation"
    )
    assert "vector_manifest_sha256" not in adapter["materials"]
    raw_path = envelope_path.parent / adapter["raw_artifact"]
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    report["artifact_identity"]["vector_manifest_sha256"] = "0" * 64
    raw_path.write_text(json.dumps(report), encoding="utf-8")
    adapter["raw_artifact_sha256"] = file_sha256(raw_path)
    adapter["materials"]["vector_manifest_sha256"] = "0" * 64

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert any("hash-bound raw report" in issue for issue in issues)


def test_productbench_volatile_response_sha_cannot_be_reintroduced(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    adapter = next(
        item for item in envelope["adapters"] if item["adapter_id"] == "productbench_offline"
    )
    raw_path = envelope_path.parent / adapter["raw_artifact"]
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    trace = report["results"][0]["trace"]
    assert "response_sha256" not in trace
    trace["response_sha256"] = "0" * 64
    raw_path.write_text(json.dumps(report), encoding="utf-8")
    adapter["raw_artifact_sha256"] = file_sha256(raw_path)

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert (
        "adapter productbench_offline raw report claims an unsupported volatile response SHA"
        in issues
    )


def test_envelope_rejects_critical_priority_downgrade(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    adapter = next(
        item for item in envelope["adapters"] if item["adapter_id"] == "hard_probe_rc2_2"
    )
    raw_path = envelope_path.parent / adapter["raw_artifact"]
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    f06 = next(row for row in report["results"] if row["id"] == "F06")
    assert f06["priority"] == "CRITICAL"
    f06["priority"] = "HIGH"
    raw_path.write_text(json.dumps(report), encoding="utf-8")
    adapter["raw_artifact_sha256"] = file_sha256(raw_path)

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert "adapter hard_probe_rc2_2 raw semantics differ from deterministic replay" in issues
    assert "report-contract failures do not reconcile" in " ".join(issues)


def test_source_change_during_run_persists_blocked_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = source_identity(ROOT)
    final = {
        **initial,
        "working_tree_status_sha256": "a" * 64,
        "working_tree_sha256": "b" * 64,
        "application_sha": "d" * 64,
    }
    changed = False
    original_source_identity = eval_lab.source_identity
    original_source_aware = eval_lab._run_source_aware

    def controlled_source_identity(root: Path = ROOT) -> dict[str, object]:
        if root.resolve() == ROOT.resolve() and changed:
            return final
        return original_source_identity(root)

    def source_aware_then_change(
        context: RunContext,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        nonlocal changed
        result = original_source_aware(context)
        changed = True
        return result

    monkeypatch.setattr(eval_lab, "source_identity", controlled_source_identity)
    monkeypatch.setattr(eval_lab, "_run_source_aware", source_aware_then_change)

    envelope, run_dir = eval_lab.run_suite(
        "core", output_dir=tmp_path / "changed", repository_root=ROOT
    )

    assert envelope["status"] == "BLOCKED"
    assert envelope["identity"]["changed_during_run"] is True
    assert any(
        item["failure_class"] == "source_identity_changed_during_run"
        for item in envelope["failures"]
    )
    assert (run_dir / "envelope.json").is_file()
    assert (run_dir / "failure_records.jsonl").is_file()
    assert (
        validate_run_envelope(
            envelope,
            envelope_path=run_dir / "envelope.json",
            repository_root=ROOT,
        )
        == []
    )
    comparison, comparison_status = compare_runs(
        str(envelope["identity"]["commit"]),
        str(envelope["identity"]["commit"]),
        artifact_root=run_dir,
        repository_root=ROOT,
    )
    assert comparison_status == 2
    assert comparison["status"] == "BLOCKED"
    assert (
        "source identity was not proven stable for the run"
        in comparison["artifact_eligibility_issues"]["candidate"]
    )


def test_minimal_fabricated_core_reports_are_rejected(
    tmp_path: Path, actual_core_run: Path
) -> None:
    del actual_core_run  # Populate the deterministic replay cache from an actual run first.
    current = source_identity(ROOT)
    envelope_path = _write_core_envelope(
        tmp_path / "forged",
        commit=str(current["commit"]),
        finished_at="2026-09-04T00:00:00+00:00",
    )
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert {
        "adapter productbench_offline raw semantics differ from deterministic replay",
        "adapter hard_probe_rc2_2 raw semantics differ from deterministic replay",
        "adapter source_aware_conversation raw semantics differ from deterministic replay",
    } <= set(issues)


def test_envelope_binds_raw_report_revision_to_run_identity(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    adapter = next(
        item
        for item in envelope["adapters"]
        if item["adapter_id"] == "source_aware_conversation"
    )
    raw_path = envelope_path.parent / adapter["raw_artifact"]
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    report["artifact_identity"]["commit"] = "a" * 40
    raw_path.write_text(json.dumps(report), encoding="utf-8")
    adapter["raw_artifact_sha256"] = file_sha256(raw_path)
    adapter["materials"] = report["artifact_identity"]

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert (
        "adapter source_aware_conversation raw report commit disagrees with run identity"
        in issues
    )


def test_envelope_rejects_nonexistent_commit_identity(
    tmp_path: Path, actual_core_run: Path
) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    envelope["identity"].update(
        {"commit": "a" * 40, "tree": "c" * 40, "dirty": False, "application_sha": "a" * 40}
    )

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert "run commit does not resolve to a local Git object" in issues


def test_envelope_rejects_commit_tree_mismatch(tmp_path: Path, actual_core_run: Path) -> None:
    envelope_path, envelope = _copy_actual_core_run(actual_core_run, tmp_path / "run")
    envelope["identity"]["tree"] = "c" * 40

    issues = validate_run_envelope(envelope, envelope_path=envelope_path, repository_root=ROOT)

    assert "run tree does not match the commit's Git tree" in issues


def test_failure_record_schema_is_strict_and_versioned() -> None:
    schema = json.loads(
        (ROOT / "evals/eval_lab/schema/failure_record.schema.json").read_text(encoding="utf-8")
    )

    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == ("firelens.eval_lab.failure.v1")
    assert {"failure_id", "case_id", "expected", "observed", "identity"} <= set(
        schema["required"]
    )
