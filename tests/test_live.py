from __future__ import annotations

import unittest
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from firelens.contracts import (
    Freshness,
    GeometryRelation,
    LiveResultKind,
    LocationInput,
)
from firelens.live import LiveDataService, geometry_relation


def _metadata(kind: LiveResultKind, *, updated: int = 1_760_000_000_000) -> dict:
    definitions = {
        LiveResultKind.INCIDENT: (
            "BCWS_ActiveFires_Points",
            ["OBJECTID", "FIRE_STATUS", "FIRE_NUMBER", "INCIDENT_NAME"],
        ),
        LiveResultKind.PERIMETER: (
            "Fire Perimeters",
            ["OBJECTID", "FIRE_STATUS", "FIRE_NUMBER", "FIRE_SIZE_HECTARES"],
        ),
        LiveResultKind.EVACUATION: (
            "Evacuation Orders and Alerts - View",
            ["OBJECTID", "ORDER_ALERT_STATUS", "EVENT_TYPE", "DATE_MODIFIED"],
        ),
    }
    name, fields = definitions[kind]
    return {
        "name": name,
        "editingInfo": {"dataLastEditDate": updated},
        "fields": [{"name": field} for field in fields],
    }


def _kind_from_url(request: httpx.Request) -> LiveResultKind:
    url = str(request.url)
    if "Evacuation_Orders_and_Alerts" in url:
        return LiveResultKind.EVACUATION
    if "FirePerimeters" in url:
        return LiveResultKind.PERIMETER
    return LiveResultKind.INCIDENT


class LocationContractTests(unittest.TestCase):
    def test_coordinates_are_coarsened(self) -> None:
        location = LocationInput(latitude=49.2827, longitude=-123.1207)
        self.assertEqual((location.latitude, location.longitude), (49.28, -123.12))

    def test_exact_address_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            LocationInput(label="123 Main Street")


class GeometryTests(unittest.TestCase):
    def test_boundary_counts_as_inside(self) -> None:
        polygon = {
            "type": "Polygon",
            "coordinates": [[[-124, 49], [-123, 49], [-123, 50], [-124, 50], [-124, 49]]],
        }
        self.assertEqual(
            geometry_relation(polygon, latitude=49.5, longitude=-124, radius_km=5),
            GeometryRelation.INSIDE,
        )

    def test_polygon_hole_is_not_inside(self) -> None:
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [[-124, 49], [-122, 49], [-122, 51], [-124, 51], [-124, 49]],
                [
                    [-123.6, 49.6],
                    [-123.4, 49.6],
                    [-123.4, 49.8],
                    [-123.6, 49.8],
                    [-123.6, 49.6],
                ],
            ],
        }
        self.assertNotEqual(
            geometry_relation(polygon, latitude=49.7, longitude=-123.5, radius_km=1),
            GeometryRelation.INSIDE,
        )

    def test_multipolygon_and_malformed_geometry(self) -> None:
        multipolygon = {
            "type": "MultiPolygon",
            "coordinates": [[[[-124, 49], [-123, 49], [-123, 50], [-124, 50], [-124, 49]]]],
        }
        self.assertEqual(
            geometry_relation(multipolygon, latitude=49.5, longitude=-123.5, radius_km=1),
            GeometryRelation.INSIDE,
        )
        self.assertEqual(
            geometry_relation(
                {"type": "Polygon", "coordinates": []}, latitude=49, longitude=-123, radius_km=1
            ),
            GeometryRelation.UNKNOWN,
        )


class LiveDataServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_nearby_results_keep_records_with_unknown_geometry(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.EVACUATION))
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "OBJECTID": 12,
                                "ORDER_ALERT_STATUS": "Order",
                                "EVENT_TYPE": "Wildfire",
                                "DATE_MODIFIED": 1_760_000_000_000,
                            },
                            "geometry": {"type": "Polygon", "coordinates": []},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).nearby_results(
                LocationInput(latitude=49.5, longitude=-123.5),
                layers=(LiveResultKind.EVACUATION,),
            )

        self.assertEqual([result.result_id for result in response.results], ["evacuation:12"])
        self.assertEqual(response.results[0].geometry_relation, GeometryRelation.UNKNOWN)
        self.assertTrue(any("could not be located" in item for item in response.limitations))

    async def test_repeated_full_page_fails_closed_instead_of_looping(self) -> None:
        calls = 0
        features = [
            {
                "type": "Feature",
                "properties": {"OBJECTID": index, "FIRE_STATUS": "Out of Control"},
                "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
            }
            for index in range(1_000)
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            calls += 1
            self.assertEqual(request.url.params.get("orderByFields"), "OBJECTID ASC")
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "exceededTransferLimit": True,
                    "features": features,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client, max_pages=3).map_results(
                layers=(LiveResultKind.INCIDENT,)
            )

        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.INCIDENT])
        self.assertEqual(calls, 2)

    async def test_cache_becomes_visibly_stale_after_refresh_failure(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls > 2:
                raise httpx.ReadTimeout("offline")
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "OBJECTID": 7,
                                "FIRE_STATUS": "Out of Control",
                                "INCIDENT_NAME": "Test Fire",
                                "IGNITION_DATE": 1_750_000_000_000,
                            },
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(
                client=client, fresh_seconds=0, stale_if_error_seconds=900
            )
            first = await service.map_results(layers=(LiveResultKind.INCIDENT,))
            second = await service.map_results(layers=(LiveResultKind.INCIDENT,))
        self.assertEqual(first.results[0].freshness, Freshness.FRESH)
        self.assertEqual(second.results[0].freshness, Freshness.STALE)
        self.assertEqual(first.results[0].result_id, second.results[0].result_id)
        self.assertEqual(
            first.results[0].source_updated_at,
            datetime.fromtimestamp(1_760_000_000, UTC),
        )

    async def test_expired_stale_cache_fails_closed(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls > 2:
                raise httpx.ReadTimeout("offline")
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"OBJECTID": 7, "FIRE_STATUS": "Out of Control"},
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client, fresh_seconds=0, stale_if_error_seconds=0)
            first = await service.map_results(layers=(LiveResultKind.INCIDENT,))
            second = await service.map_results(layers=(LiveResultKind.INCIDENT,))
        self.assertEqual(len(first.results), 1)
        self.assertEqual(second.results, [])
        self.assertEqual(second.unavailable_layers, [LiveResultKind.INCIDENT])

    async def test_paginated_results_and_partial_layer_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            kind = _kind_from_url(request)
            if kind == LiveResultKind.EVACUATION:
                return httpx.Response(200, json={"unexpected": []})
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(kind))
            offset = int(request.url.params.get("resultOffset", "0"))
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "exceededTransferLimit": offset == 0,
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "OBJECTID": offset + 1,
                                "FIRE_STATUS": "Out of Control",
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [-123.5 + offset, 49.5],
                            },
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.INCIDENT, LiveResultKind.EVACUATION)
            )
        self.assertEqual(
            [result.result_id for result in response.results], ["incident:1", "incident:2"]
        )
        self.assertEqual(response.unavailable_layers, [LiveResultKind.EVACUATION])

    async def test_inactive_and_non_wildfire_records_are_not_displayed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            kind = _kind_from_url(request)
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(kind))
            is_evacuation = kind == LiveResultKind.EVACUATION
            if is_evacuation:
                properties = {
                    "OBJECTID": 8,
                    "ORDER_ALERT_STATUS": "Alert",
                    "EVENT_TYPE": "Landslide",
                    "DATE_MODIFIED": 1_750_000_000_000,
                }
            else:
                properties = {
                    "OBJECTID": 7,
                    "FIRE_STATUS": "Out",
                    "IGNITION_DATE": 1_750_000_000_000,
                }
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": properties,
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.INCIDENT, LiveResultKind.EVACUATION)
            )
        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [])

    async def test_invalid_schema_fails_closed_per_layer(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.EVACUATION,)
            )
        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.EVACUATION])

    async def test_ignition_date_cannot_pose_as_source_update_time(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/query"):
                payload = _metadata(LiveResultKind.INCIDENT)
                payload["editingInfo"] = {}
                return httpx.Response(200, json=payload)
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "OBJECTID": 7,
                                "FIRE_STATUS": "Out of Control",
                                "IGNITION_DATE": 1_750_000_000_000,
                            },
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.INCIDENT,)
            )
        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.INCIDENT])

    async def test_source_identity_and_required_fields_are_validated(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            payload = _metadata(LiveResultKind.INCIDENT)
            payload["name"] = "Unrelated public layer"
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.INCIDENT,)
            )
        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.INCIDENT])
