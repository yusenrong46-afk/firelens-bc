"""Request-scoped execution budgets for the V1.6 agent loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

MAX_TOOL_CALLS_PER_REQUEST = 4


def tool_fingerprint(name: str, arguments: dict[str, Any] | None) -> tuple[str, str]:
    """Normalize one tool call so identical dispatches can be rejected."""

    payload = arguments or {}
    return (
        name,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )


@dataclass
class RequestExecutionPolicy:
    """Bounded counters for one Ask. Never stores question or answer text."""

    route: str | None = None
    deadline: float | None = None
    tool_rounds_remaining: int = 2
    tool_calls_remaining: int = MAX_TOOL_CALLS_PER_REQUEST
    retrieval_cycles_remaining: int = 2
    planner_call_budget: int = 1
    embedding_budget: int = 6
    reranking_budget: int = 6
    grounded_generation_budget: int = 1
    outer_write_budget: int = 1
    rewrite_budget: int = 1
    cancelled: bool = False
    fallback_reason: str | None = None
    outer_chat_turns: int = 0
    grounded_generations: int = 0
    planner_calls: int = 0
    embedding_calls: int = 0
    rerank_calls: int = 0
    tool_rounds: int = 0
    tool_calls: int = 0
    refused_tool_calls: int = 0
    repeated_tool_dispatch: int = 0
    retrieval_cycles: int = 0
    cache_used: bool | None = None
    provider_stages: list[str] = field(default_factory=list)

    def record_stage(self, stage: str) -> None:
        if stage not in self.provider_stages:
            self.provider_stages.append(stage)

    def consume_outer_write(self) -> bool:
        if self.outer_write_budget <= 0:
            return False
        self.outer_write_budget -= 1
        self.outer_chat_turns += 1
        self.record_stage("outer_chat_turn")
        return True

    def consume_rewrite(self) -> bool:
        if self.rewrite_budget <= 0:
            return False
        self.rewrite_budget -= 1
        self.record_stage("outer_rewrite")
        return True

    def consume_grounded_generation(self) -> None:
        self.grounded_generations += 1
        if self.grounded_generation_budget > 0:
            self.grounded_generation_budget -= 1
        self.record_stage("grounded_generation")

    def consume_tool_round(self) -> bool:
        if self.tool_rounds_remaining <= 0:
            return False
        self.tool_rounds_remaining -= 1
        self.tool_rounds += 1
        return True

    def consume_tool_call(self) -> bool:
        if self.tool_calls_remaining <= 0:
            self.refused_tool_calls += 1
            if self.fallback_reason is None:
                self.fallback_reason = "tool_call_budget_exhausted"
            return False
        self.tool_calls_remaining -= 1
        self.tool_calls += 1
        return True

    def consume_retrieval_cycle(self) -> None:
        self.retrieval_cycles += 1
        if self.retrieval_cycles_remaining > 0:
            self.retrieval_cycles_remaining -= 1

    def as_counters(self) -> dict[str, int | str | None]:
        return {
            "route": self.route,
            "outer_chat_turns": self.outer_chat_turns,
            "grounded_generations": self.grounded_generations,
            "planner_calls": self.planner_calls,
            "embedding_calls": self.embedding_calls,
            "rerank_calls": self.rerank_calls,
            "tool_rounds": self.tool_rounds,
            "tool_calls": self.tool_calls,
            "refused_tool_calls": self.refused_tool_calls,
            "repeated_tool_dispatch": self.repeated_tool_dispatch,
            "retrieval_cycles": self.retrieval_cycles,
            "rewrites": int("outer_rewrite" in self.provider_stages),
            "fallback_reason": self.fallback_reason,
        }
