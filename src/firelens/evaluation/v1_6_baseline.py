"""Collect a content-free V1.6 before snapshot from the current tree."""

from __future__ import annotations

import ast
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.common import file_sha256, sha256_json
from firelens.evaluation.environment import (
    command_version,
    cpu_model,
    execution_environment,
)
from firelens.evaluation.git_evidence import git
from firelens.evaluation.v1_6_standard import (
    V16UpgradeStandard,
    load_v1_6_standard,
    standard_identity,
)

SNAPSHOT_RELATIVE = "output/benchmark/v1_6/before/snapshot.json"
SEAL_RELATIVE = "data/evaluation/firelens_v1_6_before_snapshot_seal.json"
PUBLIC_AGENT_ROOTS = ("agent", "api")


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def module_inventory(repository_root: Path) -> dict[str, Any]:
    package = repository_root / "src/firelens"
    modules = {
        path.relative_to(repository_root).as_posix(): _line_count(path)
        for path in sorted(package.rglob("*.py"))
    }
    tests = {
        path.relative_to(repository_root).as_posix(): _line_count(path)
        for path in sorted((repository_root / "tests").glob("test_*.py"))
    }
    return {
        "production_modules": modules,
        "test_modules": tests,
        "agent_loop_lines": modules.get("src/firelens/agent/loop.py"),
        "largest_production_modules": sorted(
            modules.items(), key=lambda item: item[1], reverse=True
        )[:20],
        "largest_test_modules": sorted(tests.items(), key=lambda item: item[1], reverse=True)[
            :10
        ],
    }


def public_agent_exception_inventory(repository_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    package = repository_root / "src/firelens"
    for root in PUBLIC_AGENT_ROOTS:
        for path in sorted((package / root).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler) or node.type is None:
                    continue
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    findings.append(
                        {
                            "path": path.relative_to(repository_root).as_posix(),
                            "line": node.lineno,
                            "kind": "except_Exception",
                        }
                    )
    return findings


def _run(command: list[str], *, repository_root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_chars": len(completed.stdout),
        "stderr_chars": len(completed.stderr),
        "status": "EXECUTED" if completed.returncode == 0 else "EXECUTED_FAILED",
    }


def capture_before_snapshot(
    repository_root: Path,
    *,
    run_tests: bool = False,
) -> dict[str, Any]:
    """Assemble the machine-readable before snapshot. Missing work stays BLOCKED."""

    standard = load_v1_6_standard(repository_root)
    identity = standard_identity(repository_root, standard)
    commit = git(repository_root, "rev-parse", "HEAD")
    branch = git(repository_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(git(repository_root, "status", "--porcelain"))
    environment = execution_environment(
        repository_root=repository_root,
        command_version_reader=lambda command: command_version(
            command, repository_root=repository_root
        ),
        cpu_model_reader=lambda: cpu_model(
            lambda command: command_version(command, repository_root=repository_root)
        ),
    )
    measurements: dict[str, Any] = {
        "secret_scan": _run(
            [str(repository_root / ".venv/bin/python"), "scripts/secret_scan.py"],
            repository_root=repository_root,
        ),
        "module_inventory": module_inventory(repository_root),
        "public_agent_except_exception": public_agent_exception_inventory(repository_root),
        "pure_static_outer_write": {
            "status": "INSPECTED",
            "notes": (
                "loop.py prefetches static RAG then calls chat_turn; compose.py "
                "returns packet.static_response. EXECUTED characterization is "
                "tests/test_luna_brain_agent.py::test_guidance_prefetch_single_call_"
                "includes_reviewed_answer, which currently requires one outer write."
            ),
        },
        "full_zero_cost_verification": {
            "status": "BLOCKED",
            "reason": "not run in Stage 0 capture",
        },
        "offline_hard_probe": {"status": "BLOCKED", "reason": "not run in Stage 0 capture"},
        "frontend_surface": {"status": "BLOCKED", "reason": "not run in Stage 0 capture"},
        "claimbench": {
            "status": "BLOCKED",
            "reason": "ClaimBench is authored in patch group 3",
        },
        "sealed_retrieval": {"status": "EXTERNAL", "reason": "V3 sealed set is protocol-only"},
        "paid_human_preview_firewall": {
            "status": "EXTERNAL",
            "reason": "requires explicit authorization and a cost ceiling",
        },
        "runtime_artifact_parity": {
            "status": "BLOCKED",
            "reason": "no staged Vercel/Docker pair in this capture",
        },
        "route_provider_counters": {
            "status": "BLOCKED",
            "reason": "RequestExecutionPolicy is introduced in patch group 1",
        },
    }
    if run_tests:
        measurements["targeted_agent_tests"] = _run(
            [
                str(repository_root / ".venv/bin/python"),
                "-m",
                "pytest",
                "-q",
                "tests/test_luna_brain_agent.py",
                "tests/test_v1_6_standard.py",
            ],
            repository_root=repository_root,
        )
    snapshot = {
        "schema_version": "firelens_v1_6_before_snapshot.v1",
        "captured_at": datetime.now(UTC).isoformat(),
        "phase": "before",
        "identity": {
            **identity,
            "repository_root": str(repository_root),
            "branch": branch,
            "commit": commit,
            "dirty": dirty,
            "package_version": "1.5.3rc1",
            "release_version": "1.5.3-rc.1",
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        },
        "execution_environment": environment,
        "measurements": measurements,
        "hypotheses": {
            "pure_static_discarded_outer_write": "REPRODUCED",
            "broad_exception_swallowing": "REPRODUCED",
            "stale_handbook": "REPRODUCED",
            "unqualified_verified_wording": "REPRODUCED",
            "packaging_parity": "PARTIALLY_REPRODUCED",
            "module_and_test_size": "REPRODUCED",
            "qualification_distinct_from_local": "REPRODUCED",
        },
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot


def write_before_snapshot(repository_root: Path, snapshot: dict[str, Any]) -> Path:
    path = repository_root / SNAPSHOT_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_before_snapshot_seal(
    *,
    repository_root: Path,
    snapshot: dict[str, Any],
    snapshot_path: Path,
    standard: V16UpgradeStandard,
    owner: str,
) -> dict[str, Any]:
    identity = snapshot["identity"]
    return {
        "schema_version": "firelens_v1_6_before_snapshot_seal.v1",
        "standard_id": standard.standard_id,
        "benchmark_id": standard.benchmark_id,
        "sealed_by": owner,
        "sealed_at": datetime.now(UTC).isoformat(),
        "before_snapshot": {
            "path": SNAPSHOT_RELATIVE,
            "sha256": file_sha256(snapshot_path),
        },
        "candidate_identity": {
            "commit": identity["commit"],
            "branch": identity["branch"],
            "package_version": identity["package_version"],
            "release_version": identity["release_version"],
        },
        "spec_identity": {
            "path": identity["spec_path"],
            "sha256": identity["spec_sha256"],
        },
        "dataset_identity": {
            "registry": identity["dataset_role_registry"],
            "identity_input_sha256": identity["identity_input_sha256"],
        },
        "harness_identity": {
            "harness_input_sha256": identity["harness_input_sha256"],
        },
    }


def write_seal(repository_root: Path, seal: dict[str, Any]) -> Path:
    path = repository_root / SEAL_RELATIVE
    path.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
