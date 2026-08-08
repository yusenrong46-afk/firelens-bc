"""SPA asset compatibility routes and static frontend mounting."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _entry_response(frontend: Path, asset_hash: str, suffix: str) -> Response:
    if re.fullmatch(r"[A-Za-z0-9_-]+", asset_hash) is None:
        return Response(status_code=404)
    assets = frontend / "assets"
    requested = assets / f"index-{asset_hash}.{suffix}"
    candidate = requested if requested.is_file() else None
    if candidate is None:
        index_html = frontend.joinpath("index.html").read_text(encoding="utf-8")
        match = re.search(
            rf'(?:src|href)=["\']/assets/'
            rf'(index-[A-Za-z0-9_-]+\.{re.escape(suffix)})["\']',
            index_html,
        )
        if match is not None:
            current = assets / match.group(1)
            candidate = current if current.is_file() else None
    if candidate is None:
        return Response(status_code=404)
    media_type = "text/javascript" if suffix == "js" else "text/css"
    return FileResponse(
        candidate,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


def install_frontend(app: FastAPI, frontend: Path | None) -> None:
    if frontend is None or not frontend.joinpath("index.html").is_file():
        return

    @app.get("/assets/index-{asset_hash}.js", include_in_schema=False)
    async def frontend_javascript_entry(asset_hash: str) -> Response:
        return _entry_response(frontend, asset_hash, "js")

    @app.get("/assets/index-{asset_hash}.css", include_in_schema=False)
    async def frontend_stylesheet_entry(asset_hash: str) -> Response:
        return _entry_response(frontend, asset_hash, "css")

    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
