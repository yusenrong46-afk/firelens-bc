"""Deterministic offline provider used by the normal test suite."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from typing import Any

from firelens.contracts import (
    BACKGROUND_LIMITATION,
    BackgroundDraft,
    BackgroundDraftClaim,
    DocumentContextDraft,
    DocumentContextItem,
    DocumentContextResponse,
    DraftProposalClaim,
    EmbeddingResponse,
    GenerationResponse,
    GroundedDraft,
    PlanningDecision,
    PlanningResponse,
    QueryRelation,
    RerankResponse,
    RerankResult,
)

_TOKENS = re.compile(r"[a-z0-9]+")

# The fake planner represents deterministic control-flow behaviour, not model
# intelligence.  These low-risk explanatory concepts deliberately exercise the
# background branch in offline tests; live-provider benchmarks measure whether
# the configured planner makes the same semantic distinction in practice.
_ADJACENT_CONCEPT_PATTERNS = (
    r"\bember shower\b",
    r"\bwind\b.{0,40}\bspread\b",
    r"\brelative humidity\b",
    r"\bhepa\b",
    r"\b(?:flaming )?combustion\b",
    r"\bsmouldering\b",
    r"\bdry vegetation\b",
    r"\btemperature inversion\b",
    r"\bradiant heat\b",
    r"\bconifer needles\b",
    r"\btiny particles\b",
)


class FakeProvider:
    """A predictable provider that performs no network calls."""

    def __init__(self, *, dimensions: int = 64) -> None:
        self.dimensions = dimensions
        self.plan_calls = 0
        self.embed_calls = 0
        self.rerank_calls = 0
        self.generate_calls = 0

    async def plan(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse:
        del output_schema
        self.plan_calls += 1
        payload = json.loads(messages[-1]["content"])
        question = str(payload["question"])
        history = payload.get("history") or []
        context = " ".join([*(str(item.get("content", "")) for item in history), question])
        question_lower = question.lower()
        tokens = set(_TOKENS.findall(context.lower()))
        candidate_tokens = {
            token
            for candidate in payload.get("untrusted_corpus_candidates") or []
            for token in _TOKENS.findall(
                " ".join(str(value) for value in candidate.values()).lower()
            )
        }
        distinctive_query_tokens = {
            token for token in _TOKENS.findall(question_lower) if len(token) > 2
        }
        grounded_terms = {
            "wildfire",
            "fire",
            "smoke",
            "evacuation",
            "alert",
            "order",
            "emergency",
            "kit",
            "firesmart",
            "ember",
            "combustible",
            "sprinkler",
            "rank",
            "control",
        }
        adjacent_terms = {"forest", "burn", "flame", "preparedness", "disaster"}
        if any(re.search(pattern, question_lower) for pattern in _ADJACENT_CONCEPT_PATTERNS):
            relation = QueryRelation.ADJACENT
            queries = [context.strip()[:2_000]]
        elif tokens & grounded_terms or distinctive_query_tokens & candidate_tokens:
            relation = QueryRelation.GROUNDED_CANDIDATE
            queries = [context.strip()[:2_000]]
        elif tokens & adjacent_terms:
            relation = QueryRelation.ADJACENT
            queries = [context.strip()[:2_000]]
        else:
            relation = QueryRelation.TANGENT
            queries = []
        return PlanningResponse(
            model="fake/planner",
            decision=PlanningDecision(
                relation=relation,
                retrieval_queries=queries,
                explanation="Deterministic offline planning result.",
            ),
        )

    async def generate_contexts(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> DocumentContextResponse:
        del output_schema
        payload = json.loads(messages[-1]["content"])
        items = []
        for chunk in payload["chunks"]:
            context = (
                f"This passage comes from {payload['document_title']} and belongs to the "
                f"section {chunk.get('section') or 'general guidance'}. It provides reviewed "
                "wildfire preparedness information whose exact wording remains in the raw passage "
                "and should be used only to improve retrieval, never as citation evidence."
            )
            items.append(DocumentContextItem(chunk_id=chunk["chunk_id"], context=context))
        return DocumentContextResponse(
            model="fake/context-generator",
            draft=DocumentContextDraft(items=items),
        )

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
                RerankResult(index=index, relevance_score=score) for score, index in ranked
            ],
        )

    async def generate_grounded(
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
        draft = GroundedDraft(
            answer_type="grounded",
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

    async def generate_background(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        del messages, output_schema
        self.generate_calls += 1
        return GenerationResponse(
            model="fake/generator",
            draft=BackgroundDraft(
                answer_type="background",
                claims=[
                    BackgroundDraftClaim(
                        text="This is general explanatory background related to wildfire preparedness."
                    )
                ],
                limitations=[BACKGROUND_LIMITATION],
            ),
        )
