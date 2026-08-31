"""Regression locks for empty official results authorized by an agent plan."""

from __future__ import annotations

from types import SimpleNamespace

from firelens.agent.compose import compose_response
from firelens.agent.packet import AgentPacket
from firelens.contracts import (
    CoarseResolvedLocation,
    LiveResultKind,
    QueryRequest,
    ResponseMode,
)


def test_authorized_empty_live_plan_stays_an_explicit_no_match_response() -> None:
    """A successful zero-result lookup must not be reclassified from question text."""

    response = compose_response(
        QueryRequest(question="Anything I gotta worry about around Kamloops?"),
        AgentPacket(
            query_plan=SimpleNamespace(
                live_layers=(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
            ),
            resolved_location=CoarseResolvedLocation(latitude=50.67, longitude=-120.33),
        ),
        "No live record was returned.",
    )

    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert response.response_mode == ResponseMode.LIVE
    assert "no matching official wildfire records" in public
    assert "not an all-clear" in public
    assert "outside firelens" not in public
