#!/usr/bin/env python3
"""Check that declared dependencies remain represented by exact lock entries."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
EXACT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)")


def check_python_lock() -> list[str]:
    findings: list[str] = []
    locked: dict[str, str] = {}
    for raw_line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT.match(line)
        if match is None:
            findings.append(f"requirements.lock is not exact: {line}")
            continue
        locked[canonicalize_name(match.group(1))] = match.group(2)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = [
        *pyproject["project"].get("dependencies", []),
        *pyproject["project"].get("optional-dependencies", {}).get("dev", []),
    ]
    for value in declared:
        requirement = Requirement(value)
        name = canonicalize_name(requirement.name)
        version = locked.get(name)
        if version is None:
            findings.append(f"Python dependency is missing from requirements.lock: {name}")
        elif requirement.specifier and Version(version) not in requirement.specifier:
            findings.append(f"Locked {name}=={version} violates {requirement.specifier}")
    return findings


def check_node_lock() -> list[str]:
    frontend = ROOT / "apps/web"
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    findings: list[str] = []
    if lock.get("lockfileVersion") != 3:
        findings.append("package-lock.json must use lockfileVersion 3")
    root_package = (lock.get("packages") or {}).get("") or {}
    for group in ("dependencies", "devDependencies"):
        declared = package.get(group) or {}
        locked = root_package.get(group) or {}
        if declared != locked:
            findings.append(f"package.json {group} differs from package-lock.json")
    return findings


def main() -> None:
    findings = [*check_python_lock(), *check_node_lock()]
    if findings:
        raise SystemExit("Lockfile consistency failed:\n" + "\n".join(findings))
    print("Python and Node lockfiles are consistent with declared dependencies.")


if __name__ == "__main__":
    main()
