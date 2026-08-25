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


def is_prohibited_license_metadata(value: str, *, field: str) -> bool:
    """Apply the license policy without treating bundled license prose as a package license.

    ``License-Expression`` is structured SPDX metadata, so it remains eligible for
    SPDX matching even if a producer happens to wrap it across lines.  The legacy
    ``License`` field is less reliable: package distributions can put a complete
    bundled-notices document there.  Only compact legacy values are package-level
    license expressions for this report.
    """

    if field != "License":
        return is_prohibited_license_expression(value)
    return "\n" not in value and "\r" not in value and is_prohibited_license_expression(value)


def python_licenses() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        expression = distribution.metadata.get("License-Expression")
        field = "License-Expression" if expression else "License"
        license_value = expression or distribution.metadata.get("License")
        rows.append(
            {
                "name": name,
                "version": distribution.version,
                "license": (license_value or "UNKNOWN").strip(),
                "_license_field": field,
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
                "_license_field": "package.json license",
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def _report_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove collection-only metadata before writing the stable report schema."""

    return [
        {key: value for key, value in row.items() if not key.startswith("_")} for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    python_rows = python_licenses()
    node_rows = node_licenses(ROOT / "apps/web/package-lock.json")
    report: dict[str, list[dict[str, str]] | list[str]] = {
        "python": _report_rows(python_rows),
        "node": _report_rows(node_rows),
    }
    prohibited = [
        f"{ecosystem}:{row['name']}:{row['license']}"
        for ecosystem, rows in (("python", python_rows), ("node", node_rows))
        for row in rows
        if is_prohibited_license_metadata(row["license"], field=row["_license_field"])
    ]
    report["prohibited"] = prohibited
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if prohibited:
        raise SystemExit("Prohibited dependency licenses:\n" + "\n".join(prohibited))
    print(f"Recorded {len(report['python'])} Python and {len(report['node'])} npm licenses.")


if __name__ == "__main__":
    main()
