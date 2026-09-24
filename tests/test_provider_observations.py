"""Content-free observations distinguish transport success from provider failure."""

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from firelens.config import FireLensConfig
from firelens.errors import ProviderError
from firelens.operational_logging import PROVIDER_CORRELATION, log_provider_attempt
from firelens.providers.openrouter import OpenRouterProvider


def events(caplog):
    return [
        json.loads(r.message)
        for r in caplog.records
        if r.name == "firelens.operations" and "firelens_provider_attempt" in r.message
    ]


@pytest.mark.parametrize("status", [200, 429])
def test_embedded_errors_are_observed_without_upstream_content(caplog, status):
    caplog.set_level(logging.INFO, logger="firelens.operations")
    secret = "private-upstream-content"
    config = FireLensConfig.from_env(Path.cwd()).model_copy(
        update={"openrouter_api_key": SecretStr(secret), "provider_max_attempts": 1}
    )
    body = {
        "error": {
            "code": 429,
            "message": secret,
            "metadata": {
                "provider_code": 429,
                "error_type": "rate_limit_exceeded",
                "limit_source": secret,
                "raw": secret,
            },
        }
    }

    async def run():
        token = PROVIDER_CORRELATION.set("a" * 32)
        try:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(status, json=body, headers={"Retry-After": "3"})
                )
            ) as client:
                with pytest.raises(ProviderError, match="rate limit"):
                    await OpenRouterProvider(config, client=client)._post(
                        "background_generation", "chat/completions", {"prompt": secret}
                    )
        finally:
            PROVIDER_CORRELATION.reset(token)

    asyncio.run(run())
    rows = events(caplog)
    assert [r["state"] for r in rows] == ["started", "completed"]
    assert rows[0]["attempt_id"] == rows[1]["attempt_id"]
    assert rows[1]["http_status"] == status
    assert rows[1]["embedded_error_code"] == 429
    assert rows[1]["provider_error_code"] == 429
    assert rows[1]["retry_after_seconds"] == 3
    assert rows[1]["outcome"] == "rate_limit"
    assert rows[1]["limit_source"] is None
    assert rows[1]["provider_correlation_id"] == "a" * 32
    assert secret not in json.dumps(rows)
    assert PROVIDER_CORRELATION.get() is None


@pytest.mark.parametrize("failure", ["timeout", "cancelled", "malformed"])
def test_terminal_failures_keep_attempt_accounting(caplog, failure):
    caplog.set_level(logging.INFO, logger="firelens.operations")
    config = FireLensConfig.from_env(Path.cwd()).model_copy(
        update={"openrouter_api_key": SecretStr("test"), "provider_max_attempts": 1}
    )

    async def handler(_):
        if failure == "timeout":
            raise httpx.ReadTimeout("private error")
        if failure == "cancelled":
            raise asyncio.CancelledError()
        return httpx.Response(200, text="private malformed response")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises((ProviderError, asyncio.CancelledError)):
                await OpenRouterProvider(config, client=client)._post(
                    "planning", "chat/completions", {}
                )

    asyncio.run(run())
    rows = events(caplog)
    assert len(rows) == 2
    assert rows[-1]["outcome"] == ("invalid_response" if failure == "malformed" else failure)
    assert "private" not in json.dumps(rows)


@pytest.mark.parametrize("cost", ["bad", 10**400, -1, None])
def test_retries_have_unique_ids_and_do_not_require_cost(caplog, cost):
    caplog.set_level(logging.INFO, logger="firelens.operations")
    config = FireLensConfig.from_env(Path.cwd()).model_copy(
        update={"openrouter_api_key": SecretStr("test"), "provider_retry_base_seconds": 0}
    )
    calls = 0

    def handler(_):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"error": {"code": 429}} if calls == 1 else {"usage": {"cost": cost}}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result, attempts = await OpenRouterProvider(config, client=client)._post(
                "planning", "chat/completions", {}
            )
            assert result == {"usage": {"cost": cost}} and attempts == 2

    asyncio.run(run())
    rows = [r for r in events(caplog) if r["state"] == "completed"]
    assert [r["attempt"] for r in rows] == [1, 2]
    assert len({r["attempt_id"] for r in rows}) == 2
    assert rows[-1]["outcome"] == "response_received"
    assert all(r["cost_usd"] is None for r in rows)


@pytest.mark.parametrize("value", ["secret-text", [], {}, True])
def test_malformed_metadata_is_not_serialized_or_blocking(caplog, value):
    caplog.set_level(logging.INFO, logger="firelens.operations")
    log_provider_attempt(
        stage="planning",
        attempt=1,
        attempt_id="a" * 32,
        state="completed",
        elapsed_ms=1,
        body={
            "error": {
                "code": value,
                "metadata": {
                    "provider_code": value,
                    "limit_source": value,
                    "error_type": value,
                },
            }
        },
    )
    row = events(caplog)[0]
    assert all(
        row[k] is None
        for k in ("embedded_error_code", "provider_error_code", "limit_source", "error_type")
    )
    assert "secret-text" not in json.dumps(row)


def test_transport_latency_excludes_semaphore_wait(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="firelens.operations")
    config = FireLensConfig.from_env(Path.cwd()).model_copy(
        update={
            "openrouter_api_key": SecretStr("test"),
            "provider_max_concurrency": 1,
            "provider_adaptive_min_concurrency": 1,
        }
    )

    clock = [0.0]
    monkeypatch.setattr("firelens.providers.openrouter.monotonic", lambda: clock[0])

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
        ) as client:
            provider = OpenRouterProvider(config, client=client)
            await provider._semaphore.acquire()
            task = asyncio.create_task(
                provider._post_attempt("planning", "chat/completions", {})
            )
            await asyncio.sleep(0)
            assert not events(caplog)
            clock[0] = 100.0
            provider._semaphore.release()
            await task

    asyncio.run(run())
    assert events(caplog)[-1]["elapsed_ms"] == 0


def test_public_error_logs_link_attempts_and_reset_correlation(caplog, monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from firelens.api.answer_routes import install_answer_routes
    from firelens.contracts import AskResponse

    caplog.set_level(logging.INFO, logger="firelens.operations")
    response = AskResponse(status="error", trace_id="f" * 32, error_kind="rate_limit")
    policy = SimpleNamespace(
        provider_stages=("background_generation",),
        tool_rounds=0,
        outer_chat_turns=0,
        retrieval_cycles=0,
        cache_used=False,
        fallback_reason=None,
    )

    async def answer(_):
        log_provider_attempt(
            stage="background_generation",
            attempt=1,
            attempt_id="b" * 32,
            state="completed",
            elapsed_ms=1,
            http_status=200,
            body={"error": {"code": 429}},
            outcome="rate_limit",
        )
        return SimpleNamespace(
            response=response, route=SimpleNamespace(value="related"), policy=policy, tools=()
        )

    monkeypatch.setattr(
        "firelens.api.answer_routes.FireLensAgent",
        lambda *_: SimpleNamespace(answer=answer),
    )
    runtime = SimpleNamespace(service=object(), corpus_version=None, bound_candidate=None)
    app = FastAPI()
    install_answer_routes(app, FireLensConfig.from_env(Path.cwd()), lambda: runtime, None)
    with TestClient(app) as client:
        result = client.post("/api/v1/ask", json={"question": "Explain wildfire weather."})
    assert result.status_code == 503
    assert result.json()["trace_id"] == "f" * 32
    logged = [json.loads(r.message) for r in caplog.records if r.name == "firelens.operations"]
    request = next(r for r in logged if r["event"] == "firelens_request")
    attempt = next(r for r in logged if r["event"] == "firelens_provider_attempt")
    assert request["trace_id"] == result.json()["trace_id"]
    assert request["provider_correlation_id"] == attempt["provider_correlation_id"]
    assert len(request["provider_correlation_id"]) == 32
    assert PROVIDER_CORRELATION.get() is None
