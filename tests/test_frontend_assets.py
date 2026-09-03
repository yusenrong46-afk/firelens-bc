"""The deployed frontend is one complete, immutably cached asset set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from firelens.api.frontend import frontend_integrity_errors, install_frontend


def _build(root: Path, *, drop_chunk: bool = False) -> Path:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text(
        '<script type="module" src="/assets/index-AAAAAAAA.js"></script>'
        '<link rel="stylesheet" href="/assets/index-BBBBBBBB.css">',
        encoding="utf-8",
    )
    (assets / "index-AAAAAAAA.js").write_text("import('/assets/LiveMap-CCCCCCCC.js')")
    (assets / "index-BBBBBBBB.css").write_text("body{}")
    if not drop_chunk:
        (assets / "LiveMap-CCCCCCCC.js").write_text("export const LiveMap = 1")
    (assets / "firelens-mark.png").write_bytes(b"png")
    manifest = {
        "index.html": {
            "file": "assets/index-AAAAAAAA.js",
            "isEntry": True,
            "css": ["assets/index-BBBBBBBB.css"],
            "dynamicImports": ["src/features/near-me/LiveMap.tsx"],
        },
        "src/features/near-me/LiveMap.tsx": {"file": "assets/LiveMap-CCCCCCCC.js"},
    }
    (root / ".vite").mkdir()
    (root / ".vite/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_complete_build_has_no_integrity_errors(tmp_path: Path) -> None:
    assert frontend_integrity_errors(_build(tmp_path)) == []


def test_missing_lazy_chunk_is_named_before_anyone_gets_a_404(tmp_path: Path) -> None:
    errors = frontend_integrity_errors(_build(tmp_path, drop_chunk=True))
    assert errors == ["manifest names missing file assets/LiveMap-CCCCCCCC.js"]
    app = FastAPI()
    with pytest.raises(RuntimeError, match="LiveMap-CCCCCCCC.js"):
        install_frontend(app, tmp_path)


def test_hashed_assets_are_immutable_and_the_document_is_not(tmp_path: Path) -> None:
    app = FastAPI()
    install_frontend(app, _build(tmp_path))
    client = TestClient(app)
    chunk = client.get("/assets/LiveMap-CCCCCCCC.js")
    assert chunk.status_code == 200
    assert chunk.headers["cache-control"] == "public, max-age=31536000, immutable"
    mark = client.get("/assets/firelens-mark.png")
    assert mark.status_code == 200
    assert mark.headers["cache-control"] == "no-cache"
    assert client.get("/assets/LiveMap-ZZZZZZZZ.js").status_code == 404
    assert client.get("/").status_code == 200


def test_real_build_is_complete_when_present() -> None:
    dist = Path(__file__).resolve().parents[1] / "apps/web/dist/client"
    if not dist.joinpath("index.html").is_file():
        pytest.skip("frontend not built")
    assert frontend_integrity_errors(dist) == []
