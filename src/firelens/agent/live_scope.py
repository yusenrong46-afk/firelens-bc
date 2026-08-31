"""Packet-level location qualifications for composed official responses."""

from __future__ import annotations

from firelens.agent.packet import AgentPacket
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import QueryRequest
from firelens.live_support import (
    official_fire_centre_from_question,
    official_fire_centre_label,
    regional_reference_point_limitation,
)


def packet_scope_limitations(request: QueryRequest, packet: AgentPacket) -> list[str]:
    """Derive public-safe regional qualifications from the request and packet."""

    location = request.location or coarse_location_from_question(request.question)
    if not packet.live_results:
        return []
    limitations: list[str] = []
    if location is not None:
        regional_limitation = regional_reference_point_limitation(location)
        if regional_limitation is not None:
            limitations.append(regional_limitation)
    fire_centre = (
        official_fire_centre_label(location.label)
        if location is not None
        else official_fire_centre_from_question(request.question)
    )
    if fire_centre is not None and all(
        result.fire_centre is not None
        and result.fire_centre.casefold() == fire_centre.casefold()
        for result in packet.live_results
    ):
        limitations.append(
            f"Results are filtered to the official BC Wildfire Service {fire_centre} label."
        )
    return limitations
