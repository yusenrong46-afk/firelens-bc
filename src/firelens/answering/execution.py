"""Typed private execution records used by benchmark runners."""

from dataclasses import dataclass, field

from firelens.answering.grounded import GenerationObservation
from firelens.contracts import (
    AskResponse,
    EvidencePacket,
    PlanningDecision,
    PlanningResponse,
    QueryPlan,
    RetrievalBundle,
    SearchResponse,
)


@dataclass(frozen=True)
class ExecutionObservation:
    """Typed stage measurements exposed to evaluation without trace parsing."""

    planning: PlanningResponse | None
    retrieval: RetrievalBundle


@dataclass(frozen=True)
class SearchExecution:
    """Private search result containing both public output and evaluation data."""

    public_response: SearchResponse
    evidence_packet: EvidencePacket | None
    observation: ExecutionObservation


@dataclass
class ExecutionObserver:
    """Per-request capture object used by benchmarks and safe for concurrent calls."""

    search: SearchExecution | None = None
    generations: list[GenerationObservation] = field(default_factory=list)


@dataclass(frozen=True)
class AskExecution:
    """Complete private execution record consumed by benchmark runners."""

    response: AskResponse
    plan: QueryPlan
    planning_decision: PlanningDecision | None
    retrieval: RetrievalBundle
    search: SearchExecution
    generations: tuple[GenerationObservation, ...]
