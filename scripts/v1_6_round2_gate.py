#!/usr/bin/env python3
"""Run Round-2 zero-cost qualification commands and fail if any subcommand fails."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
HARD_PROBE_OUTPUT = ROOT / "output/benchmark/v1_6_round2/hard_probe_gate.json"
FROZEN_HARD_PROBE_SHA256 = "ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035"
ROUND1_PASS_FLOOR = 82
ROUND2_PASS_FLOOR = 86
COMMANDS = (
    (
        "claimbench-v1",
        [
            str(PYTHON),
            "-c",
            (
                "from pathlib import Path; "
                "from firelens.evaluation.claimbench import evaluate_catalog, load_claimbench; "
                "summary = evaluate_catalog(load_claimbench(Path('.'))); "
                "assert summary['correct'] == summary['total'] == 200, summary; "
                "print(summary['correct'])"
            ),
        ],
    ),
    (
        "claimbench-v2",
        [
            str(PYTHON),
            "-c",
            (
                "from pathlib import Path; "
                "from firelens.evaluation.claimbench_v2 import evaluate_v2_catalog, load_claimbench_v2; "
                "summary = evaluate_v2_catalog(load_claimbench_v2(Path('.'))); "
                "summary.pop('rows', None); "
                "assert summary['unsafe_false_accept_rate'] == 0.0, summary; "
                "assert summary['faithful_false_reject_rate'] == 0.0, summary; "
                "assert summary['critical_field_preservation'] == 1.0, summary; "
                "assert summary['always_abstain'] is False, summary; "
                "assert summary['correct'] == summary['total'], summary; "
                "print(summary['correct'])"
            ),
        ],
    ),
    (
        "hard-probe",
        [
            str(PYTHON),
            "scripts/run_hard_probe.py",
            "--mode",
            "offline",
            "--output",
            "output/benchmark/v1_6_round2/hard_probe_gate.json",
        ],
    ),
    ("retrieval-dry-run", [str(PYTHON), "scripts/v1_6_round2_retrieval.py", "--dry-run"]),
    (
        "performance",
        [
            str(PYTHON),
            "scripts/v1_6_round2_performance.py",
            "--warmup",
            "10",
            "--measured",
            "30",
        ],
    ),
    ("package-verify", [str(PYTHON), "scripts/v1_6_upgrade.py", "package-verify"]),
)


def _hard_probe_gate(returncode: int) -> int:
    payload = json.loads(HARD_PROBE_OUTPUT.read_text(encoding="utf-8"))
    summary = payload["summary"]
    failed_ids = [row["id"] for row in payload["results"] if not row["passed"]]
    dataset = payload["manifest"]["dataset_sha256"]
    print(
        json.dumps(
            {
                "executed": summary["executed"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "failed_ids": failed_ids,
                "dataset_sha256": dataset,
                "probe_exit": returncode,
            },
            indent=2,
        )
    )
    if dataset != FROZEN_HARD_PROBE_SHA256:
        print("FAILED hard-probe dataset hash changed", file=sys.stderr)
        return 1
    if summary["executed"] != 105:
        print("FAILED hard-probe did not execute 105 cases", file=sys.stderr)
        return 1
    if summary["passed"] < ROUND2_PASS_FLOOR:
        print(
            f"FAILED hard-probe {summary['passed']}/105 below Round-2 floor {ROUND2_PASS_FLOOR} "
            f"(Round-1 floor {ROUND1_PASS_FLOOR})",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    results: list[dict[str, object]] = []
    failed = False
    for name, command in COMMANDS:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        status = completed.returncode
        if name == "hard-probe":
            status = _hard_probe_gate(completed.returncode)
        results.append({"name": name, "returncode": status, "command": command})
        if status != 0:
            failed = True
            print(f"FAILED {name} status={status}", file=sys.stderr)
        else:
            print(f"PASSED {name}")
    if failed:
        print(
            "Round-2 gate failed:", [row["name"] for row in results if row["returncode"] != 0]
        )
        return 1
    print("Round-2 gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
