"""Source failure reasons survive the adapter, agent, and public answer."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from test_live import _metadata

from firelens.agent.compose import compose_response
from firelens.agent.packet import AgentPacket
from firelens.agent.runtime_tools import _record_successful_live_response
from firelens.answering.live_response_support import empty_live_response
from firelens.contracts import (
    CoarseResolvedLocation,
    LiveResultKind,
    LocationInput,
    QueryRequest,
)
from firelens.live import LiveDataService


@pytest.mark.parametrize("page", [False, True])
def test_native_invalid_boundary_survives_to_evacuation_answer(page):
    asyncio.run(_native_invalid_boundary_survives_to_evacuation_answer(page))


async def _native_invalid_boundary_survives_to_evacuation_answer(page):
    kind = LiveResultKind.EVACUATION
    payload = json.loads(
        (Path(__file__).parent / "fixtures/arcgis/evacuation-2026-09-07.json").read_text()
    )

    def handler(request):
        if not request.url.path.endswith("/query"):
            return httpx.Response(200, json=_metadata(kind))
        if request.url.params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": len(payload["features"])})
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = LiveDataService(client=client)
        lookup = service.nearby_page if page else service.nearby_results
        result = await lookup(LocationInput(latitude=50.68, longitude=-120.34), layers=(kind,))
    assert result.results == []
    assert result.unavailable_layers == [kind]
    assert result.layer_statuses[0].unavailability_reason == "invalid_geometry"
    packet = AgentPacket(
        resolved_location=CoarseResolvedLocation(latitude=50.68, longitude=-120.34)
    )
    _record_successful_live_response(packet, result)
    response = compose_response(
        QueryRequest(question="Are there evacuation orders near Kamloops?"), packet, ""
    )
    public = " ".join([response.answer or "", *response.limitations]).lower()
    assert "firelens reached emergencyinfobc" in public
    assert "boundaries could not be validated" in public
    assert "near kamloops" in public
    assert "could not reach" not in public
    assert "no evacuation" not in public
    assert "not an all-clear" in public
    assert response.response_mode.value == "abstention"
    assert response.related_links[0].title == "EmergencyInfoBC"
    assert response.status_banner.official_escalation_title == "EmergencyInfoBC"


@pytest.mark.parametrize("invalid", [[], [LiveResultKind.EVACUATION]])
def test_failure_reason_does_not_claim_missing_layer_is_empty(invalid):
    response = empty_live_response(
        requested_layers=(LiveResultKind.INCIDENT, LiveResultKind.EVACUATION),
        unavailable_layers=[LiveResultKind.EVACUATION],
        invalid_geometry_layers=invalid,
        resolved_location=CoarseResolvedLocation(latitude=50.68, longitude=-120.34),
        retrieved_at=datetime.now(UTC),
        place="Kamloops",
    )
    public = response.answer.lower()
    assert "no fires are listed" in public
    assert "no evacuation" not in public
    assert "could not reach" not in public
    assert ("boundaries could not be validated" in public) == bool(invalid)
    assert "not an all-clear" in public


def test_network_failure_does_not_claim_invalid_geometry():
    asyncio.run(_network_failure_does_not_claim_invalid_geometry())


async def _network_failure_does_not_claim_invalid_geometry():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await LiveDataService(client=client).map_results(
            layers=(LiveResultKind.EVACUATION,)
        )
    assert result.layer_statuses[0].unavailability_reason is None
    packet = AgentPacket()
    _record_successful_live_response(packet, result)
    assert packet.invalid_geometry_layers == []
