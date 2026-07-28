from __future__ import annotations

import unittest

import httpx
from pydantic import ValidationError

from firelens.contracts import (
    Freshness,
    GeometryRelation,
    LiveResultKind,
    LocationInput,
)
from firelens.live import LiveDataService, geometry_relation


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
    async def test_cache_becomes_visibly_stale_after_refresh_failure(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise httpx.ReadTimeout("offline")
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

    async def test_invalid_schema_fails_closed_per_layer(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.EVACUATION,)
            )
        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.EVACUATION])
