#!/usr/bin/env python3
"""Fail when a workflow action or container reference is not digest pinned."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
USE = re.compile(r"""^\s*(?:-\s*)?uses:\s*["']?([^"'\s#]+)""", re.MULTILINE)
FULL_SHA = re.compile(r"^[a-f0-9]{40}$")
DOCKER_DIGEST = re.compile(r"^docker://.+@sha256:[a-f0-9]{64}$")
DOCKERFILE_FROM = re.compile(
    r"^\s*FROM(?:\s+--platform=\S+)?\s+(\S+)", re.MULTILINE | re.IGNORECASE
)
PINNED_BASE = re.compile(r"^[^@\s]+@sha256:[a-f0-9]{64}$")


def unpinned_actions(directory: Path = WORKFLOWS) -> list[str]:
    findings: list[str] = []
    for path in sorted(directory.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for reference in USE.findall(text):
            if reference.startswith("./"):
                continue
            if reference.startswith("docker://"):
                pinned = DOCKER_DIGEST.fullmatch(reference) is not None
            else:
                _, separator, revision = reference.rpartition("@")
                pinned = bool(separator and FULL_SHA.fullmatch(revision))
            if not pinned:
                label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
                findings.append(f"{label}: {reference}")
    return findings


def unpinned_dockerfile_bases(path: Path = ROOT / "Dockerfile") -> list[str]:
    """Return mutable external base-image references from one Dockerfile."""

    findings: list[str] = []
    for reference in DOCKERFILE_FROM.findall(path.read_text(encoding="utf-8")):
        if reference.casefold() == "scratch":
            continue
        if PINNED_BASE.fullmatch(reference) is None:
            label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
            findings.append(f"{label}: {reference}")
    return findings


def main() -> None:
    findings = [*unpinned_actions(), *unpinned_dockerfile_bases()]
    if findings:
        raise SystemExit("Unpinned external references:\n" + "\n".join(findings))
    print("All external workflow actions and Docker bases use immutable references.")


if __name__ == "__main__":
    main()
