"""Command-line interface for the canonical FireLens EvalLab adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from firelens.evaluation.common import ROOT
from firelens_eval.lab import (
    DEFAULT_ARTIFACT_ROOT,
    SUITES,
    compare_runs,
    diagnose_case,
    exit_code_for_status,
    inventory,
    run_suite,
)


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m firelens_eval",
        description="Run and inspect normalized, zero-cost FireLens evaluation evidence.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inventory_parser = commands.add_parser(
        "inventory", help="List executable and blocked evaluation adapters"
    )
    inventory_parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON destination; stdout is always emitted",
    )

    run_parser = commands.add_parser("run", help="Run one canonical suite")
    run_parser.add_argument("--suite", required=True, choices=SUITES)
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        help=f"Run directory (default: a new directory below {DEFAULT_ARTIFACT_ROOT})",
    )

    diagnose_parser = commands.add_parser(
        "diagnose", help="Find raw and normalized evidence for one case ID"
    )
    diagnose_parser.add_argument("case_id")
    diagnose_parser.add_argument(
        "--artifacts",
        type=Path,
        help="Artifact directory or envelope.json to search",
    )

    compare_parser = commands.add_parser(
        "compare", help="Compare normalized evidence for two recorded Git identities"
    )
    compare_parser.add_argument("base_sha")
    compare_parser.add_argument("candidate_sha")
    compare_parser.add_argument(
        "--suite", choices=SUITES, default="core", help="Suite to compare (default: core)"
    )
    compare_parser.add_argument(
        "--artifacts",
        type=Path,
        help="Artifact directory or envelope.json to search",
    )
    draft = commands.add_parser(
        "draft-public", help="Run public-path v2 with pending contract approval"
    )
    draft.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "draft-public":
            from firelens_eval.public_v2 import run_sync

            report = run_sync(args.output)
            _print(
                {
                    "protocol": report["schema_version"],
                    "counts": report["counts"],
                    "approval_status": report["approval_status"],
                }
            )
            return 1 if report["counts"].get("FAIL") else 0
        if args.command == "inventory":
            payload = inventory(ROOT)
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            _print(payload)
            return 0
        if args.command == "run":
            envelope, run_dir = run_suite(
                args.suite,
                output_dir=args.output_dir,
                repository_root=ROOT,
            )
            _print(
                {
                    "schema_version": envelope["schema_version"],
                    "run_id": envelope["run_id"],
                    "suite": envelope["suite"],
                    "status": envelope["status"],
                    "run_dir": str(run_dir),
                    "envelope": str(run_dir / "envelope.json"),
                    "report": str(run_dir / "report.md"),
                    "failure_records": str(run_dir / "failure_records.jsonl"),
                    "summary": envelope["summary"],
                }
            )
            return exit_code_for_status(str(envelope["status"]))
        if args.command == "diagnose":
            payload, status = diagnose_case(
                args.case_id,
                artifact_root=args.artifacts,
                repository_root=ROOT,
            )
            _print(payload)
            return status
        if args.command == "compare":
            payload, status = compare_runs(
                args.base_sha,
                args.candidate_sha,
                artifact_root=args.artifacts,
                repository_root=ROOT,
                suite=args.suite,
            )
            _print(payload)
            return status
    except (OSError, RuntimeError, ValueError) as exc:
        _print(
            {
                "schema_version": "firelens.eval_lab.cli_error.v1",
                "status": "BLOCKED",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return 2
    print("unknown EvalLab command", file=sys.stderr)
    return 2
