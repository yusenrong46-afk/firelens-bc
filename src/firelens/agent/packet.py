"""This-turn official and reviewed facts passed to Luna and the output rail."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from firelens.agent.budget import RequestExecutionPolicy
from firelens.contracts import (
    AnswerSection,
    AskResponse,
    CoarseResolvedLocation,
    LiveResult,
    LiveResultKind,
    RelatedLink,
)


def live_record_fact(result: LiveResult) -> dict[str, Any]:
    """Compact official fields for the model. Raw coordinates are omitted."""

    from firelens.answering.live_analysis import official_display_name

    return {
        "result_id": result.result_id,
        "kind": result.kind.value,
        "name": official_display_name(result),
        "status": result.status,
        "incident_number": result.incident_number,
        "size_hectares": result.size_hectares,
        "fire_centre": result.fire_centre,
        "fire_zone": result.fire_zone,
        "authority": result.authority,
        "distance_km": result.distance_km,
        "distance_basis": result.distance_basis,
        "geometry_relation": result.geometry_relation.value,
        "source_updated_at": result.source_updated_at.isoformat(),
        "retrieved_at": result.retrieved_at.isoformat(),
        "freshness": result.freshness.value
        if hasattr(result.freshness, "value")
        else str(result.freshness),
    }


@dataclass
class AgentPacket:
    """Facts collected this turn. Not a user-content log."""

    live_results: list[LiveResult] = field(default_factory=list)
    static_response: AskResponse | None = None
    tool_names: list[str] = field(default_factory=list)
    unknown_topics: list[str] = field(default_factory=list)
    resolved_location: CoarseResolvedLocation | None = None
    related_links: list[RelatedLink] = field(default_factory=list)
    roster_total: int | None = None
    unavailable_layers: list[LiveResultKind] = field(default_factory=list)
    live_limitations: list[str] = field(default_factory=list)
    retrieved_at: datetime | None = None
    policy: RequestExecutionPolicy = field(default_factory=RequestExecutionPolicy)
    tool_fingerprints: list[tuple[str, str]] = field(default_factory=list)
    query_plan: Any | None = None

    @property
    def boundaries(self) -> tuple[AnswerSection, ...]:
        """Clauses the plan declined or cannot serve, each owed its own section."""

        return tuple(getattr(self.query_plan, "boundaries", ()) or ())

    def mark_unavailable(
        self, layers: tuple[LiveResultKind, ...] | list[LiveResultKind]
    ) -> None:
        for kind in layers:
            if kind not in self.unavailable_layers:
                self.unavailable_layers.append(kind)

    def add_live_limitation(self, limitation: str | None) -> None:
        """Retain a bounded, source-owned live-query qualification."""

        if limitation and limitation not in self.live_limitations:
            self.live_limitations.append(limitation)

    def allowed_names(self) -> set[str]:
        from firelens.answering.live_analysis import official_display_name

        names = {official_display_name(item).casefold() for item in self.live_results}
        names.update(
            (item.incident_number or "").casefold()
            for item in self.live_results
            if item.incident_number
        )
        return {name for name in names if name}

    def allowed_result_ids(self) -> set[str]:
        return {item.result_id for item in self.live_results}

    def facts_for_model(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "official_records": [live_record_fact(item) for item in self.live_results],
            "unknown_topics": list(self.unknown_topics),
        }
        if self.static_response is not None and self.static_response.answer:
            payload["reviewed_guidance_answer"] = self.static_response.answer
        if self.unavailable_layers:
            payload["unavailable_layers"] = [kind.value for kind in self.unavailable_layers]
        return payload
