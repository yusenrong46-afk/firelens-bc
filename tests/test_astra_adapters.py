"""Native evidence reconciliation controls and realistic report mutants."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from firelens_eval import local_adapters


def _control(tmp_path: Path) -> tuple[dict, dict]:
    native = {
        "collected": ["case-a"],
        "events": {
            "case-a": [
                {"phase": phase, "outcome": "passed", "duration_s": 0.1}
                for phase in ("setup", "call", "teardown")
            ]
        },
    }
    path = tmp_path / "native.json"
    path.write_text(json.dumps(native))
    definition = {"id": "test", "engine": "pytest", "materials": [], "expected_ids": ["case-a"]}
    report = {
        "schema_version": "firelens.local_diagnostic.v1",
        "adapter_id": "test",
        "engine": "pytest",
        "command": "local-diagnostics-v1 test",
        "exit_code": 0,
        "rows": [{"id": "case-a", "outcome": "passed"}],
        "materials": {},
        "artifacts": {"native.json": local_adapters.sha(path)},
        "native_artifact": "native.json",
    }
    return report, definition


def test_native_control(tmp_path: Path) -> None:
    report, definition = _control(tmp_path)
    assert local_adapters.validate(report, tmp_path, tmp_path, definition) == []


@pytest.mark.parametrize(
    "mutation",
    [
        "omitted_case",
        "invented_case",
        "exit_code",
        "stale_native",
        "rewritten_outcome",
        "skip",
        "command",
        "missing_native",
    ],
)
def test_native_report_mutants_fail_closed(tmp_path: Path, mutation: str) -> None:
    report, definition = _control(tmp_path)
    changed = copy.deepcopy(report)
    if mutation == "omitted_case":
        changed["rows"] = []
    elif mutation == "invented_case":
        changed["rows"][0]["id"] = "invented"
    elif mutation == "exit_code":
        changed["exit_code"] = 1
    elif mutation == "stale_native":
        (tmp_path / "native.json").write_text("{}")
    elif mutation == "rewritten_outcome":
        changed["rows"][0]["outcome"] = "failed"
    elif mutation == "skip":
        changed["rows"][0]["outcome"] = "skipped"
    elif mutation == "command":
        changed["command"] = "echo success"
    elif mutation == "missing_native":
        changed["artifacts"] = {}
    assert local_adapters.validate(changed, tmp_path, tmp_path, definition)
