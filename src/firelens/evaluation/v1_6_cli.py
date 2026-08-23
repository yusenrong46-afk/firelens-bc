"""CLI for the frozen FireLens V1.6 baseline, gate, report, and package checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from firelens.evaluation.v1_6_baseline import (
    SEAL_RELATIVE,
    SNAPSHOT_RELATIVE,
    build_before_snapshot_seal,
    capture_before_snapshot,
    write_before_snapshot,
    write_seal,
)
from firelens.evaluation.v1_6_standard import load_v1_6_standard


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def baseline(args: argparse.Namespace) -> int:
    root = _root()
    standard = load_v1_6_standard(root)
    snapshot = capture_before_snapshot(root, run_tests=args.run_tests)
    snapshot_path = write_before_snapshot(root, snapshot)
    result: dict[str, Any] = {
        "status": "captured",
        "snapshot": SNAPSHOT_RELATIVE,
        "commit": snapshot["identity"]["commit"],
        "spec_sha256": snapshot["identity"]["spec_sha256"],
    }
    if args.seal:
        seal = build_before_snapshot_seal(
            repository_root=root,
            snapshot=snapshot,
            snapshot_path=snapshot_path,
            standard=standard,
            owner=args.owner,
        )
        write_seal(root, seal)
        result["seal"] = SEAL_RELATIVE
    _print(result)
    return 0


def gate(_args: argparse.Namespace) -> int:
    root = _root()
    standard = load_v1_6_standard(root)
    snapshot_path = root / SNAPSHOT_RELATIVE
    seal_path = root / SEAL_RELATIVE
    if not snapshot_path.is_file() or not seal_path.is_file():
        _print({"status": "BLOCKED", "reason": "before snapshot or seal is missing"})
        return 2
    _print(
        {
            "status": "standard_loaded",
            "standard_id": standard.standard_id,
            "gates": list(standard.hard_gates),
            "snapshot_present": True,
            "seal_present": True,
            "note": "H0-H9 require implementation evidence; this command only checks freeze identity",
        }
    )
    return 0


def report(_args: argparse.Namespace) -> int:
    root = _root()
    standard = load_v1_6_standard(root)
    snapshot = root / SNAPSHOT_RELATIVE
    _print(
        {
            "standard_id": standard.standard_id,
            "release_target": standard.release_target,
            "snapshot": SNAPSHOT_RELATIVE if snapshot.is_file() else None,
            "h10": "EXTERNAL",
        }
    )
    return 0


def package_verify(_args: argparse.Namespace) -> int:
    from firelens.runtime_packaging import verify_packaging_parity

    report = verify_packaging_parity(_root())
    staged = {
        "status": "BLOCKED",
        "reason": "staged Vercel/Docker inventories are not captured in this environment",
    }
    payload = {**report, "staged_inventories": staged}
    _print(payload)
    return 0 if report["status"] == "passed" else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="FireLens V1.6 upgrade harness")
    commands = parser.add_subparsers(dest="command", required=True)
    baseline_parser = commands.add_parser("baseline", help="Capture the before snapshot")
    baseline_parser.add_argument("--run-tests", action="store_true")
    baseline_parser.add_argument("--seal", action="store_true")
    baseline_parser.add_argument("--owner", default="FireLens V1.6 engineering owner")
    commands.add_parser("gate", help="Check frozen standard and seal identity")
    commands.add_parser("report", help="Print the current V1.6 evidence pointer")
    commands.add_parser("package-verify", help="Runtime-artifact qualification pointer")
    args = parser.parse_args()
    handlers = {
        "baseline": baseline,
        "gate": gate,
        "report": report,
        "package-verify": package_verify,
    }
    raise SystemExit(handlers[args.command](args))
