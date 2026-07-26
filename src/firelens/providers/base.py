"""The intentionally narrow provider boundary used by domain code."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from firelens.contracts import EmbeddingResponse, GenerationResponse, RerankResponse


class AIProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse: ...

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse: ...

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse: ...
