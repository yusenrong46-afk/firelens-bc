"""Individual source defects cannot erase valid records or manufacture completeness."""

import asyncio
from typing import Any, cast

import httpx
import pytest
from test_live import _locality_feature, _metadata

from firelens.agent import FireLensAgent
from firelens.contracts import LiveResultKind, LocationInput, QueryRequest
from firelens.live import LiveDataService
from firelens.live_answering import LiveAnswerCoordinator

EVAC = LiveResultKind.EVACUATION


def feature(number=1, status="Order", invalid=False):
    ring = [[-120.4, 50.6], [-120.3, 50.6], [-120.3, 50.7], [-120.4, 50.7], [-120.4, 50.6]]
    if invalid:
        ring = [ring[0], ring[2], ring[1], ring[3], ring[0]]
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": number,
            "ORDER_ALERT_STATUS": status,
            "EVENT_NAME": f"Example {number}",
            "EVENT_TYPE": "Wildfire",
            "ISSUING_AGENCY": "Test authority",
            "DATE_MODIFIED": 1_760_000_000_000,
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


class Feed:
    def __init__(self, features):
        self.features = features
        self.offline = False

    def __call__(self, request):
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        if "geocoder" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "features": [_locality_feature("Kamloops", coordinates=[-120.34, 50.68])]
                },
            )
        if not request.url.path.endswith("/query"):
            return httpx.Response(200, json=_metadata(EVAC))
        if request.url.params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": len(self.features)})
        return httpx.Response(
            200, json={"type": "FeatureCollection", "features": self.features}
        )


@pytest.mark.parametrize(
    "statuses, expected, partial",
    [
        ((), 1, True),
        (("order",), 1, False),
        (("alert",), 0, True),
        (("order", "alert"), 1, True),
    ],
)
def test_status_admission_precedes_geometry(statuses, expected, partial):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(Feed([feature(), feature(2, "Alert", True)]))
        ) as client:
            result = await LiveDataService(client=client).nearby_page(
                LocationInput(latitude=50.68, longitude=-120.34),
                layers=(EVAC,),
                evacuation_statuses=statuses,
            )
        assert len(result.results) == expected
        assert result.partial_layers == ([EVAC] if partial else [])
        assert result.unavailable_layers == []
        assert result.layer_statuses[0].available
        assert result.pagination.total_results == expected
        assert result.layer_statuses[0].omitted_geometry_count == int(partial)

    asyncio.run(run())


@pytest.mark.parametrize(
    "rows, expected_omitted", [([], 0), ([feature(status="Unexpected")], 1)]
)
def test_empty_is_distinct_from_unknown_status(rows, expected_omitted):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(Feed(rows))) as client:
            result = await LiveDataService(client=client).nearby_page(
                LocationInput(latitude=50.68, longitude=-120.34),
                layers=(EVAC,),
                evacuation_statuses=("order",),
            )
        assert result.results == []
        assert result.layer_statuses[0].omitted_status_count == expected_omitted
        assert bool(result.partial_layers) == bool(expected_omitted)

    asyncio.run(run())


class NoStatic:
    provider = None

    async def ask(self, *args, **kwargs):
        raise AssertionError("Live lookup must not use a paid model or static retrieval")


@pytest.mark.parametrize(
    "question, partial, count",
    [
        ("Evacuation orders near Kamloops", False, 1),
        ("Evacuation alerts near Kamloops", True, 0),
        ("Show evacuation orders and alerts near Kamloops", True, 1),
        ("Show evacuation alerts across BC", True, 0),
        ("How many evacuation records are there across BC?", True, 1),
        ("Which evacuation order or alert is nearest to Kamloops?", True, 1),
    ],
)
def test_real_agent_prefetch_retains_partial_and_prevents_complete_claims(
    question, partial, count
):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(Feed([feature(), feature(2, "Alert", True)]))
        ) as client:
            result = await FireLensAgent(
                cast(Any, NoStatic()), LiveAnswerCoordinator(LiveDataService(client=client))
            ).answer(QueryRequest(question=question))
        response = result.response
        assert len(response.live_results) == count
        assert bool(response.partial_layers) == partial
        if partial:
            assert response.roster_total is None
            assert "incomplete" in response.answer.lower()
            assert "not an all-clear" in response.answer.lower()
            assert "no evacuation" not in response.answer.lower()
            assert "nearest to farthest" not in response.answer.lower()
            assert "partial" in response.status_banner.availability_label.lower()
            assert "incomplete" in response.history_text.lower()

    asyncio.run(run())


def test_partial_cached_refresh_and_source_recovery():
    async def run():
        feed = Feed([feature(), feature(2, "Alert", True)])
        async with httpx.AsyncClient(transport=httpx.MockTransport(feed)) as client:
            service = LiveDataService(client=client, fresh_seconds=0)
            location = LocationInput(latitude=50.68, longitude=-120.34)
            initial = await service.nearby_page(location, layers=(EVAC,))
            feed.offline = True
            stale = await service.nearby_page(location, layers=(EVAC,))
            assert stale.partial_layers == initial.partial_layers == [EVAC]
            assert stale.aggregate_freshness.value == "stale"
            assert (
                stale.layer_statuses[0].retrieved_at == initial.layer_statuses[0].retrieved_at
            )
            feed.offline = False
            feed.features[1] = feature(2, "Alert")
            recovered = await service.nearby_page(location, layers=(EVAC,))
            assert not recovered.partial_layers
            assert len(recovered.results) == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "rows", [[feature(), feature(2, "Alert", True)], [feature(2, "Alert", True)]]
)
def test_legacy_coordinator_preserves_partial_state(rows):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(Feed(rows))) as client:
            result = await LiveAnswerCoordinator(LiveDataService(client=client)).answer(
                QueryRequest(question="Show evacuation orders and alerts near Kamloops"), None
            )
        assert result.partial_layers == [EVAC]
        assert result.roster_total is None
        assert "incomplete" in result.answer.lower()
        assert "no evacuation" not in result.answer.lower()

    asyncio.run(run())
