"""Bound local pytest/browser adapters over existing test owners.

The versioned roster is accessible and provisional, never sealed qualification.
Native results are retained separately and reconciled on every validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST = Path("data/evaluation/astra_local_diagnostics.v1.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definitions(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / MANIFEST).read_text())
    return {
        key: {**value, "materials": manifest["materials"]}
        for key, value in manifest["adapters"].items()
    }


def materials(root: Path, definition: dict[str, Any]) -> dict[str, str]:
    return {relative: sha(root / relative) for relative in definition["materials"]}


def canonical_command(definition: dict[str, Any]) -> str:
    return "local-diagnostics-v1 " + str(definition["id"])


def _browser_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []

    def visit(suites: list[dict[str, Any]]) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    results = test.get("results", [])
                    status = test.get("status")
                    rows.append(
                        {
                            "id": spec["title"],
                            "outcome": "passed"
                            if status == "expected"
                            and results
                            and results[-1].get("status") == "passed"
                            else "skipped"
                            if status == "skipped"
                            else "failed",
                        }
                    )
            visit(suite.get("suites", []))

    visit(payload.get("suites", []))
    return rows


def native_rows(payload: dict[str, Any], engine: str) -> list[dict[str, Any]]:
    if engine == "playwright":
        return _browser_rows(payload)
    if engine == "vitest":
        return [
            {"id": row["fullName"], "outcome": row["status"]}
            for suite in payload.get("testResults", [])
            for row in suite.get("assertionResults", [])
        ]
    rows = []
    for nodeid in payload.get("collected", []):
        events = payload.get("events", {}).get(nodeid, [])
        outcome = "skipped"
        if any(event["outcome"] == "failed" for event in events):
            outcome = "failed"
        elif {event["phase"] for event in events} == {"setup", "call", "teardown"} and all(
            event["outcome"] == "passed" for event in events
        ):
            outcome = "passed"
        rows.append({"id": nodeid, "outcome": outcome})
    return rows


def counts(rows: list[dict[str, Any]], expected: int) -> dict[str, int]:
    passed = sum(row["outcome"] == "passed" for row in rows)
    failed = sum(row["outcome"] == "failed" for row in rows)
    return {
        "expected": expected,
        "executed": passed + failed,
        "passed": passed,
        "failed": failed,
        "not_run": max(0, expected - passed - failed),
    }


def execute(
    root: Path, run_dir: Path, definition: dict[str, Any], identity: dict[str, Any]
) -> dict[str, Any]:
    adapter_id = definition["id"]
    raw_dir = run_dir / "raw" / adapter_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    native_path = raw_dir / "native.json"
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(token in key for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))
    }
    env.update(
        PYTHONPATH=f"{root / 'src'}:{root / 'tests'}",
        FIRELENS_LOCAL_REPORT=str(native_path),
        FIRELENS_LOCAL_ARTIFACTS=str(raw_dir),
    )
    engine = definition["engine"]
    if engine == "pytest":
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "firelens_eval.pytest_reporter",
            *definition["selection"],
        ]
        cwd = root
    elif engine == "vitest":
        command = [
            "npm",
            "exec",
            "--",
            "vitest",
            "run",
            *definition["selection"],
            "--reporter=json",
            f"--outputFile={native_path}",
        ]
        cwd = root / "apps/web"
    else:
        command = [
            "npm",
            "exec",
            "--",
            "playwright",
            "test",
            "--config=playwright.real.config.ts",
            *definition["selection"],
            "--reporter=json",
        ]
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(native_path)
        env["PLAYWRIGHT_HTML_OPEN"] = "never"
        cwd = root / "apps/web"
    problem = None
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
        (raw_dir / "runner.log").write_text(result.stdout)
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        (raw_dir / "runner.log").write_text(str(exc))
        exit_code, problem = -1, "runner_timeout"
    payload = json.loads(native_path.read_text()) if native_path.is_file() else {}
    rows = native_rows(payload, engine)
    if engine == "playwright" and (root / "apps/web/test-results").is_dir():
        shutil.copytree(
            root / "apps/web/test-results", raw_dir / "browser-artifacts", dirs_exist_ok=True
        )
    artifacts = {
        str(path.relative_to(run_dir)): sha(path)
        for path in raw_dir.rglob("*")
        if path.is_file()
    }
    return {
        "schema_version": "firelens.local_diagnostic.v1",
        "adapter_id": adapter_id,
        "identity": {key: identity[key] for key in ("commit", "tree", "application_sha")},
        "command": canonical_command(definition),
        "engine": engine,
        "exit_code": exit_code,
        "runner_problem": problem,
        "rows": rows,
        "materials": materials(root, definition),
        "artifacts": artifacts,
        "native_artifact": str(native_path.relative_to(run_dir)),
        "limits": "Unsealed local fixtures; no provider, live-feed, deployed, human or release qualification.",
    }


def validate(
    report: dict[str, Any], root: Path, run_dir: Path, definition: dict[str, Any]
) -> list[str]:
    issues = []
    if (
        report.get("schema_version") != "firelens.local_diagnostic.v1"
        or report.get("adapter_id") != definition["id"]
    ):
        issues.append("invalid_adapter_identity")
    if (
        report.get("command") != canonical_command(definition)
        or report.get("engine") != definition["engine"]
    ):
        issues.append("noncanonical_command")
    if report.get("materials") != materials(root, definition):
        issues.append("changed_diagnostic_materials")
    rows = report.get("rows", [])
    if [row.get("id") for row in rows] != definition["expected_ids"]:
        issues.append("incomplete_or_changed_roster")
    if any(row.get("outcome") not in {"passed", "failed", "skipped"} for row in rows):
        issues.append("invalid_outcome")
    if report.get("runner_problem") or report.get("exit_code") not in {0, 1}:
        issues.append("runner_did_not_complete")
    expected_exit = 1 if any(row.get("outcome") == "failed" for row in rows) else 0
    if report.get("exit_code") != expected_exit:
        issues.append("exit_status_disagrees_with_cases")
    if any(row.get("outcome") == "skipped" for row in rows):
        issues.append("unexpected_skip")
    for relative, digest in report.get("artifacts", {}).items():
        path = (run_dir / relative).resolve()
        if (
            not path.is_relative_to(run_dir.resolve())
            or not path.is_file()
            or sha(path) != digest
        ):
            issues.append("native_artifact_missing_or_changed")
    native_relative = report.get("native_artifact", "")
    path = (run_dir / native_relative).resolve()
    if (
        native_relative not in report.get("artifacts", {})
        or not path.is_relative_to(run_dir.resolve())
        or not path.is_file()
    ):
        issues.append("missing_native_results")
    elif rows != native_rows(json.loads(path.read_text()), definition["engine"]):
        issues.append("native_outcomes_disagree")
    for relative in report.get("artifacts", {}):
        if relative.endswith("loopback-samples.json"):
            payload = json.loads((run_dir / relative).read_text())
            if len(payload.get("repetitions", [])) != 3:
                issues.append("incomplete_performance_repetitions")
            for repetition in payload.get("repetitions", []):
                for row in repetition.get("routes", {}).values():
                    samples = row.get("samples", [])
                    if len(samples) != 30 or any(
                        not s.get("contract_valid")
                        or s.get("http_status") != 200
                        or not math.isfinite(s.get("latency_ms", math.nan))
                        for s in samples
                    ):
                        issues.append("invalid_performance_samples")
    return sorted(set(issues))
