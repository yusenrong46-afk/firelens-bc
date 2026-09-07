"""Retained source regression: map-only omissions never enter strict queries."""

import copy
import json
import unittest
from pathlib import Path

import httpx
from test_live import _metadata

from firelens.contracts import LiveMapResponse, LiveResultKind, LocationInput
from firelens.live import LiveDataService
from firelens.live_support import geometry_integrity_errors


class GeometryQuarantineTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_source_capture_preserves_holes_and_quarantines_real_defects(self):
        for kind in (LiveResultKind.PERIMETER, LiveResultKind.EVACUATION):
            with self.subTest(kind=kind):
                payload = json.loads(
                    (
                        Path(__file__).parent
                        / "fixtures"
                        / "arcgis"
                        / f"{kind.value}-2026-09-07.json"
                    ).read_text()
                )
                requests = []

                def handler(request, requests=requests, kind=kind, payload=payload):
                    requests.append(request)
                    if not request.url.path.endswith("/query"):
                        return httpx.Response(200, json=_metadata(kind))
                    if request.url.params.get("returnCountOnly") == "true":
                        return httpx.Response(200, json={"count": len(payload["features"])})
                    self.assertEqual(request.url.params["f"], "json")
                    self.assertEqual(request.url.params["outSR"], "4326")
                    return httpx.Response(200, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    service = LiveDataService(client=client)
                    mapped = await service.map_results(
                        layers=(kind,), allow_partial_geometry=True
                    )
                    strict = await service.map_results(layers=(kind,))
                    self.assertEqual(len(mapped.results), 1)
                    self.assertEqual(mapped.unavailable_layers, [])
                    self.assertEqual(geometry_integrity_errors(mapped.results[0].geometry), [])
                    self.assertEqual(len(requests), 3)  # shared source cache, no second fetch
                    if kind is LiveResultKind.PERIMETER:
                        self.assertEqual(len(strict.results), 1)
                        self.assertEqual(mapped.partial_layers, [])
                        rings = [
                            ring
                            for poly in mapped.results[0].geometry["coordinates"]
                            for ring in poly
                        ]
                        self.assertCountEqual(
                            rings, payload["features"][0]["geometry"]["rings"]
                        )
                    else:
                        self.assertEqual(mapped.partial_layers, [kind])
                        self.assertEqual(mapped.layer_statuses[0].omitted_geometry_count, 2)
                        self.assertEqual(mapped.results[0].result_id, "evacuation:c2b6ef51b037")
                        self.assertEqual(strict.results, [])
                        self.assertEqual(strict.unavailable_layers, [kind])
                        near = await service.nearby_results(
                            LocationInput(latitude=51.1, longitude=-122.1), layers=(kind,)
                        )
                        self.assertEqual(near.results, [])
                        self.assertEqual(near.unavailable_layers, [kind])

                    bad = mapped.model_dump(mode="json")
                    bad["partial_layers"] = [] if mapped.partial_layers else [kind.value]
                    with self.assertRaises(ValueError):
                        LiveMapResponse.model_validate(bad)

    async def test_all_invalid_is_unavailable_and_empty_is_available(self):
        kind = LiveResultKind.EVACUATION
        captured = json.loads(
            (Path(__file__).parent / "fixtures/arcgis/evacuation-2026-09-07.json").read_text()
        )
        for features, unavailable in [([], False), ([captured["features"][0]], True)]:
            with self.subTest(unavailable=unavailable):
                payload = {**captured, "features": features}

                def handler(request, features=features, payload=payload):
                    if not request.url.path.endswith("/query"):
                        return httpx.Response(200, json=_metadata(kind))
                    if request.url.params.get("returnCountOnly") == "true":
                        return httpx.Response(200, json={"count": len(features)})
                    return httpx.Response(200, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    mapped = await LiveDataService(client=client).map_results(
                        layers=(kind,), allow_partial_geometry=True
                    )
                self.assertEqual(mapped.results, [])
                self.assertEqual(mapped.layer_statuses[0].available, not unavailable)
                self.assertEqual(mapped.partial_layers, [])

    async def test_native_crs_and_published_count_are_not_bypassed(self):
        kind = LiveResultKind.EVACUATION
        captured = json.loads(
            (Path(__file__).parent / "fixtures/arcgis/evacuation-2026-09-07.json").read_text()
        )
        for fault in ("crs", "count", "metadata"):
            with self.subTest(fault=fault):
                payload = copy.deepcopy(captured)
                if fault == "crs":
                    payload["spatialReference"] = {"wkid": 3857}

                def handler(request, fault=fault, payload=payload):
                    if not request.url.path.endswith("/query"):
                        return httpx.Response(
                            200, json={} if fault == "metadata" else _metadata(kind)
                        )
                    if request.url.params.get("returnCountOnly") == "true":
                        return httpx.Response(200, json={"count": 4 if fault == "count" else 3})
                    return httpx.Response(200, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    mapped = await LiveDataService(client=client).map_results(
                        layers=(kind,), allow_partial_geometry=True
                    )
                self.assertEqual(mapped.results, [])
                self.assertEqual(mapped.unavailable_layers, [kind])
