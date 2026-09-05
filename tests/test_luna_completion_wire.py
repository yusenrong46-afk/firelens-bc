"""Luna token-field migration: exact wire contract, with non-Luna controls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from rag_helpers import make_chunk, write_test_corpus

from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from firelens.providers import openrouter_operations
from firelens.providers.openrouter import OpenRouterProvider


@pytest.mark.parametrize("model", ["openai/gpt-5.6-luna", "other/model"])
@pytest.mark.parametrize("ceiling", [500, 1200, 1800])
def test_structured_completion_wire(tmp_path: Path, model: str, ceiling: int) -> None:
    async def run() -> None:
        config = write_test_corpus(tmp_path, [make_chunk("a", "water")]).model_copy(
            update={
                "openrouter_api_key": SecretStr("test-key"),
                "generation_model": model,
                "privacy": APPROVED_PRODUCTION_PRIVACY,
            }
        )
        messages = [{"role": "user", "content": "test"}]
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        luna = model == "openai/gpt-5.6-luna"

        def handler(request: httpx.Request) -> httpx.Response:
            expected = {
                "model": model,
                "messages": messages,
                "stream": False,
                "max_completion_tokens" if luna else "max_tokens": ceiling,
                "provider": {
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                    "zdr": True,
                    **({} if luna else {"require_parameters": True}),
                },
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "wire_probe",
                        "strict": True,
                        "schema": {**schema, **({"required": []} if luna else {})},
                    },
                },
                **({} if luna else {"temperature": config.generation_temperature}),
            }
            assert json.loads(request.content) == expected
            return httpx.Response(
                200, json={"model": model, "choices": [{"message": {"content": "{}"}}]}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await openrouter_operations.chat_json(
                OpenRouterProvider(config, client=client),
                messages,
                output_schema=schema,
                schema_name="wire_probe",
                max_tokens=ceiling,
                stage="grounded_generation",
            )

    asyncio.run(run())


@pytest.mark.parametrize("model", ["openai/gpt-5.6-luna", "other/model"])
@pytest.mark.parametrize("with_tools", [False, True])
def test_chat_completion_wire(tmp_path: Path, model: str, with_tools: bool) -> None:
    async def run() -> None:
        config = write_test_corpus(tmp_path, [make_chunk("a", "water")]).model_copy(
            update={
                "openrouter_api_key": SecretStr("test-key"),
                "generation_model": model,
                "privacy": APPROVED_PRODUCTION_PRIVACY,
            }
        )
        messages = [{"role": "user", "content": "test"}]
        tools = [{"type": "function", "function": {"name": "list_official_fires"}}]
        luna = model == "openai/gpt-5.6-luna"

        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content) == {
                "model": model,
                "messages": messages,
                "stream": False,
                "max_completion_tokens" if luna else "max_tokens": 1200,
                "provider": {
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                    "zdr": True,
                    **({} if luna else {"require_parameters": True}),
                },
                **({} if luna else {"temperature": config.generation_temperature}),
                **({"tools": tools, "tool_choice": "auto"} if with_tools else {}),
            }
            return httpx.Response(
                200, json={"model": model, "choices": [{"message": {"content": "test"}}]}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await OpenRouterProvider(config, client=client).chat_turn(
                messages, tools=tools if with_tools else None
            )

    asyncio.run(run())
