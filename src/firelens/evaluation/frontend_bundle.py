"""Manifest-complete frontend bundle accounting for release qualification."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

Manifest = dict[str, dict[str, Any]]


def measure_frontend_bundle(dist: Path, *, repository_root: Path) -> dict[str, Any]:
    """Measure every emitted frontend artifact using the Vite dependency graph."""

    client = dist / "client"
    manifest_path = client / ".vite/manifest.json"
    if not manifest_path.is_file():
        raise ValueError("frontend Vite manifest is missing; bundle size cannot be measured")
    manifest = _load_manifest(manifest_path)
    entries = [key for key, item in manifest.items() if item.get("isEntry") is True]
    if len(entries) != 1:
        raise ValueError("frontend Vite manifest must contain exactly one entry")
    initial_chunks = _manifest_closure(manifest, entries, follow_dynamic=False)
    all_chunks = _manifest_closure(manifest, entries, follow_dynamic=True)
    initial_js = {
        value
        for value in _referenced_files(manifest, initial_chunks, "file")
        if value.endswith(".js")
    }
    all_js = {
        value
        for value in _referenced_files(manifest, all_chunks, "file")
        if value.endswith(".js")
    }
    lazy_js = all_js - initial_js
    initial_css = _referenced_files(manifest, initial_chunks, "css")
    all_css = _referenced_files(manifest, all_chunks, "css")
    lazy_css = all_css - initial_css
    initial_assets = _referenced_files(manifest, initial_chunks, "assets")
    all_assets = _referenced_files(manifest, all_chunks, "assets")
    lazy_assets = all_assets - initial_assets
    emitted_files = {
        path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()
    }
    client_emitted_files = {
        path.relative_to(client).as_posix() for path in client.rglob("*") if path.is_file()
    }
    _validate_emitted_graph(
        emitted_files,
        client_emitted_files,
        initial_js,
        lazy_js,
        all_js,
        initial_css,
        lazy_css,
        all_css,
        all_assets,
    )
    rows = _asset_rows(
        dist,
        emitted_files,
        initial_js,
        lazy_js,
        initial_css,
        lazy_css,
        initial_assets,
        lazy_assets,
    )
    if {row["name"] for row in rows} != emitted_files:
        raise ValueError("frontend build output contains unclassified files")
    return _bundle_report(manifest_path, repository_root, rows)


def _load_manifest(path: Path) -> Manifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not payload
        or not all(isinstance(value, dict) for value in payload.values())
    ):
        raise ValueError("frontend Vite manifest is empty or invalid")
    return payload


def _manifest_closure(manifest: Manifest, keys: list[str], *, follow_dynamic: bool) -> set[str]:
    visited: set[str] = set()
    pending = list(keys)
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        item = manifest.get(key)
        if item is None:
            raise ValueError(f"frontend manifest references an unknown entry: {key}")
        visited.add(key)
        fields = ["imports", "dynamicImports"] if follow_dynamic else ["imports"]
        for field in fields:
            values = item.get(field) or []
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                raise ValueError(f"frontend manifest {field} are invalid for {key}")
            pending.extend(values)
    return visited


def _referenced_files(manifest: Manifest, keys: set[str], field: str) -> set[str]:
    files: set[str] = set()
    for key in keys:
        value = manifest[key].get(field)
        values = [value] if field == "file" else value or []
        if not isinstance(values, list) or not all(
            item is None or isinstance(item, str) for item in values
        ):
            raise ValueError(f"frontend manifest {field} is invalid for {key}")
        files.update(item for item in values if item)
    return files


def _validate_emitted_graph(
    emitted: set[str],
    client_emitted: set[str],
    initial_js: set[str],
    lazy_js: set[str],
    all_js: set[str],
    initial_css: set[str],
    lazy_css: set[str],
    all_css: set[str],
    all_assets: set[str],
) -> None:
    missing_runtime = sorted({"server/index.js", ".openai/hosting.json"} - emitted)
    if missing_runtime:
        raise ValueError(
            f"frontend build is missing required server/hosting artifacts: {missing_runtime}"
        )
    if not initial_js:
        raise ValueError("frontend Vite manifest entry does not emit JavaScript")
    if initial_js & lazy_js or initial_css & lazy_css:
        raise ValueError("frontend JavaScript was classified as both initial and lazy")
    _validate_classification(
        all_js, {item for item in client_emitted if item.endswith(".js")}, "JavaScript"
    )
    _validate_classification(
        all_css, {item for item in client_emitted if item.endswith(".css")}, "CSS"
    )
    missing_assets = sorted((all_assets | all_css | all_js) - client_emitted)
    if missing_assets:
        raise ValueError(
            f"frontend manifest assets are missing from build output: {missing_assets}"
        )


def _validate_classification(classified: set[str], emitted: set[str], label: str) -> None:
    if classified != emitted:
        raise ValueError(
            f"frontend {label} classification mismatch; unclassified={sorted(emitted - classified)}, missing={sorted(classified - emitted)}"
        )


def _asset_scope(client_relative: str | None, initial: set[str], lazy: set[str]) -> str:
    return (
        "initial"
        if client_relative in initial
        else "lazy"
        if client_relative in lazy
        else "static"
    )


def _classify_asset(
    relative: str,
    initial_js: set[str],
    lazy_js: set[str],
    initial_css: set[str],
    lazy_css: set[str],
    initial_assets: set[str],
    lazy_assets: set[str],
) -> tuple[str, str]:
    client_relative = (
        Path(relative).relative_to("client").as_posix()
        if relative.startswith("client/")
        else None
    )
    direct = (
        (initial_js, "js", "initial"),
        (lazy_js, "js", "lazy"),
        (initial_css, "css", "initial"),
        (lazy_css, "css", "lazy"),
    )
    for members, category, scope in direct:
        if client_relative in members:
            return category, scope
    suffix = Path(relative).suffix.lower()
    if relative.startswith("server/") and suffix == ".js":
        return "js", "server"
    if relative == ".openai/hosting.json":
        return "deployment_metadata", "hosting"
    if client_relative is not None and suffix in {".eot", ".otf", ".ttf", ".woff", ".woff2"}:
        return "font", _asset_scope(client_relative, initial_assets, lazy_assets)
    if client_relative is not None and suffix in {
        ".avif",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".webp",
    }:
        return "image", _asset_scope(client_relative, initial_assets, lazy_assets)
    scope = (
        "initial"
        if client_relative == "index.html" or client_relative in initial_assets
        else "lazy"
        if client_relative in lazy_assets
        else "server"
        if relative.startswith("server/")
        else "metadata"
    )
    return "other", scope


def _asset_rows(dist: Path, emitted: set[str], *groups: set[str]) -> list[dict[str, Any]]:
    rows = []
    for relative in sorted(emitted):
        content = (dist / relative).read_bytes()
        category, scope = _classify_asset(relative, *groups)
        rows.append(
            {
                "name": relative,
                "area": relative.split("/", 1)[0],
                "category": category,
                "scope": scope,
                "bytes": len(content),
                "gzip_bytes": len(gzip.compress(content, compresslevel=9, mtime=0)),
            }
        )
    return rows


def _bundle_report(
    manifest_path: Path, repository_root: Path, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    def total(field: str, category: str | None = None, scope: str | None = None) -> int:
        return sum(
            int(row[field])
            for row in rows
            if (category is None or row["category"] == category)
            and (scope is None or row["scope"] == scope)
        )

    return {
        "manifest_path": str(manifest_path.relative_to(repository_root))
        if manifest_path.is_relative_to(repository_root)
        else str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "assets": rows,
        "initial_js_bytes": total("bytes", "js", "initial"),
        "initial_js_gzip_bytes": total("gzip_bytes", "js", "initial"),
        "lazy_js_bytes": total("bytes", "js", "lazy"),
        "lazy_js_gzip_bytes": total("gzip_bytes", "js", "lazy"),
        "initial_css_bytes": total("bytes", "css", "initial"),
        "initial_css_gzip_bytes": total("gzip_bytes", "css", "initial"),
        "lazy_css_bytes": total("bytes", "css", "lazy"),
        "lazy_css_gzip_bytes": total("gzip_bytes", "css", "lazy"),
        "server_js_bytes": total("bytes", "js", "server"),
        "server_js_gzip_bytes": total("gzip_bytes", "js", "server"),
        "font_bytes": total("bytes", "font"),
        "image_bytes": total("bytes", "image"),
        "deployment_metadata_bytes": total("bytes", "deployment_metadata"),
        "other_bytes": total("bytes", "other"),
        "total_js_bytes": total("bytes", "js"),
        "total_js_gzip_bytes": total("gzip_bytes", "js"),
        "total_emitted_bytes": total("bytes"),
        "unclassified_files": [],
        "unclassified_bytes": 0,
    }
