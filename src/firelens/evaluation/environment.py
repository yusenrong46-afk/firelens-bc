"""Process, report, and execution-environment helpers for qualification runs."""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from firelens.evaluation.common import file_sha256


def read_report(path: Path | None) -> dict[str, Any] | None:
    """Read a JSON or YAML object, returning ``None`` for absent reports."""

    if path is None or not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw) if path.suffix in {".yaml", ".yml"} else json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def p95(values: list[float]) -> float | None:
    """Return the nearest-rank 95th percentile used by retained reports."""

    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def run_logged(
    command: list[str],
    log_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Run one qualification command and retain its complete output digest."""

    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "log_path": str(log_path.relative_to(repository_root)),
        "log_sha256": file_sha256(log_path),
    }


def command_version(command: list[str], *, repository_root: Path) -> str:
    """Return a tool version string without making environment capture fail open."""

    try:
        completed = subprocess.run(
            command,
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return completed.stdout.strip() or completed.stderr.strip() or "unavailable"


def cpu_model(
    command_version_reader: Callable[[list[str]], str],
    *,
    processor_reader: Callable[[], str] = platform.processor,
    uname_processor_reader: Callable[[], str] = lambda: platform.uname().processor,
    system_reader: Callable[[], str] = platform.system,
) -> str:
    """Resolve the CPU identity using the browser runner's Node source first."""

    observed = command_version_reader(
        [
            "node",
            "-e",
            "process.stdout.write(require('os').cpus()[0]?.model ?? '')",
        ]
    )
    if observed != "unavailable":
        return observed
    observed = processor_reader().strip() or uname_processor_reader().strip()
    if observed:
        return observed
    if system_reader() == "Darwin":
        observed = command_version_reader(["sysctl", "-n", "machdep.cpu.brand_string"])
        if observed != "unavailable":
            return observed
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return "unknown"


def execution_environment(
    *,
    repository_root: Path,
    command_version_reader: Callable[[list[str]], str],
    cpu_model_reader: Callable[[], str],
) -> dict[str, str | int]:
    """Return stable fields that bind timing and bundle measurements."""

    frontend = repository_root / "apps/web"
    try:
        lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
        playwright_version = str(lock["packages"]["node_modules/@playwright/test"]["version"])
    except (KeyError, OSError, TypeError, ValueError):
        playwright_version = "unavailable"
    chromium_executable = command_version_reader(
        [
            "node",
            "-e",
            (
                "const {chromium}=require('./apps/web/node_modules/"
                "playwright');process.stdout.write(chromium.executablePath())"
            ),
        ]
    )
    chromium_version = (
        command_version_reader([chromium_executable, "--version"])
        if chromium_executable != "unavailable"
        else "unavailable"
    )
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_model": cpu_model_reader(),
        "logical_cpu_count": os.cpu_count() or 0,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "node_version": command_version_reader(["node", "--version"]),
        "npm_version": command_version_reader(["npm", "--version"]),
        "playwright_version": playwright_version,
        "chromium_version": chromium_version,
    }
