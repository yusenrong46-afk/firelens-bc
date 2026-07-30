#!/usr/bin/env python3
"""Fail when a workflow uses an external action without a full commit SHA."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
USE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[a-f0-9]{40}$")


def unpinned_actions(directory: Path = WORKFLOWS) -> list[str]:
    findings: list[str] = []
    for path in sorted(directory.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for action, revision in USE.findall(text):
            if action.startswith("./"):
                continue
            if not FULL_SHA.fullmatch(revision):
                label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
                findings.append(f"{label}: {action}@{revision}")
    return findings


def main() -> None:
    findings = unpinned_actions()
    if findings:
        raise SystemExit("Unpinned GitHub Actions:\n" + "\n".join(findings))
    print("All external GitHub Actions are pinned to full commit SHAs.")


if __name__ == "__main__":
    main()
