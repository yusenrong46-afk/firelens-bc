from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from rag_helpers import make_chunk, write_test_corpus

from firelens.config import FireLensConfig
from firelens.errors import ProviderError
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from firelens.providers.openrouter import OpenRouterProvider
from firelens.providers.openrouter_support import CHAT_STAGES


def test_generation_provider_subset_config_and_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FIRELENS_GENERATION_PROVIDER_ONLY", raising=False)
    assert FireLensConfig.from_env(tmp_path).generation_provider_only == ()
    (tmp_path / ".env").write_text("FIRELENS_GENERATION_PROVIDER_ONLY=vendor/region-a\n")
    assert FireLensConfig.from_env(tmp_path).generation_provider_only == ("vendor/region-a",)
    monkeypatch.setenv(
        "FIRELENS_GENERATION_PROVIDER_ONLY", " vendor/region-b, vendor/region-c "
    )
    config = FireLensConfig.from_env(tmp_path)
    assert config.generation_provider_only == ("vendor/region-b", "vendor/region-c")
    assert FireLensConfig.model_validate_json(config.model_dump_json()) == config


def test_generation_subset_only_changes_chat_routing(tmp_path: Path) -> None:
    asyncio.run(_capture_generation_subset(tmp_path))


async def _capture_generation_subset(tmp_path: Path) -> None:
    config = write_test_corpus(tmp_path, [make_chunk("a", "water")]).model_copy(
        update={"privacy": APPROVED_PRODUCTION_PRIVACY, "openrouter_api_key": SecretStr("fake")}
    )
    observed = []

    def reject(request: httpx.Request) -> httpx.Response:
        observed.append((request.url.path, json.loads(request.content)))
        return httpx.Response(400, json={"error": {"message": "offline wire capture"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
        baseline = OpenRouterProvider(config, client=client)
        narrowed = OpenRouterProvider(
            config.model_copy(update={"generation_provider_only": ("vendor/region-a",)}),
            client=client,
        )
        for stage in CHAT_STAGES:
            before = baseline._provider_preferences(stage)
            assert "only" not in before
            assert narrowed._provider_preferences(stage) == {
                **before,
                "only": ["vendor/region-a"],
            }
        for stage in ("embedding", "reranking"):
            assert narrowed._provider_preferences(stage) == baseline._provider_preferences(
                stage
            )
        for call in (
            narrowed.embed(["water"]),
            narrowed.rerank("water", ["passage"], top_n=1),
            narrowed.plan([{"role": "user", "content": "plan"}], output_schema={}),
        ):
            with pytest.raises(ProviderError):
                await call
    assert len(observed) == 3
    for path, body in observed:
        preferences = body["provider"]
        assert preferences["data_collection"] == "deny"
        assert preferences["allow_fallbacks"] is False
        if path.endswith("/chat/completions"):
            assert preferences["only"] == ["vendor/region-a"]
            assert preferences["zdr"] is True
            assert "require_parameters" not in preferences
        else:
            assert "only" not in preferences
            assert preferences["require_parameters"] is True
            assert preferences.get("zdr") is (True if path.endswith("/embeddings") else None)
