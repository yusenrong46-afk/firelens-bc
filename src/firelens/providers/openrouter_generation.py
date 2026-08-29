"""Configured model-specific wire details for the OpenRouter adapter."""

from __future__ import annotations

from typing import Any

from firelens.config import FireLensConfig
from firelens.providers.openrouter_support import strict_wire_schema


def model_id(config: FireLensConfig) -> str:
    return config.generation_model.split(":", maxsplit=1)[0]


def sampling_parameters(config: FireLensConfig) -> dict[str, float]:
    if model_id(config) == "openai/gpt-5.6-luna":
        return {}
    return {"temperature": config.generation_temperature}


def output_schema(config: FireLensConfig, schema: dict[str, Any]) -> dict[str, Any]:
    return strict_wire_schema(schema) if model_id(config) == "openai/gpt-5.6-luna" else schema
