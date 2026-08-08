"""Manifest-complete frontend bundle accounting for release qualification."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def measure_frontend_bundle(dist: Path, *, repository_root: Path) -> dict[str, Any]:
    """Measure every emitted frontend artifact using the Vite dependency graph."""

    client = dist / "client"
    manifest_path = client / ".vite/manifest.json"
    if not manifest_path.is_file():
        raise ValueError("frontend Vite manifest is missing; bundle size cannot be measured")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("frontend Vite manifest is empty or invalid")
    entries = [key for key, item in manifest.items() if item.get("isEntry") is True]
    if len(entries) != 1:
        raise ValueError("frontend Vite manifest must contain exactly one entry")

    def closure(keys: list[str], *, follow_dynamic: bool) -> set[str]:
        visited: set[str] = set()
        pending = list(keys)
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            item = manifest.get(key)
            if not isinstance(item, dict):
                raise ValueError(f"frontend manifest references an unknown entry: {key}")
            visited.add(key)
            imports = item.get("imports") or []
            if not isinstance(imports, list) or not all(
                isinstance(value, str) for value in imports
            ):
                raise ValueError(f"frontend manifest imports are invalid for {key}")
            pending.extend(imports)
            if follow_dynamic:
                dynamic = item.get("dynamicImports") or []
                if not isinstance(dynamic, list) or not all(
                    isinstance(value, str) for value in dynamic
                ):
                    raise ValueError(f"frontend manifest dynamic imports are invalid for {key}")
                pending.extend(dynamic)
        return visited

    initial_chunks = closure(entries, follow_dynamic=False)
    all_chunks = closure(entries, follow_dynamic=True)

    def referenced_files(keys: set[str], field: str) -> set[str]:
        files: set[str] = set()
        for key in keys:
            item = manifest[key]
            if field == "file":
                values = [item.get("file")]
            else:
                values = item.get(field) or []
                if not isinstance(values, list):
                    raise ValueError(f"frontend manifest {field} is invalid for {key}")
            if not all(value is None or isinstance(value, str) for value in values):
                raise ValueError(f"frontend manifest {field} is invalid for {key}")
            files.update(value for value in values if value)
        return files

    initial_js = {
        value for value in referenced_files(initial_chunks, "file") if value.endswith(".js")
    }
    all_js = {value for value in referenced_files(all_chunks, "file") if value.endswith(".js")}
    lazy_js = all_js - initial_js
    initial_css = referenced_files(initial_chunks, "css")
    all_css = referenced_files(all_chunks, "css")
    lazy_css = all_css - initial_css
    initial_assets = referenced_files(initial_chunks, "assets")
    all_assets = referenced_files(all_chunks, "assets")
    lazy_assets = all_assets - initial_assets

    required_runtime_artifacts = {"server/index.js", ".openai/hosting.json"}
    emitted_files = {
        path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()
    }
    missing_runtime_artifacts = sorted(required_runtime_artifacts - emitted_files)
    if missing_runtime_artifacts:
        raise ValueError(
            "frontend build is missing required server/hosting artifacts: "
            f"{missing_runtime_artifacts}"
        )
    client_emitted_files = {
        path.relative_to(client).as_posix() for path in client.rglob("*") if path.is_file()
    }
    emitted_js = {relative for relative in client_emitted_files if relative.endswith(".js")}
    emitted_css = {relative for relative in client_emitted_files if relative.endswith(".css")}
    if not initial_js:
        raise ValueError("frontend Vite manifest entry does not emit JavaScript")
    if initial_js & lazy_js or initial_css & lazy_css:
        raise ValueError("frontend JavaScript was classified as both initial and lazy")
    if all_js != emitted_js:
        missing = sorted(emitted_js - all_js)
        unknown = sorted(all_js - emitted_js)
        raise ValueError(
            f"frontend JavaScript classification mismatch; unclassified={missing}, missing={unknown}"
        )
    if all_css != emitted_css:
        missing = sorted(emitted_css - all_css)
        unknown = sorted(all_css - emitted_css)
        raise ValueError(
            f"frontend CSS classification mismatch; unclassified={missing}, missing={unknown}"
        )
    missing_manifest_assets = sorted((all_assets | all_css | all_js) - client_emitted_files)
    if missing_manifest_assets:
        raise ValueError(
            f"frontend manifest assets are missing from build output: {missing_manifest_assets}"
        )

    rows: list[dict[str, Any]] = []
    font_extensions = {".eot", ".otf", ".ttf", ".woff", ".woff2"}
    image_extensions = {".avif", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
    for relative in sorted(emitted_files):
        path = dist / relative
        suffix = path.suffix.lower()
        client_relative = (
            Path(relative).relative_to("client").as_posix()
            if relative == "client" or relative.startswith("client/")
            else None
        )
        if client_relative in initial_js:
            category, scope = "js", "initial"
        elif client_relative in lazy_js:
            category, scope = "js", "lazy"
        elif client_relative in initial_css:
            category, scope = "css", "initial"
        elif client_relative in lazy_css:
            category, scope = "css", "lazy"
        elif relative.startswith("server/") and suffix == ".js":
            category, scope = "js", "server"
        elif relative == ".openai/hosting.json":
            category, scope = "deployment_metadata", "hosting"
        elif client_relative is not None and suffix in font_extensions:
            category = "font"
            scope = (
                "initial"
                if client_relative in initial_assets
                else "lazy"
                if client_relative in lazy_assets
                else "static"
            )
        elif client_relative is not None and suffix in image_extensions:
            category = "image"
            scope = (
                "initial"
                if client_relative in initial_assets
                else "lazy"
                if client_relative in lazy_assets
                else "static"
            )
        else:
            category = "other"
            scope = (
                "initial"
                if client_relative == "index.html" or client_relative in initial_assets
                else "lazy"
                if client_relative in lazy_assets
                else "server"
                if relative.startswith("server/")
                else "metadata"
            )
        content = path.read_bytes()
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

    if {row["name"] for row in rows} != emitted_files:
        raise ValueError("frontend build output contains unclassified files")

    def total(field: str, *, category: str | None = None, scope: str | None = None) -> int:
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
        "initial_js_bytes": total("bytes", category="js", scope="initial"),
        "initial_js_gzip_bytes": total("gzip_bytes", category="js", scope="initial"),
        "lazy_js_bytes": total("bytes", category="js", scope="lazy"),
        "lazy_js_gzip_bytes": total("gzip_bytes", category="js", scope="lazy"),
        "initial_css_bytes": total("bytes", category="css", scope="initial"),
        "initial_css_gzip_bytes": total("gzip_bytes", category="css", scope="initial"),
        "lazy_css_bytes": total("bytes", category="css", scope="lazy"),
        "lazy_css_gzip_bytes": total("gzip_bytes", category="css", scope="lazy"),
        "server_js_bytes": total("bytes", category="js", scope="server"),
        "server_js_gzip_bytes": total("gzip_bytes", category="js", scope="server"),
        "font_bytes": total("bytes", category="font"),
        "image_bytes": total("bytes", category="image"),
        "deployment_metadata_bytes": total("bytes", category="deployment_metadata"),
        "other_bytes": total("bytes", category="other"),
        "total_js_bytes": total("bytes", category="js"),
        "total_js_gzip_bytes": total("gzip_bytes", category="js"),
        "total_emitted_bytes": total("bytes"),
        "unclassified_files": [],
        "unclassified_bytes": 0,
    }
