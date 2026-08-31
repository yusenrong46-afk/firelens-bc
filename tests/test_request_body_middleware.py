"""ASGI request-body bounding keeps guarded request bodies replayable."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, Request

from firelens.api.middleware import install_middlewares
from firelens.request_guard import AnonymousRequestGuard


def _app(*, max_body_bytes: int = 16, limit: int = 10) -> FastAPI:
    app = FastAPI()
    guard = AnonymousRequestGuard(
        limit=limit,
        window_seconds=60,
        max_body_bytes=max_body_bytes,
        secret=b"request-body-test-secret",
    )
    install_middlewares(app, guard)

    @app.post("/api/v1/ask")
    async def echo_body(request: Request) -> dict[str, object]:
        parsed = await request.json()
        replayed = await request.body()
        return {"parsed": parsed, "replayed": replayed.decode("utf-8")}

    return app


async def _post(
    app: FastAPI,
    content: bytes | AsyncIterator[bytes],
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post("/api/v1/ask", content=content, headers=headers)


def test_bounded_body_replays_to_downstream_at_exact_limit() -> None:
    body = b'{"value":"1234"}'
    assert len(body) == 16

    response = asyncio.run(
        _post(
            _app(),
            body,
            headers={"content-type": "application/json", "content-length": str(len(body))},
        )
    )

    assert response.status_code == 200
    assert response.json() == {"parsed": {"value": "1234"}, "replayed": '{"value":"1234"}'}
    assert response.headers["x-ratelimit-remaining"] == "9"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chunked_overflow_stops_at_rejecting_chunk() -> None:
    yielded = 0

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal yielded
        yielded += 1
        yield b"{" + b"x" * 9
        yielded += 1
        yield b"y" * 8
        yielded += 1
        raise AssertionError("body reader consumed beyond overflow")

    response = asyncio.run(
        _post(_app(), chunks(), headers={"content-type": "application/json"})
    )

    assert response.status_code == 413
    assert response.json()["error_kind"] == "request_too_large"
    assert yielded == 2


def test_invalid_declared_length_fails_before_body_consumption() -> None:
    consumed = False

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal consumed
        consumed = True
        yield b"{}"

    response = asyncio.run(
        _post(
            _app(),
            chunks(),
            headers={"content-type": "application/json", "content-length": "not-a-number"},
        )
    )

    assert response.status_code == 400
    assert response.json()["error_kind"] == "invalid_request"
    assert not consumed


def test_oversized_declared_length_keeps_error_and_security_contract() -> None:
    response = asyncio.run(
        _post(
            _app(),
            b"{}",
            headers={"content-type": "application/json", "content-length": "17"},
        )
    )

    assert response.status_code == 413
    assert response.json()["error_kind"] == "request_too_large"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
