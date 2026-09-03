"""Static frontend serving with immutable hashed assets and a build integrity check.

The SPA is one document (``index.html``, never cached) plus content-hashed
files under ``/assets`` (cached forever). Every deploy is a complete, internally
consistent set: the Vite manifest is checked against the files on disk before
the app will serve it, so a build that lost a lazy chunk fails at startup
instead of returning 404s to people. A browser that still holds a previous
entry file recovers client-side (see ``vite:preloadError`` in ``main.tsx``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

HASHED_ASSET = re.compile(r"^[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
IMMUTABLE = "public, max-age=31536000, immutable"
MANIFEST_RELATIVE_PATH = ".vite/manifest.json"


def frontend_integrity_errors(frontend: Path) -> list[str]:
    """Return every way this build is not a complete, self-consistent set.

    Checks that ``index.html`` exists and only references assets that exist,
    and that every file the Vite manifest names (entries, CSS, static assets,
    and lazily imported chunks) is present on disk.
    """

    errors: list[str] = []
    index_html = frontend / "index.html"
    if not index_html.is_file():
        return [f"{index_html} is missing"]
    html = index_html.read_text(encoding="utf-8")
    for referenced in sorted(
        set(re.findall(r'(?:src|href)=["\']/(assets/[^"\']+)["\']', html))
    ):
        if not frontend.joinpath(referenced).is_file():
            errors.append(f"index.html references missing {referenced}")
    manifest_path = frontend / MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        errors.append(f"{MANIFEST_RELATIVE_PATH} is missing; build with manifest: true")
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [*errors, f"{MANIFEST_RELATIVE_PATH} is not valid JSON: {exc}"]
    if not isinstance(manifest, dict) or not manifest:
        return [*errors, f"{MANIFEST_RELATIVE_PATH} is empty"]
    referenced_files: set[str] = set()
    for key, entry in manifest.items():
        if not isinstance(entry, dict):
            errors.append(f"manifest entry {key} is malformed")
            continue
        file = entry.get("file")
        if isinstance(file, str):
            referenced_files.add(file)
        for field in ("css", "assets"):
            for item in entry.get(field, ()) or ():
                if isinstance(item, str):
                    referenced_files.add(item)
        for field in ("imports", "dynamicImports"):
            for item in entry.get(field, ()) or ():
                if isinstance(item, str) and item not in manifest:
                    errors.append(f"manifest entry {key} imports unknown chunk {item}")
    for file in sorted(referenced_files):
        if not frontend.joinpath(file).is_file():
            errors.append(f"manifest names missing file {file}")
        elif file.startswith("assets/") and HASHED_ASSET.match(Path(file).name) is None:
            errors.append(f"asset {file} is not content-hashed and cannot be cached immutably")
    return errors


class HashedAssets(StaticFiles):
    """Serve ``/assets``; content-hashed files are immutable, anything else is not cached."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            hashed = HASHED_ASSET.match(Path(path).name) is not None
            response.headers["Cache-Control"] = IMMUTABLE if hashed else "no-cache"
        return response


def install_frontend(app: FastAPI, frontend: Path | None) -> None:
    if frontend is None or not frontend.joinpath("index.html").is_file():
        return
    errors = frontend_integrity_errors(frontend)
    if errors:
        raise RuntimeError(
            "frontend build is not a complete asset set: " + "; ".join(errors[:5])
        )
    app.mount("/assets", HashedAssets(directory=frontend / "assets"), name="frontend-assets")
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
