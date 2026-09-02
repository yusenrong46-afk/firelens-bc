"""Typed LLM planning and generation envelopes."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from firelens.contract_base import FrozenStrictModel


class PlanningResponse(FrozenStrictModel):
    model: str
    decision: Any
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)


class GenerationResponse(FrozenStrictModel):
    model: str
    draft: Any
    usage: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
