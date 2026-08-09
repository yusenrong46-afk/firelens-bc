from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

import firelens.evaluation.limitation_cli as limitation_cli
import scripts.run_limitation_probe as legacy_limitation_probe
from firelens.evaluation.limitation_cases import (
    build_generalization_cases,
    build_jailbreak_cases,
    build_naive_cases,
    dump_yaml_cases,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"


def test_legacy_limitation_probe_import_resolves_to_package_cli() -> None:
    assert legacy_limitation_probe is limitation_cli


def test_generated_limitation_cases_match_frozen_datasets(tmp_path: Path) -> None:
    suites = (
        ("naive_user_probe.v1.yaml", build_naive_cases, 100),
        ("rag_jailbreak_probe.v1.yaml", build_jailbreak_cases, 32),
        ("rag_generalization_probe.v1.yaml", build_generalization_cases, 33),
    )
    observed_ids: set[str] = set()
    for filename, builder, expected_count in suites:
        cases = builder()
        assert len(cases) == expected_count
        case_ids = {case.id for case in cases}
        assert len(case_ids) == expected_count
        assert not observed_ids.intersection(case_ids)
        observed_ids.update(case_ids)

        output = tmp_path / filename
        dump_yaml_cases(cases, output)
        generated = yaml.safe_load(output.read_text(encoding="utf-8"))
        frozen = yaml.safe_load(
            (ROOT / "data/evaluation" / filename).read_text(encoding="utf-8")
        )
        assert generated["dataset_version"] == frozen["dataset_version"]
        assert generated["case_count"] == frozen["case_count"]
        assert generated["cases"] == frozen["cases"]


def test_limitation_probe_launcher_is_runnable() -> None:
    completed = subprocess.run(
        [str(PYTHON), "scripts/run_limitation_probe.py", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--dump-only" in completed.stdout
