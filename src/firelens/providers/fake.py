"""Deterministic offline provider used by the normal test suite."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Sequence

from firelens.contracts import (
    DraftAnswer,
    DraftProposalClaim,
    EmbeddingResponse,
    GenerationResponse,
    RerankResponse,
    RerankResult,
)


_TOKENS = re.compile(r"[a-z0-9]+")


class FakeProvider:
    """A predictable provider that performs no network calls."""

    def __init__(self, *, dimensions: int = 64) -> None:
        self.dimensions = dimensions
        self.embed_calls = 0
        self.rerank_calls = 0
        self.generate_calls = 0

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        for token in _TOKENS.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            values[index] += 1.0
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values] if norm else values

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        self.embed_calls += 1
        return EmbeddingResponse(
            model="fake/embedding",
            vectors=[self._vector(text) for text in texts],
        )

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse:
        self.rerank_calls += 1
        query_terms = set(_TOKENS.findall(query.lower()))
        scored = []
        for index, document in enumerate(documents):
            terms = set(_TOKENS.findall(document.lower()))
            overlap = len(query_terms & terms)
            score = overlap / max(1, len(query_terms))
            scored.append((score, index))
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))[:top_n]
        return RerankResponse(
            model="fake/reranker",
            results=[
                RerankResult(index=index, relevance_score=score)
                for score, index in ranked
            ],
        )

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        del output_schema
        self.generate_calls += 1
        payload = json.loads(messages[-1]["content"])
        item = payload["evidence"]["items"][0]
        candidate = next(
            quote
            for quote in payload["evidence"]["quote_candidates"]
            if quote["evidence_id"] == item["evidence_id"]
        )
        quote = candidate["text"]
        draft = DraftAnswer(
            answer_type="guidance",
            answer=quote,
            claims=[
                DraftProposalClaim(
                    text=quote,
                    evidence_quote_ids=[candidate["quote_id"]],
                )
            ],
            limitations=payload["evidence"].get("limitations", []),
            requires_live_verification=False,
        )
        return GenerationResponse(model="fake/generator", draft=draft)
