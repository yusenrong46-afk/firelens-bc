"""Focused readiness and adapter-boundary regressions for V1.6."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr
from rag_helpers import make_chunk

from firelens.agent.packet import AgentPacket
from firelens.agent.prefetch import resolve_place
from firelens.agent.runtime_tools import execute_tool
from firelens.config import FireLensConfig
from firelens.errors import ToolInputError
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime


class _StateProvider:
    def __init__(self, state: str) -> None:
        self.state = state

    def operational_state(self) -> str:
        return self.state


def _production_runtime(tmp_path: Path, state: str) -> Runtime:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "production",
            "privacy": APPROVED_PRODUCTION_PRIVACY,
            "openrouter_api_key": SecretStr("test-key"),
        }
    )
    runtime = Runtime(
        config=config,
        chunks=(make_chunk("ready-chunk", "Reviewed guidance."),),
        corpus_version="test-corpus.v1",
        service=cast(Any, object()),
        provider_configured=True,
        provider=cast(Any, _StateProvider(state)),
        zdr_policy_state="required_stages_eligible",
    )
    runtime.embedding_zdr_state = "eligible"
    runtime.generation_zdr_state = "eligible"
    runtime.reranking_zdr_state = "zdr_optional"
    return runtime


@pytest.mark.parametrize("state", ["configured_unprobed", "degraded", "circuit_open"])
def test_production_readiness_requires_available_provider_state(
    tmp_path: Path, state: str
) -> None:
    health = _production_runtime(tmp_path, state).health()

    assert health.provider_state == state
    assert health.status == "not_ready"


def test_local_fixture_readiness_does_not_require_network_preflight(tmp_path: Path) -> None:
    config = FireLensConfig.from_env(tmp_path)
    runtime = Runtime(
        config=config,
        chunks=(make_chunk("ready-chunk", "Reviewed guidance."),),
        corpus_version="test-corpus.v1",
        service=cast(Any, object()),
        provider_configured=True,
        provider=cast(Any, _StateProvider("configured_unprobed")),
    )

    assert runtime.health().status == "ready"


def test_successful_zdr_preflight_marks_health_provider_available_without_model_call(
    tmp_path: Path,
) -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"model_id": "openai/text-embedding-3-small"},
                    {"model_id": "openai/gpt-5.6-luna"},
                ]
            },
        )

    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "production",
            "privacy": APPROVED_PRODUCTION_PRIVACY,
            "openrouter_api_key": SecretStr("test-key"),
            "openrouter_base_url": "https://openrouter.test/api/v1",
            "embedding_model": "openai/text-embedding-3-small",
            "generation_model": "openai/gpt-5.6-luna",
        }
    )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenRouterProvider(config, client=client)
            assert provider.operational_state() == "configured_unprobed"
            report = await provider.preflight_zdr()
            runtime = Runtime(
                config=config,
                chunks=(make_chunk("ready-chunk", "Reviewed guidance."),),
                corpus_version="test-corpus.v1",
                service=cast(Any, object()),
                provider_configured=True,
                provider=provider,
            )
            runtime.apply_zdr_preflight(report, failed=False)
            assert runtime.health().provider_state == "available"
            assert runtime.health().status == "ready"

    asyncio.run(exercise())
    assert requests == [("GET", "/api/v1/endpoints/zdr")]


def test_location_resolver_programming_error_is_not_silently_ignored() -> None:
    class BrokenLiveService:
        async def resolve_location(self, _location: object) -> tuple[float, float]:
            raise TypeError("adapter contract drift")

    class Coordinator:
        live_service = BrokenLiveService()

    from firelens.contracts import LocationInput, QueryRequest

    with pytest.raises(TypeError, match="adapter contract drift"):
        asyncio.run(
            resolve_place(
                cast(Any, Coordinator()),
                QueryRequest(
                    question="What is burning near Kelowna?",
                    location=LocationInput(label="Kelowna"),
                ),
                AgentPacket(),
            )
        )


def test_unknown_runtime_tool_uses_domain_input_error() -> None:
    class Coordinator:
        live_service = object()

    from firelens.contracts import QueryRequest

    with pytest.raises(ToolInputError):
        asyncio.run(
            execute_tool(
                "not_a_tool",
                {},
                request=QueryRequest(question="test"),
                live_coordinator=cast(Any, Coordinator()),
                static_service=None,
                packet=AgentPacket(),
            )
        )
