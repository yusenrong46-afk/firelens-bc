"""Default traces and public API errors must not echo private request content."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError
from rag_helpers import make_runtime

from firelens.agent.failures import shout_unexpected
from firelens.answering.service import StaticRAGService
from firelens.api.middleware import install_exception_handlers
from firelens.config import FireLensConfig
from firelens.contracts import ConversationTurn, QueryRequest
from firelens.errors import UnexpectedProgrammingError
from firelens.live_contracts import LocationInput
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from firelens.traces import TraceRecorder

PRIVATE_QUESTION = "What belongs in an emergency kit?"
HISTORY_CANARY = "PRIVATE-HISTORY-CANARY"
COORDINATE_CANARY = "49.282749"
LONGITUDE_CANARY = "-123.120735"
INPUT_CANARY = "PRIVATE-CANARY-INPUT"
PRIVATE_CANARY = "PRIVATE-CANARY-SECRET"
ANSWER_CANARY = "PRIVATE-ANSWER-CANARY"
HOSTILE_EVENT_CANARY = "private-hostile-event-canary-7f91d3"
LOCATION_ERROR = "introduces or substitutes an unsupported location: Kelowna"


def _unsalted_digest(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _service(
    runtime, provider, config, *, environment: str, trace_dir: Path
) -> StaticRAGService:
    payload = config.model_dump()
    payload.update(
        {
            "deployment_environment": environment,
            "trace_dir": trace_dir,
            "trace_content": False,
        }
    )
    if environment == "production":
        payload["privacy"] = APPROVED_PRODUCTION_PRIVACY.model_dump()
    return StaticRAGService(
        runtime.service.chunks,
        corpus_version=runtime.service.corpus_version,
        retrieval=runtime.service.retrieval,
        provider=provider,
        config=FireLensConfig.model_validate(payload),
    )


def _app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app, FireLensConfig.from_env(tmp_path))

    @app.post("/api/v1/ask")
    async def ask(body: QueryRequest) -> dict[str, str]:
        del body
        return {"status": "ok"}

    return app


@pytest.mark.parametrize("environment", ["local", "preview", "production"])
def test_default_traces_omit_content_and_unsalted_digests(
    tmp_path: Path, environment: str
) -> None:
    async def _run() -> None:
        runtime, provider, config = await make_runtime(tmp_path)
        traces = tmp_path / f"traces-{environment}"
        service = _service(runtime, provider, config, environment=environment, trace_dir=traces)
        response = await service.ask(
            QueryRequest(
                question=PRIVATE_QUESTION,
                history=[ConversationTurn(role="user", content=HISTORY_CANARY)],
                location=LocationInput(latitude=49.282749, longitude=-123.120735),
            )
        )
        payload = json.loads((traces / f"{response.trace_id}.json").read_text())
        blob = json.dumps(payload)
        assert "question" not in payload
        assert PRIVATE_QUESTION not in blob
        assert HISTORY_CANARY not in blob
        assert COORDINATE_CANARY not in blob
        assert LONGITUDE_CANARY not in blob
        assert _unsalted_digest(PRIVATE_QUESTION) not in blob

    asyncio.run(_run())


def test_hostile_event_strings_and_digest_are_not_persisted(tmp_path: Path) -> None:
    async def _run() -> None:
        trace_id = "f" * 32
        recorder = TraceRecorder(tmp_path / "hostile-traces")
        written = await recorder.record(
            trace_id,
            question=HOSTILE_EVENT_CANARY,
            payload={
                "operation": HOSTILE_EVENT_CANARY,
                "route": HOSTILE_EVENT_CANARY,
                "relation": HOSTILE_EVENT_CANARY,
                "support": HOSTILE_EVENT_CANARY,
                "status": HOSTILE_EVENT_CANARY,
                "response_mode": HOSTILE_EVENT_CANARY,
                "reason_code": HOSTILE_EVENT_CANARY,
                "error_kind": HOSTILE_EVENT_CANARY,
                "model": HOSTILE_EVENT_CANARY,
                "versions": {
                    "corpus": HOSTILE_EVENT_CANARY,
                    HOSTILE_EVENT_CANARY: HOSTILE_EVENT_CANARY,
                },
                "provider_models": {
                    "embedding": HOSTILE_EVENT_CANARY,
                    HOSTILE_EVENT_CANARY: HOSTILE_EVENT_CANARY,
                },
                "cited_evidence_ids": [HOSTILE_EVENT_CANARY],
                "stage_rankings": {
                    "bm25": [HOSTILE_EVENT_CANARY],
                    HOSTILE_EVENT_CANARY: [HOSTILE_EVENT_CANARY],
                },
                "stage_counts": {"bm25": 3, HOSTILE_EVENT_CANARY: 99},
                "timings_ms": {"bm25": 4.0, HOSTILE_EVENT_CANARY: 99.0},
                "provider_attempts": {"embedding": 2, HOSTILE_EVENT_CANARY: 99},
                "provider_usage": {
                    "embedding": {
                        "prompt_tokens": 6,
                        HOSTILE_EVENT_CANARY: 99,
                    },
                    HOSTILE_EVENT_CANARY: {"prompt_tokens": 99},
                },
                "generation_usage": {
                    "completion_tokens": 7,
                    HOSTILE_EVENT_CANARY: 99,
                },
                "errors": [HOSTILE_EVENT_CANARY],
                "validation": {
                    "accepted": False,
                    "errors": [HOSTILE_EVENT_CANARY],
                },
            },
        )
        payload = json.loads((tmp_path / "hostile-traces" / f"{trace_id}.json").read_text())
        blob = json.dumps(payload)
        event = payload["events"][0]

        assert written
        assert HOSTILE_EVENT_CANARY not in blob
        assert _unsalted_digest(HOSTILE_EVENT_CANARY) not in blob
        assert {
            "model",
            "versions",
            "provider_models",
            "cited_evidence_ids",
            "stage_rankings",
        }.isdisjoint(event)
        assert event["generation_model_present"] is True
        assert event["version_present"] == {"corpus": True}
        assert event["provider_model_present"] == {"embedding": True}
        assert event["cited_evidence_count"] == 1
        assert event["stage_ranking_counts"]["bm25"] == 1
        assert event["stage_counts"] == {"bm25": 3}
        assert event["timings_ms"] == {"bm25": 4.0}
        assert event["provider_attempts"] == {"embedding": 2}
        assert event["provider_usage"] == {"embedding": {"prompt_tokens": 6}}
        assert event["generation_usage"] == {"completion_tokens": 7}
        assert event["error_count"] == 1
        assert event["validation"] == {"accepted": False, "error_count": 1}

    asyncio.run(_run())


def test_appending_trace_preserves_prior_safe_diagnostics_without_content(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        trace_id = "d" * 32
        directory = tmp_path / "append-traces"
        recorder = TraceRecorder(directory)
        await recorder.record(
            trace_id,
            question=HOSTILE_EVENT_CANARY,
            payload={
                "operation": "search",
                "versions": {"corpus": HOSTILE_EVENT_CANARY},
                "provider_models": {"embedding": HOSTILE_EVENT_CANARY},
                "stage_rankings": {"bm25": [HOSTILE_EVENT_CANARY]},
            },
        )
        path = directory / f"{trace_id}.json"
        before = json.loads(path.read_text(encoding="utf-8"))["events"][0]

        await recorder.record(
            trace_id,
            question=HOSTILE_EVENT_CANARY,
            payload={"operation": "ask", "status": "answer"},
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        blob = json.dumps(payload)

        assert payload["events"][0] == before
        assert before["version_present"] == {"corpus": True}
        assert before["provider_model_present"] == {"embedding": True}
        assert before["stage_ranking_counts"]["bm25"] == 1
        assert HOSTILE_EVENT_CANARY not in blob
        assert _unsalted_digest(HOSTILE_EVENT_CANARY) not in blob

    asyncio.run(_run())


def test_explicit_local_trace_content_keeps_question_without_digest(tmp_path: Path) -> None:
    async def _run() -> None:
        trace_id = "e" * 32
        recorder = TraceRecorder(tmp_path / "local-debug-traces", include_content=True)
        written = await recorder.record(
            trace_id,
            question=PRIVATE_QUESTION,
            payload={"operation": "ask"},
        )
        payload = json.loads((tmp_path / "local-debug-traces" / f"{trace_id}.json").read_text())
        assert written
        assert payload["question"] == PRIVATE_QUESTION
        assert "question_sha256" not in payload
        assert _unsalted_digest(PRIVATE_QUESTION) not in json.dumps(payload)

    asyncio.run(_run())


def test_validation_error_text_is_not_copied_into_default_traces(tmp_path: Path) -> None:
    async def _run() -> None:
        runtime, provider, config = await make_runtime(tmp_path)
        traces = tmp_path / "traces-validation"
        service = _service(runtime, provider, config, environment="local", trace_dir=traces)
        request = QueryRequest(question=PRIVATE_QUESTION)
        response = await service.ask(request)
        await service._record_ask(
            request,
            response,
            route="related",
            validation={"accepted": False, "errors": [LOCATION_ERROR]},
            answer=ANSWER_CANARY,
        )
        blob = (traces / f"{response.trace_id}.json").read_text()
        assert LOCATION_ERROR not in blob
        assert ANSWER_CANARY not in blob
        assert "unsupported location" not in blob.casefold()

    asyncio.run(_run())


def test_preview_rejects_trace_content_while_production_already_does(
    tmp_path: Path,
) -> None:
    dumped = FireLensConfig.from_env(tmp_path).model_dump()
    production = dict(dumped)
    production["deployment_environment"] = "production"
    production["privacy"] = APPROVED_PRODUCTION_PRIVACY.model_dump()
    production["trace_content"] = True
    with pytest.raises(ValidationError, match="cannot persist"):
        FireLensConfig.model_validate(production)
    preview = dict(dumped)
    preview["deployment_environment"] = "preview"
    preview["trace_content"] = True
    with pytest.raises(ValidationError, match="cannot persist"):
        FireLensConfig.model_validate(preview)


def test_request_validation_does_not_echo_submitted_values(tmp_path: Path) -> None:
    async def _run() -> None:
        transport = httpx.ASGITransport(app=_app(tmp_path))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            extra = await client.post(
                "/api/v1/ask",
                json={"question": PRIVATE_QUESTION, "injected": INPUT_CANARY},
            )
            coords = await client.post(
                "/api/v1/ask",
                json={
                    "question": "Where are the current wildfires in Kelowna?",
                    "location": {
                        "latitude": 49.282749,
                        "longitude": -123.120735,
                        "label": "SECRET-PLACE",
                    },
                },
            )
            valid = await client.post("/api/v1/ask", json={"question": PRIVATE_QUESTION})
        assert extra.status_code == 400
        assert INPUT_CANARY not in str(extra.json())
        assert all(set(detail) == {"loc", "type"} for detail in extra.json()["details"])
        assert coords.status_code == 400
        assert COORDINATE_CANARY not in str(coords.json())
        assert "SECRET-PLACE" not in str(coords.json())
        assert valid.status_code == 200
        assert valid.json() == {"status": "ok"}

    asyncio.run(_run())


def test_response_validation_is_consumed_without_echoing_rejected_values(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class PublicResponse(BaseModel):
        status: str

    app = FastAPI()
    install_exception_handlers(app, FireLensConfig.from_env(tmp_path))

    @app.get("/api/v1/ask", response_model=PublicResponse)
    async def malformed_response() -> dict[str, object]:
        return {"status": {"private": PRIVATE_CANARY}}

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/ask")

        assert response.status_code == 500
        assert response.json()["error_kind"] == "unexpected_programming_error"
        assert PRIVATE_CANARY not in response.text
        assert PRIVATE_CANARY not in caplog.text

    caplog.set_level(logging.DEBUG)
    asyncio.run(_run())


@pytest.mark.parametrize("environment", ["local", "preview", "production"])
def test_unexpected_logs_omit_exception_message_and_canary(
    caplog: pytest.LogCaptureFixture, environment: str
) -> None:
    caplog.set_level(logging.DEBUG)
    try:
        raise RuntimeError(PRIVATE_CANARY)
    except RuntimeError as exc:
        classified = shout_unexpected(exc, environment=environment)
    assert isinstance(classified, UnexpectedProgrammingError)
    assert PRIVATE_CANARY not in classified.public_message
    assert PRIVATE_CANARY not in caplog.text
