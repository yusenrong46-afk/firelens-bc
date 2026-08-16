"""Deterministic offline provider used by the normal test suite."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from typing import Any

from pydantic import HttpUrl

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
_QUESTION_STOPWORDS = {
    "about",
    "are",
    "does",
    "for",
    "from",
    "how",
    "the",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

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
            token
            for token in _TOKENS.findall(question_lower)
            if len(token) > 2 and token not in _QUESTION_STOPWORDS
        }
        grounded_terms = {
            "wildfire",
            "fire",
            "smoke",
            "evacuation",
            "alert",
            "order",
            "emergency",
            "bag",
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
        elif tokens & grounded_terms or len(distinctive_query_tokens & candidate_tokens) >= 2:
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
        evidence = payload["evidence"]
        items = evidence["items"]
        selected_items = [items[0]]
        question = str(
            payload.get("original_question") or payload.get("resolved_question") or ""
        ).casefold()
        if re.search(r"\b(?:stages|types|categories|levels|zones|steps)\b", question):
            by_source: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                by_source.setdefault(str(item["source_id"]), []).append(item)
            enumerated_groups = [group for group in by_source.values() if len(group) >= 3]
            if enumerated_groups:
                selected_items = max(enumerated_groups, key=len)
        candidates = [
            next(
                quote
                for quote in evidence["quote_candidates"]
                if quote["evidence_id"] == item["evidence_id"]
            )
            for item in selected_items
        ]
        draft = GroundedDraft(
            answer_type="grounded",
            claims=[
                DraftProposalClaim(
                    text=candidate["text"],
                    evidence_quote_ids=[candidate["quote_id"]],
                )
                for candidate in candidates
            ],
            limitations=evidence.get("limitations", []),
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

    async def chat_turn(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        from firelens.agent.chat import ChatToolCall, ChatTurn
        from firelens.agent.fallback_brain import fallback_write, heuristic_tool_calls
        from firelens.agent.packet import AgentPacket
        from firelens.contracts import (
            Freshness,
            LiveResult,
            LiveResultKind,
            MapContext,
            QueryRequest,
        )

        self.generate_calls += 1
        user_payload: dict[str, Any] = {}
        for message in messages:
            if message.get("role") != "user":
                continue
            raw = message.get("content")
            if not isinstance(raw, str):
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"question": raw}
            if isinstance(parsed, dict):
                user_payload = parsed
        question = str(user_payload.get("question") or "wildfire question")
        selected = user_payload.get("selected_live_result_id")
        request = QueryRequest(
            question=question,
            context=MapContext(
                selected_live_result_id=selected if isinstance(selected, str) else None
            ),
        )
        has_tool_results = any(message.get("role") == "tool" for message in messages)
        if tools and not has_tool_results:
            calls = heuristic_tool_calls(request)
            if not calls:
                return ChatTurn(
                    content=("That question is outside FireLens fire and preparedness sources.")
                )
            return ChatTurn(
                content=None,
                tool_calls=tuple(
                    ChatToolCall(
                        id=f"fake_{index}",
                        name=str(call["name"]),
                        arguments=dict(call.get("arguments") or {}),
                    )
                    for index, call in enumerate(calls)
                ),
            )
        packet = AgentPacket()
        official = (
            user_payload.get("official_packet") if isinstance(user_payload, dict) else None
        )
        records = official.get("official_records") if isinstance(official, dict) else None
        guidance_answer: str | None = None
        if not isinstance(records, list):
            records = []
            for message in messages:
                if message.get("role") != "tool":
                    continue
                raw = message.get("content")
                if not isinstance(raw, str):
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("records"), list):
                    records.extend(
                        item for item in payload["records"] if isinstance(item, dict)
                    )
                if isinstance(payload.get("answer"), str) and payload["answer"]:
                    guidance_answer = payload["answer"]
        if records:
            from datetime import UTC, datetime

            timestamp = datetime(2026, 8, 15, tzinfo=UTC)
            for index, row in enumerate(records):
                if not isinstance(row, dict):
                    continue
                coords = row.get("coordinates") or [-119.0, 50.0]
                kind_name = str(row.get("kind") or "incident")
                try:
                    kind = LiveResultKind(kind_name)
                except ValueError:
                    kind = LiveResultKind.INCIDENT
                packet.live_results.append(
                    LiveResult(
                        result_id=str(row.get("result_id") or f"incident:{index}"),
                        kind=kind,
                        source_url=HttpUrl("https://example.test/live/fake"),
                        source_updated_at=timestamp,
                        retrieved_at=timestamp,
                        freshness=Freshness.FRESH,
                        status=str(row.get("status") or "Official record"),
                        name=row.get("name"),
                        size_hectares=row.get("size_hectares"),
                        fire_centre=row.get("fire_centre"),
                        geometry={"type": "Point", "coordinates": coords},
                    )
                )
        if packet.live_results:
            return ChatTurn(content=fallback_write(request, packet))
        if guidance_answer:
            return ChatTurn(content=guidance_answer)
        return ChatTurn(content=fallback_write(request, packet))
