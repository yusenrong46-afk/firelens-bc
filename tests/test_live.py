from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

import firelens.live as live_module
from firelens.contracts import (
    Freshness,
    GeometryRelation,
    LiveLayerStatus,
    LivePagination,
    LiveResultKind,
    LocationInput,
)
from firelens.live import (
    LiveDataErrorKind,
    LiveDataService,
    LiveDataUnavailable,
    geometry_relation,
)


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

    def test_live_pagination_rejects_inconsistent_derived_fields(self) -> None:
        with self.assertRaises(ValidationError):
            LivePagination(
                page=1,
                page_size=2,
                total_results=3,
                total_pages=1,
                returned_results=2,
                has_previous=False,
                has_next=False,
            )

    def test_unavailable_layer_status_cannot_claim_freshness(self) -> None:
        with self.assertRaises(ValidationError):
            LiveLayerStatus(
                kind=LiveResultKind.INCIDENT,
                authority="BC Wildfire Service",
                source_url="https://official.example.test/incidents",
                available=False,
                source_updated_at=datetime.now(UTC),
                retrieved_at=datetime.now(UTC),
                freshness=Freshness.FRESH,
                matching_result_count=0,
            )


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
    async def test_geocoder_failures_are_sanitized_and_classified(self) -> None:
        scenarios = (
            (
                lambda request: (_ for _ in ()).throw(
                    httpx.ReadTimeout("private timeout detail", request=request)
                ),
                LiveDataErrorKind.TIMEOUT,
            ),
            (
                lambda _request: httpx.Response(503, text="private upstream detail"),
                LiveDataErrorKind.UPSTREAM_HTTP,
            ),
            (
                lambda _request: httpx.Response(200, content=b"not-json"),
                LiveDataErrorKind.INVALID_RESPONSE,
            ),
            (
                lambda _request: httpx.Response(200, json={"features": []}),
                LiveDataErrorKind.NOT_FOUND,
            ),
            (
                lambda _request: httpx.Response(
                    200,
                    json={
                        "features": [
                            {
                                "geometry": {
                                    "coordinates": [-79.38, 43.65],
                                }
                            }
                        ]
                    },
                ),
                LiveDataErrorKind.INVALID_RESPONSE,
            ),
        )
        for handler, expected_kind in scenarios:
            with self.subTest(kind=expected_kind):
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    service = LiveDataService(client=client)
                    with self.assertRaises(LiveDataUnavailable) as raised:
                        await service.resolve_location(LocationInput(label="Vancouver"))
                self.assertEqual(raised.exception.kind, expected_kind)
                self.assertNotIn("private", str(raised.exception))

    async def test_geocoder_cancellation_propagates(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise asyncio.CancelledError

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client)
            with self.assertRaises(asyncio.CancelledError):
                await service.resolve_location(LocationInput(label="Vancouver"))

    async def test_geocoder_returns_only_coarse_bc_coordinates(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"features": [{"geometry": {"coordinates": [-123.1207, 49.2827]}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client)
            location = await service.resolve_location(LocationInput(label="Vancouver"))

        self.assertEqual(location, (49.28, -123.12))

    async def test_record_ceiling_fails_closed_and_is_visible(self) -> None:
        features = [
            {
                "type": "Feature",
                "properties": {"OBJECTID": index, "FIRE_STATUS": "Out of Control"},
                "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
            }
            for index in range(3)
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            return httpx.Response(
                200,
                json={"type": "FeatureCollection", "features": features},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client, max_records=2).map_results(
                layers=(LiveResultKind.INCIDENT,)
            )

        self.assertEqual(response.results, [])
        self.assertEqual(response.unavailable_layers, [LiveResultKind.INCIDENT])
        self.assertTrue(any("bounded retrieval" in item for item in response.limitations))

    async def test_geometry_byte_limits_fail_closed_and_are_visible(self) -> None:
        oversized_feature = {
            "type": "Feature",
            "properties": {"OBJECTID": 1, "FIRE_STATUS": "Out of Control"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-123.5 + index / 10_000, 49.5] for index in range(50)]],
            },
        }
        point_features = [
            {
                "type": "Feature",
                "properties": {"OBJECTID": index, "FIRE_STATUS": "Out of Control"},
                "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
            }
            for index in range(3)
        ]

        for features, feature_limit, response_limit in (
            ([oversized_feature], 100, 1_000),
            (point_features, 100, 100),
        ):
            with self.subTest(
                feature_limit=feature_limit,
                response_limit=response_limit,
            ):

                def handler(
                    request: httpx.Request,
                    response_features: list[dict] = features,
                ) -> httpx.Response:
                    if not request.url.path.endswith("/query"):
                        return httpx.Response(
                            200,
                            json=_metadata(LiveResultKind.INCIDENT),
                        )
                    return httpx.Response(
                        200,
                        json={
                            "type": "FeatureCollection",
                            "features": response_features,
                        },
                    )

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    response = await LiveDataService(
                        client=client,
                        max_feature_geometry_bytes=feature_limit,
                        max_response_geometry_bytes=response_limit,
                    ).map_results(layers=(LiveResultKind.INCIDENT,))

                self.assertEqual(response.results, [])
                self.assertEqual(
                    response.unavailable_layers,
                    [LiveResultKind.INCIDENT],
                )
                self.assertTrue(
                    any("bounded retrieval" in item for item in response.limitations)
                )

    async def test_bbox_is_sent_to_arcgis_and_retained_as_local_backstop(self) -> None:
        requested_geometry: str | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requested_geometry
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            requested_geometry = request.url.params.get("geometry")
            self.assertEqual(request.url.params.get("geometryType"), "esriGeometryEnvelope")
            self.assertEqual(request.url.params.get("spatialRel"), "esriSpatialRelIntersects")
            self.assertEqual(request.url.params.get("inSR"), "4326")
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"OBJECTID": 1, "FIRE_STATUS": "Out of Control"},
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        },
                        {
                            "type": "Feature",
                            "properties": {"OBJECTID": 2, "FIRE_STATUS": "Out of Control"},
                            "geometry": {"type": "Point", "coordinates": [-120.0, 55.0]},
                        },
                    ],
                },
            )

        bbox = (-124.0, 49.0, -123.0, 50.0)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(client=client).map_results(
                layers=(LiveResultKind.INCIDENT,), bbox=bbox
            )

        self.assertEqual(requested_geometry, ",".join(str(value) for value in bbox))
        self.assertEqual([item.result_id for item in response.results], ["incident:1"])

    async def test_nearby_viewports_share_an_expanded_normalized_cache_key(self) -> None:
        query_geometries: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            query_geometries.append(request.url.params.get("geometry"))
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"OBJECTID": 1, "FIRE_STATUS": "Out of Control"},
                            "geometry": {"type": "Point", "coordinates": [-123.4, 49.5]},
                        }
                    ],
                },
            )

        first_bbox = (-123.56, 49.21, -123.12, 49.87)
        second_bbox = (-123.55, 49.22, -123.11, 49.88)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client, bbox_grid_degrees=0.1)
            first = await service.map_results(
                layers=(LiveResultKind.INCIDENT,), bbox=first_bbox
            )
            second = await service.map_results(
                layers=(LiveResultKind.INCIDENT,), bbox=second_bbox
            )

        self.assertEqual(query_geometries, ["-123.6,49.2,-123.1,49.9"])
        self.assertEqual([item.result_id for item in first.results], ["incident:1"])
        self.assertEqual([item.result_id for item in second.results], ["incident:1"])

    async def test_adversarial_viewport_churn_is_lru_bounded(self) -> None:
        query_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal query_calls
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            query_calls += 1
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

        viewports = (
            (-124.0, 49.0, -123.8, 49.2),
            (-123.7, 49.0, -123.5, 49.2),
            (-123.4, 49.0, -123.2, 49.2),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client, max_cache_entries=2)
            for bbox in viewports:
                await service.map_results(layers=(LiveResultKind.INCIDENT,), bbox=bbox)
            await service.map_results(layers=(LiveResultKind.INCIDENT,), bbox=viewports[0])

        self.assertEqual(query_calls, 4)
        self.assertEqual(len(service._cache), 2)

    async def test_cache_feature_budget_evicts_complete_old_entries(self) -> None:
        query_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal query_calls
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            query_calls += 1
            features = [
                {
                    "type": "Feature",
                    "properties": {
                        "OBJECTID": query_calls * 10 + index,
                        "FIRE_STATUS": "Out of Control",
                    },
                    "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                }
                for index in range(2)
            ]
            return httpx.Response(
                200,
                json={"type": "FeatureCollection", "features": features},
            )

        first_bbox = (-124.0, 49.0, -123.0, 50.0)
        second_bbox = (-122.0, 49.0, -121.0, 50.0)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(
                client=client,
                max_records=3,
                max_cache_entries=10,
                max_cached_features=3,
            )
            await service.map_results(layers=(LiveResultKind.INCIDENT,), bbox=first_bbox)
            await service.map_results(layers=(LiveResultKind.INCIDENT,), bbox=second_bbox)
            await service.map_results(layers=(LiveResultKind.INCIDENT,), bbox=first_bbox)

        self.assertEqual(query_calls, 3)
        self.assertEqual(len(service._cache), 1)
        self.assertEqual(service._cached_feature_count, 2)

    def test_cache_limits_and_grid_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "entry limit"):
            LiveDataService(max_cache_entries=0)
        with self.assertRaisesRegex(ValueError, "feature limit"):
            LiveDataService(max_records=10, max_cached_features=9)
        with self.assertRaisesRegex(ValueError, "bbox grid"):
            LiveDataService(bbox_grid_degrees=0)
        with self.assertRaisesRegex(ValueError, "upstream concurrency"):
            LiveDataService(max_upstream_concurrency=0)
        with self.assertRaisesRegex(ValueError, "feature geometry"):
            LiveDataService(max_feature_geometry_bytes=0)
        with self.assertRaisesRegex(ValueError, "response geometry"):
            LiveDataService(
                max_feature_geometry_bytes=100,
                max_response_geometry_bytes=99,
            )

    async def test_independent_layers_run_concurrently_with_a_bounded_budget(self) -> None:
        active = 0
        max_active = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            kind = _kind_from_url(request)
            if request.url.path.endswith("/query"):
                return httpx.Response(
                    200,
                    json={"type": "FeatureCollection", "features": []},
                )
            return httpx.Response(200, json=_metadata(kind))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await LiveDataService(
                client=client,
                max_upstream_concurrency=2,
            ).map_results(layers=tuple(LiveResultKind))

        self.assertEqual(max_active, 2)
        self.assertEqual(response.unavailable_layers, [])

    async def test_layer_definition_can_be_injected_without_code_path_duplication(self) -> None:
        definition = live_module.LayerDefinition(
            url="https://official.example.test/custom-layer/0",
            expected_name="Custom Incidents",
            required_fields=frozenset(
                {"OBJECTID", "FIRE_STATUS", "FIRE_NUMBER", "INCIDENT_NAME"}
            ),
        )
        requested_hosts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_hosts.append(request.url.host)
            if not request.url.path.endswith("/query"):
                payload = _metadata(LiveResultKind.INCIDENT)
                payload["name"] = "Custom Incidents"
                return httpx.Response(200, json=payload)
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await LiveDataService(
                client=client,
                layer_definitions={LiveResultKind.INCIDENT: definition},
            ).map_results(layers=(LiveResultKind.INCIDENT,))

        self.assertEqual(set(requested_hosts), {"official.example.test"})

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

    async def test_nearby_page_is_bounded_explicit_and_roster_complete(self) -> None:
        features = [
            {
                "type": "Feature",
                "properties": {
                    "OBJECTID": index,
                    "FIRE_STATUS": "Being Held",
                    "FIRE_NUMBER": f"K{index:05d}",
                    "INCIDENT_NAME": f"Fire {index}",
                },
                "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
            }
            for index in range(1, 4)
        ]
        query_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal query_calls
            if not request.url.path.endswith("/query"):
                return httpx.Response(200, json=_metadata(LiveResultKind.INCIDENT))
            query_calls += 1
            return httpx.Response(
                200,
                json={"type": "FeatureCollection", "features": features},
            )

        location = LocationInput(latitude=49.5, longitude=-123.5, radius_km=25)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LiveDataService(client=client)
            first = await service.nearby_page(
                location,
                layers=(LiveResultKind.INCIDENT,),
                page=1,
                page_size=2,
            )
            second = await service.nearby_page(
                location,
                layers=(LiveResultKind.INCIDENT,),
                page=2,
                page_size=2,
            )
            beyond = await service.nearby_page(
                location,
                layers=(LiveResultKind.INCIDENT,),
                page=3,
                page_size=2,
            )

        self.assertEqual(query_calls, 1)
        self.assertEqual([row.result_id for row in first.results], ["incident:1", "incident:2"])
        self.assertEqual([row.result_id for row in second.results], ["incident:3"])
        self.assertEqual(beyond.results, [])
        self.assertEqual(first.pagination.total_results, 3)
        self.assertEqual(first.pagination.total_pages, 2)
        self.assertTrue(first.pagination.has_next)
        self.assertTrue(second.pagination.has_previous)
        self.assertFalse(second.pagination.has_next)
        self.assertEqual(first.resolved_location.latitude, 49.5)
        self.assertEqual(first.requested_radius_km, 25)
        self.assertEqual(first.requested_layers, [LiveResultKind.INCIDENT])
        self.assertTrue(first.official_fallback_urls)
        self.assertTrue(any("1-2 of 3" in item for item in first.limitations))
        self.assertTrue(any("beyond" in item for item in beyond.limitations))

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
        self.assertEqual(first.layer_statuses[0].freshness, Freshness.FRESH)
        self.assertEqual(second.layer_statuses[0].freshness, Freshness.STALE)
        self.assertEqual(first.layer_statuses[0].matching_result_count, 1)
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
        self.assertFalse(second.layer_statuses[0].available)
        self.assertIsNone(second.layer_statuses[0].source_updated_at)

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
        self.assertEqual(
            [status.matching_result_count for status in response.layer_statuses],
            [2, 0],
        )
        self.assertEqual(
            [status.available for status in response.layer_statuses],
            [True, False],
        )

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
