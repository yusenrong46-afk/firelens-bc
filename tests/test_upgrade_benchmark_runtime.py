from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_runtime_artifact_metrics_are_recomputed_from_retained_inventories() -> None:
    _, after = _passing_snapshots()

    values = upgrade_benchmark._runtime_artifact_metric_values(after)

    assert values == {
        "runtime_artifact_qualified": True,
        "runtime_artifact_missing_required_count": 0,
        "runtime_artifact_prohibited_count": 0,
        "runtime_artifact_identity_match": True,
        "runtime_artifact_candidate_commit_match": True,
    }

    after["runtime_artifact"]["comparison"]["qualified"] = False
    with pytest.raises(ValueError, match="differs from recomputed"):
        upgrade_benchmark._runtime_artifact_metric_values(after)


def test_runtime_artifact_metrics_detect_missing_and_prohibited_files() -> None:
    _, missing = _passing_snapshots()
    for inventory in missing["runtime_artifact"]["inventories"].values():
        inventory["files"] = [
            row for row in inventory["files"] if row["logical_path"] != "requirements.lock"
        ]
    _rehash_runtime_artifact_section(missing["runtime_artifact"])
    _sync_runtime_artifact_commitments(missing)

    missing_values = upgrade_benchmark._runtime_artifact_metric_values(missing)
    assert missing_values["runtime_artifact_missing_required_count"] == 2
    assert missing_values["runtime_artifact_qualified"] is False

    _, prohibited = _passing_snapshots()
    logical_path = "data/evaluation/sealed-leak.json"
    content_sha256 = hashlib.sha256(b"leak").hexdigest()
    for _platform_name, inventory in prohibited["runtime_artifact"]["inventories"].items():
        platform_root = inventory["identity"]["platform_root"]
        inventory["files"].append(
            {
                "logical_path": logical_path,
                "platform_path": f"{platform_root}/{logical_path}",
                "size_bytes": 4,
                "sha256": content_sha256,
            }
        )
    _rehash_runtime_artifact_section(prohibited["runtime_artifact"])
    _sync_runtime_artifact_commitments(prohibited)

    prohibited_values = upgrade_benchmark._runtime_artifact_metric_values(prohibited)
    assert prohibited_values["runtime_artifact_prohibited_count"] == 2
    assert prohibited_values["runtime_artifact_qualified"] is False


def test_runtime_artifact_metrics_detect_candidate_commit_substitution() -> None:
    _, after = _passing_snapshots()
    substituted_commit = "c" * 40
    section = after["runtime_artifact"]
    for platform_name, inventory in section["inventories"].items():
        evidence = section["candidate_configurations"][platform_name]
        document = json.loads(evidence["raw_json"])
        document["build_commit"] = substituted_commit
        raw_json = json.dumps(document, sort_keys=True)
        raw = raw_json.encode()
        evidence.update(
            {
                "raw_json": raw_json,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
        inventory["identity"]["build_commit"] = substituted_commit
        inventory["runtime_configuration"]["sha256"] = evidence["sha256"]
        candidate_entry = next(
            row
            for row in inventory["files"]
            if row["logical_path"] == "config/runtime_candidate.v1.json"
        )
        candidate_entry["sha256"] = evidence["sha256"]
        candidate_entry["size_bytes"] = evidence["size_bytes"]
    _rehash_runtime_artifact_section(section)
    _sync_runtime_artifact_commitments(after)

    values = upgrade_benchmark._runtime_artifact_metric_values(after)
    assert values["runtime_artifact_candidate_commit_match"] is False
    assert values["runtime_artifact_identity_match"] is False
    assert values["runtime_artifact_qualified"] is False


def test_runtime_artifact_capture_sequence_rejects_artifact_mutation() -> None:
    _, after = _passing_snapshots()
    pre_command = {
        key: value
        for key, value in after["runtime_artifact"].items()
        if key != "capture_sequence"
    }
    post_command = json.loads(json.dumps(pre_command))
    post_command["inventories"]["docker"]["identity"]["artifact_id"] = "docker-mutated"

    with pytest.raises(ValueError, match="changed during benchmark capture"):
        upgrade_benchmark._finalize_runtime_artifact_pair(pre_command, post_command)


def test_capture_owned_frontend_run_discards_external_synthetic_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "benchmark"
    stale_directory = output_dir / "frontend_surface"
    stale_directory.mkdir(parents=True)
    stale_report = stale_directory / "report.json"
    stale_report.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-01T00:00:00+00:00",
                "summary": {"qualified": True},
                "external_synthetic": True,
            }
        ),
        encoding="utf-8",
    )
    (stale_directory / "stale.png").write_bytes(b"synthetic")

    def run_fresh(command: list[str], log_path: Path) -> dict:
        assert not stale_directory.exists()
        assert command[-2:] == ["--output-dir", str(stale_directory)]
        stale_directory.mkdir()
        stale_report.write_text(
            json.dumps(
                {
                    "generated_at": upgrade_benchmark.datetime.now(
                        upgrade_benchmark.UTC
                    ).isoformat()
                }
            ),
            encoding="utf-8",
        )
        return {"exit_code": 2, "passed": False, "log_path": str(log_path)}

    monkeypatch.setattr(upgrade_benchmark, "_run_logged", run_fresh)
    monkeypatch.setattr(
        upgrade_benchmark,
        "_frontend_bundle",
        lambda: {"manifest_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        upgrade_benchmark,
        "_frontend_surface",
        lambda *args, **kwargs: {"qualified": False},
    )

    result = _capture_frontend_surface(
        output_dir=output_dir,
        expected_commit="a" * 40,
        expected_environment={},
    )

    assert result["run"]["exit_code"] == 2
    assert not (stale_directory / "stale.png").exists()
    assert "external_synthetic" not in json.loads(stale_report.read_text(encoding="utf-8"))


def test_capture_owned_frontend_run_rejects_stale_generated_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "benchmark"

    def write_stale(command: list[str], log_path: Path) -> dict:
        report_path = Path(command[-1]) / "report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(
            json.dumps({"generated_at": "2026-08-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        return {"exit_code": 2, "passed": False, "log_path": str(log_path)}

    monkeypatch.setattr(upgrade_benchmark, "_run_logged", write_stale)

    with pytest.raises(ValueError, match="current capture-owned run"):
        _capture_frontend_surface(
            output_dir=output_dir,
            expected_commit="a" * 40,
            expected_environment={},
        )
