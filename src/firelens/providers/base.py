"""The intentionally narrow provider boundary used by domain code."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from firelens.contracts import (
    EmbeddingResponse,
    GenerationResponse,
    PlanningResponse,
    RerankResponse,
)


class AIProvider(Protocol):
    async def plan(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse: ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse: ...

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse: ...

    async def generate_grounded(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse: ...

    async def generate_background(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse: ...
