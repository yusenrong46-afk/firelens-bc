#!/usr/bin/env python3
"""Create a machine-readable Python and npm license inventory."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROHIBITED = {"AGPL-3.0", "GPL-3.0", "SSPL-1.0"}
_PROHIBITED_SPDX = re.compile(
    r"(?<![A-Za-z0-9])(?:AGPL-3\.0|GPL-3\.0|SSPL-1\.0)"
    r"(?:-(?:only|or-later)|\+)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def is_prohibited_license_expression(value: str) -> bool:
    """Match prohibited SPDX identifiers, including version suffixes and expressions."""

    return bool(_PROHIBITED_SPDX.search(value))


def python_licenses() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        license_value = distribution.metadata.get(
            "License-Expression"
        ) or distribution.metadata.get("License")
        rows.append(
            {
                "name": name,
                "version": distribution.version,
                "license": (license_value or "UNKNOWN").strip(),
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def node_licenses(lock_path: Path) -> list[dict[str, str]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for package_path, metadata in (lock.get("packages") or {}).items():
        if not package_path or not isinstance(metadata, dict):
            continue
        rows.append(
            {
                "name": package_path.removeprefix("node_modules/"),
                "version": str(metadata.get("version") or "UNKNOWN"),
                "license": str(metadata.get("license") or "UNKNOWN"),
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    python_rows = python_licenses()
    node_rows = node_licenses(ROOT / "apps/web/package-lock.json")
    report: dict[str, list[dict[str, str]] | list[str]] = {
        "python": python_rows,
        "node": node_rows,
    }
    prohibited = [
        f"{ecosystem}:{row['name']}:{row['license']}"
        for ecosystem, rows in (("python", python_rows), ("node", node_rows))
        for row in rows
        if is_prohibited_license_expression(row["license"])
    ]
    report["prohibited"] = prohibited
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if prohibited:
        raise SystemExit("Prohibited dependency licenses:\n" + "\n".join(prohibited))
    print(f"Recorded {len(report['python'])} Python and {len(report['node'])} npm licenses.")


if __name__ == "__main__":
    main()
