"""Pure source and catalog identity helpers for the ProductBench v2 runner."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


def git_value(root: Path, revision: str) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", revision],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value or None


def git_bytes(root: Path, *arguments: str) -> bytes:
    """Return deterministic git output without letting a missing command look clean."""

    completed = subprocess.run(["git", *arguments], cwd=root, check=False, capture_output=True)
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return completed.stdout


def source_state(
    *,
    root: Path,
    git_bytes: Callable[..., bytes],
    canonical_sha256: Callable[[object], str],
) -> dict[str, Any]:
    """Bind a report to working-source bytes as well as HEAD/tree pointers."""

    status = git_bytes("status", "--porcelain=v1", "-z", "--untracked-files=all")
    tracked_diff = git_bytes("diff", "--binary", "HEAD")
    untracked_paths = sorted(
        path.decode("utf-8", errors="surrogateescape")
        for path in git_bytes("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if path
    )
    untracked = [
        {
            "path": path,
            "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
        }
        for path in untracked_paths
        if (root / path).is_file()
    ]
    return {
        "git_clean": not bool(status),
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "untracked_content_sha256": canonical_sha256(untracked),
        "untracked_file_count": len(untracked),
    }


def load_raw_catalog(catalog_path: Path) -> dict[str, Any]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "firelens.productbench_journeys.v1":
        raise ValueError("ProductBench v2 only accepts the v1 raw catalog schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 50:
        raise ValueError("ProductBench must contain exactly 50 raw cases")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != 50 or any(not isinstance(item, str) for item in ids) or len(set(ids)) != 50:
        raise ValueError("ProductBench raw case IDs must be exactly 50 unique strings")
    if payload.get("case_count") != 50:
        raise ValueError("ProductBench raw case_count must be 50")
    return cast(dict[str, Any], payload)


def executable_catalog_payload(
    *,
    schema: str,
    catalog: dict[str, Any],
    catalog_path: Path,
    file_sha256: Callable[[Path], str],
    contract_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the derived v2 contract without replacing the raw source catalog."""

    return {
        "schema_version": schema,
        "raw_catalog_schema": catalog["schema_version"],
        "raw_catalog_sha256": file_sha256(catalog_path),
        "case_count": len(contract_rows),
        "cases": contract_rows,
    }


def rewrite_manifest(
    *,
    manifest_path: Path,
    catalog: dict[str, Any],
    contract_rows: list[dict[str, Any]],
    raw_catalog_sha256: str,
    contract_sha256: str,
    executable_catalog_schema: str,
    executable_catalog_sha256: str,
    tiers: list[str],
) -> dict[str, Any]:
    """Rewrite the unsealed manifest's derived fields and return the new manifest."""

    text = manifest_path.read_text(encoding="utf-8")
    manifest = cast(dict[str, Any], json.loads(text))
    scalars: dict[str, Any] = {
        "raw_catalog_schema": catalog["schema_version"],
        "raw_catalog_sha256": raw_catalog_sha256,
        "case_count": len(catalog["cases"]),
        "contract_sha256": contract_sha256,
        "executable_catalog_schema": executable_catalog_schema,
        "executable_catalog_sha256": executable_catalog_sha256,
    }
    lists: dict[str, Any] = {
        "case_ids": [str(case["id"]) for case in catalog["cases"]],
        "tiers": {
            tier: [row["id"] for row in contract_rows if row["tier"] == tier] for tier in tiers
        },
    }
    if all(manifest.get(key) == value for key, value in lists.items()):
        # Only hashes moved: substitute them in place so the hand-formatted
        # ID lists keep their layout and the diff stays reviewable.
        for key, value in scalars.items():
            text = re.sub(
                rf'("{re.escape(key)}":\s*)("[^"]*"|\d+)',
                lambda match, value=value: match.group(1) + json.dumps(value),
                text,
                count=1,
            )
        manifest.update(scalars)
    else:
        manifest.update(scalars)
        manifest.update(lists)
        text = json.dumps(manifest, indent=2) + "\n"
    manifest_path.write_text(text, encoding="utf-8")
    return manifest


def identity(
    *,
    root: Path,
    catalog_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    tier: str,
    git_value: Callable[[str], str | None],
    file_sha256: Callable[[Path], str],
    source_state_value: dict[str, Any],
) -> dict[str, Any]:
    return {
        "commit": git_value("HEAD"),
        "tree": git_value("HEAD^{tree}"),
        "catalog_path": str(catalog_path.relative_to(root)),
        "manifest_path": str(manifest_path.relative_to(root)),
        "raw_catalog_sha256": manifest["raw_catalog_sha256"],
        "manifest_sha256": file_sha256(manifest_path),
        "contract_sha256": manifest["contract_sha256"],
        "executable_catalog_sha256": manifest["executable_catalog_sha256"],
        "schema_version": manifest["schema_version"],
        "tier": tier,
        "status": manifest["status"],
        "case_ids": manifest["tiers"][tier],
        **source_state_value,
    }
