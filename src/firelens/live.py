"""Fail-closed adapters for official British Columbia wildfire data."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import OrderedDict
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

import httpx
from pydantic import HttpUrl
from shapely.geometry import box

from firelens.arcgis_geometry import decode_features
from firelens.contracts import (
    CoarseResolvedLocation,
    Freshness,
    GeometryRelation,
    LiveLayerStatus,
    LiveMapResponse,
    LivePagination,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapViewport,
    NearMeResponse,
    aggregate_live_freshness,
    freshness_for_observation,
)
from firelens.live_admission import map_layer_results
from firelens.live_contracts import stale_observation_limitations
from firelens.live_http import decoded_response_headers, envelope_params, official_flag
from firelens.live_identity import feature_identity
from firelens.live_support import (
    DEFAULT_LAYER_DEFINITIONS,
    LAYER_URLS,
    OFFICIAL_FALLBACK_URLS,
    WGS84_GEOD,
    CacheEntry,
    LayerDefinition,
    LiveDataErrorKind,
    LiveDataUnavailable,
    _BBox,
    _CacheKey,
    _official_record_updated_at,
    _official_size_hectares,
    authority,
    bc_region_entry,
    geometry_relation,
    property_value,
    regional_lookup_limitations,
    resolve_bc_location,
    timestamp,
)

__all__ = [
    "LAYER_URLS",
    "LayerDefinition",
    "LiveDataErrorKind",
    "LiveDataService",
    "LiveDataUnavailable",
    "geometry_relation",
]


class LiveDataService:
    """One source of truth for chat and map live records."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        fresh_seconds: float = 300,
        stale_if_error_seconds: float = 900,
        max_pages: int = 100,
        max_records: int = 20_000,
        max_feature_geometry_bytes: int = 512_000,
        max_response_geometry_bytes: int = 8_000_000,
        max_upstream_response_bytes: int = 16_000_000,
        max_cache_entries: int = 32,
        max_cached_features: int = 60_000,
        bbox_grid_degrees: float = 0.1,
        max_upstream_concurrency: int = 4,
        layer_definitions: dict[LiveResultKind, LayerDefinition] | None = None,
    ) -> None:
        if max_pages < 1 or max_records < 1:
            raise ValueError("live pagination limits must be positive")
        if max_feature_geometry_bytes < 1:
            raise ValueError("live feature geometry limit must be positive")
        if max_response_geometry_bytes < max_feature_geometry_bytes:
            raise ValueError("live response geometry limit must cover one bounded feature")
        if max_upstream_response_bytes < max_response_geometry_bytes:
            raise ValueError("live upstream response limit must cover bounded geometry")
        if max_cache_entries < 1:
            raise ValueError("live cache entry limit must be positive")
        if max_cached_features < max_records:
            raise ValueError("live cached feature limit must cover one bounded response")
        if not math.isfinite(bbox_grid_degrees) or not 0.01 <= bbox_grid_degrees <= 1.0:
            raise ValueError("live bbox grid must be between 0.01 and 1.0 degrees")
        if not 1 <= max_upstream_concurrency <= 16:
            raise ValueError("live upstream concurrency must be between 1 and 16")
        self.client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None
        self.fresh_seconds = fresh_seconds
        self.stale_if_error_seconds = stale_if_error_seconds
        self.max_pages = max_pages
        self.max_records = max_records
        self.max_feature_geometry_bytes = max_feature_geometry_bytes
        self.max_response_geometry_bytes = max_response_geometry_bytes
        self.max_upstream_response_bytes = max_upstream_response_bytes
        self.max_cache_entries = max_cache_entries
        self.max_cached_features = max_cached_features
        self.bbox_grid_degrees = bbox_grid_degrees
        self.max_upstream_concurrency = max_upstream_concurrency
        self.layer_definitions = dict(layer_definitions or DEFAULT_LAYER_DEFINITIONS)
        self._cache: OrderedDict[_CacheKey, CacheEntry] = OrderedDict()
        self._cached_feature_count = 0
        self._locks = {kind: asyncio.Lock() for kind in LiveResultKind}
        self._upstream_semaphore = asyncio.Semaphore(max_upstream_concurrency)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _get(self, url: str, *, params: dict[str, Any]) -> httpx.Response:
        async with self._upstream_semaphore:
            async with self.client.stream("GET", url, params=params) as response:
                declared_length = response.headers.get("content-length")
                if declared_length is not None and declared_length.isdecimal():
                    if int(declared_length) > self.max_upstream_response_bytes:
                        raise LiveDataUnavailable(
                            "official live source exceeded the upstream response limit",
                            kind=LiveDataErrorKind.BOUNDED_LIMIT,
                        )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_upstream_response_bytes:
                        raise LiveDataUnavailable(
                            "official live source exceeded the upstream response limit",
                            kind=LiveDataErrorKind.BOUNDED_LIMIT,
                        )
                    chunks.append(chunk)
                return httpx.Response(
                    response.status_code,
                    headers=decoded_response_headers(response.headers),
                    content=b"".join(chunks),
                    request=response.request,
                )

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        return await resolve_bc_location(self._get, location)

    def _layer(self, kind: LiveResultKind) -> LayerDefinition:
        try:
            return self.layer_definitions[kind]
        except KeyError as exc:
            raise LiveDataUnavailable(
                f"{kind.value} layer is not configured",
                kind=LiveDataErrorKind.NOT_CONFIGURED,
            ) from exc

    def _normalized_bbox(self, bbox: _BBox | None) -> _BBox | None:
        """Expand a viewport onto a stable grid so nearby pans share cache entries.

        ArcGIS may return extra records; map_results filters the exact bounds.
        """
        if bbox is None:
            return None
        west, south, east, north = bbox
        if (
            not all(math.isfinite(value) for value in bbox)
            or not -180 <= west < east <= 180
            or not -90 <= south < north <= 90
        ):
            raise ValueError("live bbox must be finite, ordered WGS84 coordinates")
        grid = Decimal(str(self.bbox_grid_degrees))

        def lower(value: float) -> float:
            units = (Decimal(str(value)) / grid).to_integral_value(rounding=ROUND_FLOOR)
            return float(units * grid)

        def upper(value: float) -> float:
            units = (Decimal(str(value)) / grid).to_integral_value(rounding=ROUND_CEILING)
            return float(units * grid)

        return lower(west), lower(south), upper(east), upper(north)

    def _cache_get(self, key: _CacheKey) -> CacheEntry | None:
        entry = self._cache.get(key)
        if entry is not None:
            self._cache.move_to_end(key)
        return entry

    def _cache_put(self, key: _CacheKey, entry: CacheEntry) -> None:
        previous = self._cache.pop(key, None)
        if previous is not None:
            self._cached_feature_count -= len(previous.features)
        self._cache[key] = entry
        self._cached_feature_count += len(entry.features)
        while (
            len(self._cache) > self.max_cache_entries
            or self._cached_feature_count > self.max_cached_features
        ):
            _evicted_key, evicted = self._cache.popitem(last=False)
            self._cached_feature_count -= len(evicted.features)

    async def _fetch_page(
        self,
        kind: LiveResultKind,
        *,
        offset: int,
        bbox: tuple[float, float, float, float] | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        params: dict[str, Any] = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson" if kind is LiveResultKind.INCIDENT else "json",
            "resultOffset": offset,
            "resultRecordCount": 1000,
            "orderByFields": "OBJECTID ASC",
            **envelope_params(bbox),
        }
        response = await self._get(
            f"{self._layer(kind).url}/query",
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        return decode_features(payload, kind, self.max_feature_geometry_bytes)

    async def _published_count(self, kind: LiveResultKind, *, bbox: _BBox | None) -> int:
        """Return the authoritative record count or fail closed."""

        params = {
            "where": "1=1",
            "returnCountOnly": "true",
            "f": "json",
            **envelope_params(bbox),
        }
        try:
            response = await self._get(f"{self._layer(kind).url}/query", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LiveDataUnavailable(
                f"{kind.value} source count was unavailable",
                kind=LiveDataErrorKind.INVALID_RESPONSE,
            ) from exc
        count = payload.get("count") if isinstance(payload, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise LiveDataUnavailable(
                f"{kind.value} source returned an invalid published count",
                kind=LiveDataErrorKind.INVALID_RESPONSE,
            )
        return count

    async def _source_metadata(self, kind: LiveResultKind) -> datetime:
        definition = self._layer(kind)
        response = await self._get(definition.url, params={"f": "json"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("name") != definition.expected_name:
            raise LiveDataUnavailable(f"{kind.value} source identity did not match")
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise LiveDataUnavailable(f"{kind.value} source fields were unavailable")
        field_names = {
            item.get("name")
            for item in fields
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if not definition.required_fields.issubset(field_names):
            raise LiveDataUnavailable(f"{kind.value} source schema did not match")
        editing = payload.get("editingInfo")
        updated = timestamp(
            editing.get("dataLastEditDate") if isinstance(editing, dict) else None
        )
        if updated is None:
            raise LiveDataUnavailable(f"{kind.value} source has no authoritative update time")
        return updated

    async def _refresh(
        self,
        kind: LiveResultKind,
        *,
        bbox: tuple[float, float, float, float] | None,
    ) -> CacheEntry:
        source_updated_at, (page, exceeded), published = await asyncio.gather(
            self._source_metadata(kind),
            self._fetch_page(kind, offset=0, bbox=bbox),
            self._published_count(kind, bbox=bbox),
        )
        features: list[dict[str, Any]] = []
        seen_feature_ids: set[str] = set()
        seen_pages: set[tuple[str, ...]] = set()
        geometry_bytes = 0
        offset = 0
        for page_number in range(self.max_pages):
            if page_number:
                page, exceeded = await self._fetch_page(kind, offset=offset, bbox=bbox)
            page_ids = tuple(feature_identity(kind, feature) for feature in page)
            if page and page_ids in seen_pages:
                raise LiveDataUnavailable(f"{kind.value} source repeated a result page")
            seen_pages.add(page_ids)
            new_features = [
                feature
                for feature, feature_id in zip(page, page_ids, strict=True)
                if feature_id not in seen_feature_ids
            ]
            if page and not new_features:
                raise LiveDataUnavailable(f"{kind.value} source pagination made no progress")
            if len(features) + len(new_features) > self.max_records:
                raise LiveDataUnavailable(
                    f"{kind.value} source exceeded the bounded retrieval record limit",
                    kind=LiveDataErrorKind.BOUNDED_LIMIT,
                )
            new_geometry_sizes = [
                len(
                    json.dumps(
                        feature["geometry"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                for feature in new_features
            ]
            if any(size > self.max_feature_geometry_bytes for size in new_geometry_sizes):
                raise LiveDataUnavailable(
                    f"{kind.value} source exceeded the per-feature geometry limit",
                    kind=LiveDataErrorKind.BOUNDED_LIMIT,
                )
            if geometry_bytes + sum(new_geometry_sizes) > self.max_response_geometry_bytes:
                raise LiveDataUnavailable(
                    f"{kind.value} source exceeded the response geometry limit",
                    kind=LiveDataErrorKind.BOUNDED_LIMIT,
                )
            features.extend(new_features)
            geometry_bytes += sum(new_geometry_sizes)
            seen_feature_ids.update(feature_identity(kind, item) for item in new_features)
            if not exceeded and len(page) < 1000:
                break
            if not page:
                break
            offset += len(page)
        else:
            raise LiveDataUnavailable(
                f"{kind.value} source exceeded the pagination limit",
                kind=LiveDataErrorKind.BOUNDED_LIMIT,
            )
        if len(features) != published:
            raise LiveDataUnavailable(
                f"{kind.value} source returned {len(features)} of {published} "
                "published records",
                kind=LiveDataErrorKind.INVALID_RESPONSE,
            )
        entry = CacheEntry(
            fetched_monotonic=time.monotonic(),
            retrieved_at=datetime.now(UTC),
            source_updated_at=source_updated_at,
            features=tuple(features),
        )
        return entry

    async def _features(
        self,
        kind: LiveResultKind,
        *,
        bbox: tuple[float, float, float, float] | None,
    ) -> tuple[CacheEntry, Freshness]:
        normalized_bbox = self._normalized_bbox(bbox)
        cache_key = (kind, normalized_bbox)
        cached = self._cache_get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached.fetched_monotonic <= self.fresh_seconds
        ):
            return cached, Freshness.FRESH
        async with self._locks[kind]:
            cached = self._cache_get(cache_key)
            if (
                cached is not None
                and time.monotonic() - cached.fetched_monotonic <= self.fresh_seconds
            ):
                return cached, Freshness.FRESH
            try:
                refreshed = await self._refresh(kind, bbox=normalized_bbox)
                self._cache_put(cache_key, refreshed)
                return refreshed, Freshness.FRESH
            except (
                httpx.HTTPError,
                ValueError,
                json.JSONDecodeError,
                LiveDataUnavailable,
            ) as exc:
                cached = self._cache_get(cache_key)
                if (
                    cached is not None
                    and time.monotonic() - cached.fetched_monotonic
                    <= self.stale_if_error_seconds
                ):
                    return cached, Freshness.STALE
                if isinstance(exc, LiveDataUnavailable):
                    raise LiveDataUnavailable(str(exc), kind=exc.kind) from exc
                raise LiveDataUnavailable(f"{kind.value} source is unavailable") from exc

    def _to_result(
        self,
        kind: LiveResultKind,
        feature: dict[str, Any],
        *,
        result_id: str,
        retrieved_at: datetime,
        freshness: Freshness,
        source_updated_at: datetime,
        location: tuple[float, float, float] | None = None,
    ) -> LiveResult:
        properties = feature["properties"]
        geometry = feature["geometry"]
        relation = GeometryRelation.UNKNOWN
        if location is not None:
            latitude, longitude, radius_km = location
            relation = geometry_relation(
                geometry,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            )
        updated = _official_record_updated_at(properties, source_updated_at)
        size = property_value(properties, "FIRE_SIZE_HECTARES", "CURRENT_SIZE", "SIZE_HA")
        observed_freshness = freshness_for_observation(
            freshness, source_updated_at=updated, retrieved_at=retrieved_at
        )
        return LiveResult(
            result_id=result_id,
            kind=kind,
            authority=authority(kind),
            source_url=HttpUrl(self._layer(kind).url),
            source_updated_at=updated,
            retrieved_at=retrieved_at,
            freshness=observed_freshness,
            status=str(
                property_value(
                    properties,
                    "FIRE_STATUS",
                    "ORDER_ALERT_STATUS",
                    "STATUS",
                    "EVENT_STATUS",
                )
                or "Official record"
            ),
            name=(
                str(raw_name).strip()
                if (
                    raw_name := property_value(
                        properties,
                        "INCIDENT_NAME",
                        "FIRE_NAME",
                        "EVENT_NAME",
                        "NAME",
                        "LOCATION_DESCRIPTION",
                    )
                )
                else None
            ),
            incident_number=(
                str(value)
                if (value := property_value(properties, "FIRE_NUMBER", "INCIDENT_NUMBER"))
                is not None
                else None
            ),
            size_hectares=_official_size_hectares(size),
            fire_centre=(
                str(value)
                if (value := property_value(properties, "FIRE_CENTRE", "FIRE_CENTER"))
                is not None
                else None
            ),
            fire_zone=(
                str(value)
                if (value := property_value(properties, "FIRE_ZONE")) is not None
                else None
            ),
            issuer=(
                str(value)
                if (
                    value := property_value(properties, "ISSUING_AGENCY", "ISSUED_BY", "AGENCY")
                )
                is not None
                else None
            ),
            fire_of_note=official_flag(property_value(properties, "FIRE_OF_NOTE_IND"))
            or str(property_value(properties, "FIRE_STATUS") or "").strip().casefold()
            == "fire of note",
            geometry_relation=relation,
            geometry=geometry,
        )

    def _unavailable_status(
        self, kind: LiveResultKind, *, invalid_geometry: bool = False
    ) -> LiveLayerStatus:
        definition = self.layer_definitions.get(kind, DEFAULT_LAYER_DEFINITIONS[kind])
        return LiveLayerStatus(
            kind=kind,
            authority=authority(kind),
            source_url=HttpUrl(definition.url),
            available=False,
            matching_result_count=0,
            unavailability_reason="invalid_geometry" if invalid_geometry else None,
        )

    async def map_results(
        self,
        *,
        layers: tuple[LiveResultKind, ...],
        bbox: tuple[float, float, float, float] | None = None,
        allow_partial_geometry: bool = False,
        evacuation_statuses: tuple[str, ...] = (),
    ) -> LiveMapResponse:
        results: list[LiveResult] = []
        unavailable: list[LiveResultKind] = []
        layer_statuses: list[LiveLayerStatus] = []
        unavailable_reasons: list[str] = []
        bounds = box(*bbox) if bbox is not None else None
        layer_outcomes = await asyncio.gather(
            *(
                map_layer_results(
                    self,
                    kind,
                    bbox=bbox,
                    bounds=bounds,
                    allow_partial_geometry=allow_partial_geometry,
                    evacuation_statuses=evacuation_statuses,
                )
                for kind in layers
            )
        )
        for kind, (layer_results, layer_status, unavailable_reason) in zip(
            layers, layer_outcomes, strict=True
        ):
            layer_statuses.append(layer_status)
            if unavailable_reason is not None:
                unavailable.append(kind)
                unavailable_reasons.append(unavailable_reason)
                continue
            results.extend(layer_results)
        limitations = [
            "Official records can change quickly; confirm emergency directions with the issuing authority.",
            "No matching record is not a safety determination.",
        ]
        if unavailable_reasons:
            limitations.append(
                "Some official layers were unavailable or exceeded bounded retrieval limits: "
                + "; ".join(unavailable_reasons)
            )
        partial = [
            status.kind
            for status in layer_statuses
            if status.omitted_geometry_count or status.omitted_status_count
        ]
        for status in layer_statuses:
            if status.omitted_geometry_count:
                limitations.append(
                    f"{status.kind.value}: {status.omitted_geometry_count} official records omitted because their geometry is invalid. "
                    "Displayed records are incomplete; absence is not an all-clear."
                )
            if status.omitted_status_count:
                limitations.append(
                    f"{status.kind.value}: {status.omitted_status_count} official records have an unrecognized status; coverage is incomplete."
                )
        limitations.extend(stale_observation_limitations(layer_statuses, results))
        return LiveMapResponse(
            generated_at=datetime.now(UTC),
            results=sorted(results, key=lambda result: (result.kind.value, result.result_id)),
            aggregate_freshness=aggregate_live_freshness(results),
            unavailable_layers=unavailable,
            partial_layers=partial,
            layer_statuses=layer_statuses,
            limitations=limitations,
        )

    async def _nearby_full(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...],
        evacuation_statuses: tuple[str, ...] = (),
    ) -> tuple[LiveMapResponse, float, float, _BBox]:
        latitude, longitude = await self.resolve_location(location)
        radius_km = location.radius_km
        if location.label:
            region = bc_region_entry(location.label)
            if region is not None:
                radius_km = region.radius_km
        west = WGS84_GEOD.fwd(longitude, latitude, 270, radius_km * 1_000)[0]
        east = WGS84_GEOD.fwd(longitude, latitude, 90, radius_km * 1_000)[0]
        south = WGS84_GEOD.fwd(longitude, latitude, 180, radius_km * 1_000)[1]
        north = WGS84_GEOD.fwd(longitude, latitude, 0, radius_km * 1_000)[1]
        bbox = (west, south, east, north)
        response = await self.map_results(
            layers=layers,
            bbox=bbox,
            allow_partial_geometry=True,
            evacuation_statuses=evacuation_statuses,
        )
        related: list[LiveResult] = []
        unknown_located = False
        for result in response.results:
            relation = geometry_relation(
                result.geometry,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            )
            if relation == GeometryRelation.UNKNOWN:
                unknown_located = True
                continue
            if relation in {GeometryRelation.INSIDE, GeometryRelation.NEARBY}:
                related.append(result.model_copy(update={"geometry_relation": relation}))
        limitations = regional_lookup_limitations(
            location, response.limitations, unknown_located=unknown_located
        )
        related_response = response.model_copy(
            update={
                "results": related,
                "aggregate_freshness": aggregate_live_freshness(related),
                "layer_statuses": [
                    status.model_copy(
                        update={
                            "matching_result_count": sum(
                                result.kind == status.kind for result in related
                            )
                        }
                    )
                    for status in response.layer_statuses
                ],
                "limitations": limitations,
            }
        )
        return related_response, latitude, longitude, bbox

    async def nearby_results(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...] = tuple(LiveResultKind),
        evacuation_statuses: tuple[str, ...] = (),
    ) -> LiveMapResponse:
        response, _latitude, _longitude, _bbox = await self._nearby_full(
            location,
            layers=layers,
            evacuation_statuses=evacuation_statuses,
        )
        return response

    async def nearby_page(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...] = tuple(LiveResultKind),
        evacuation_statuses: tuple[str, ...] = (),
        page: int = 1,
        page_size: int = 100,
    ) -> NearMeResponse:
        """Return a bounded, explicit page for the map and accessible record list."""
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("near-me pagination is outside the public bounds")
        requested_layers = tuple(dict.fromkeys(layers))
        if not requested_layers:
            raise ValueError("near-me requires at least one official layer")
        response, latitude, longitude, bbox = await self._nearby_full(
            location,
            layers=requested_layers,
            evacuation_statuses=evacuation_statuses,
        )
        total_results = len(response.results)
        total_pages = math.ceil(total_results / page_size)
        start = (page - 1) * page_size
        page_results = response.results[start : start + page_size]
        limitations = list(response.limitations)
        if total_results > page_size or page > 1:
            if page_results:
                scope = (
                    "validated subset; complete official totals are unknown"
                    if response.partial_layers
                    else "full roster"
                )
                limitations.append(
                    f"Showing official records {start + 1}-{start + len(page_results)} of "
                    f"{total_results}; use the record-list pagination to inspect the {scope}."
                )
            else:
                scope = (
                    "validated record subset"
                    if response.partial_layers
                    else "matching official record roster"
                )
                limitations.append(
                    f"The requested page is beyond the {scope}; return to page 1."
                )
        west, south, east, north = bbox
        return NearMeResponse(
            generated_at=response.generated_at,
            requested_radius_km=location.radius_km,
            requested_layers=list(requested_layers),
            resolved_location=CoarseResolvedLocation(
                latitude=latitude,
                longitude=longitude,
            ),
            viewport=MapViewport(west=west, south=south, east=east, north=north),
            results=page_results,
            pagination=LivePagination(
                page=page,
                page_size=page_size,
                total_results=total_results,
                total_pages=total_pages,
                returned_results=len(page_results),
                has_previous=page > 1,
                has_next=page < total_pages,
            ),
            aggregate_freshness=aggregate_live_freshness(page_results),
            partial_layers=response.partial_layers,
            unavailable_layers=response.unavailable_layers,
            layer_statuses=response.layer_statuses,
            limitations=limitations,
            official_fallback_urls=list(OFFICIAL_FALLBACK_URLS),
        )
