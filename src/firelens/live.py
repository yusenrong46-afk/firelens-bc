"""Fail-closed adapters for official British Columbia wildfire data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import HttpUrl
from shapely.geometry import Point, box, shape
from shapely.ops import nearest_points

from firelens.contracts import (
    Freshness,
    GeometryRelation,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    LocationInput,
)

ACTIVE_FIRES_URL = (
    "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/"
    "BCWS_ActiveFires_PublicView/FeatureServer/0"
)
FIRE_PERIMETERS_URL = (
    "https://services6.arcgis.com/ubm4tcTYICKBpist/ArcGIS/rest/services/"
    "BCWS_FirePerimeters_PublicView/FeatureServer/0"
)
EVACUATIONS_URL = (
    "https://services6.arcgis.com/ubm4tcTYICKBpist/ArcGIS/rest/services/"
    "Evacuation_Orders_and_Alerts/FeatureServer/0"
)
BC_GEOCODER_URL = "https://geocoder.api.gov.bc.ca/addresses.geojson"

LAYER_URLS = {
    LiveResultKind.INCIDENT: ACTIVE_FIRES_URL,
    LiveResultKind.PERIMETER: FIRE_PERIMETERS_URL,
    LiveResultKind.EVACUATION: EVACUATIONS_URL,
}


class LiveDataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class _CacheEntry:
    fetched_monotonic: float
    retrieved_at: datetime
    features: tuple[dict[str, Any], ...]


def _property(properties: dict[str, Any], *names: str) -> Any:
    folded = {str(key).casefold(): value for key, value in properties.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value not in (None, ""):
            return value
    return None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lon1, lat1 = first
    lon2, lat2 = second
    radius = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = (
        math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


def geometry_relation(
    geometry: dict[str, Any], *, latitude: float, longitude: float, radius_km: float
) -> GeometryRelation:
    """Compute a conservative relation with boundary points treated as inside."""

    try:
        target = shape(geometry)
        if target.is_empty or not target.is_valid:
            return GeometryRelation.UNKNOWN
        point = Point(longitude, latitude)
        if isinstance(target, Point):
            distance = _haversine_km((longitude, latitude), (float(target.x), float(target.y)))
        else:
            if target.contains(point) or target.touches(point):
                return GeometryRelation.INSIDE
            nearest = nearest_points(point, target)[1]
            distance = _haversine_km(
                (longitude, latitude), (float(nearest.x), float(nearest.y))
            )
        return GeometryRelation.NEARBY if distance <= radius_km else GeometryRelation.OUTSIDE
    except (TypeError, ValueError):
        return GeometryRelation.UNKNOWN


class LiveDataService:
    """One source of truth for chat and map live records."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        fresh_seconds: float = 300,
        stale_if_error_seconds: float = 900,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None
        self.fresh_seconds = fresh_seconds
        self.stale_if_error_seconds = stale_if_error_seconds
        self._cache: dict[LiveResultKind, _CacheEntry] = {}
        self._locks = {kind: asyncio.Lock() for kind in LiveResultKind}

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        if location.latitude is not None and location.longitude is not None:
            return location.latitude, location.longitude
        if location.label is None:
            raise LiveDataUnavailable("a coarse location is required for a nearby query")
        response = await self.client.get(
            BC_GEOCODER_URL,
            params={
                "addressString": location.label,
                "maxResults": 1,
                "outputSRS": 4326,
                "echo": "false",
            },
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features:
            raise LiveDataUnavailable("the place label could not be resolved")
        coordinates = features[0].get("geometry", {}).get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise LiveDataUnavailable("the geocoder returned invalid coordinates")
        return round(float(coordinates[1]), 2), round(float(coordinates[0]), 2)

    async def _fetch_page(
        self, kind: LiveResultKind, *, offset: int
    ) -> tuple[list[dict[str, Any]], bool]:
        response = await self.client.get(
            f"{LAYER_URLS[kind]}/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise LiveDataUnavailable(f"{kind.value} source returned an invalid schema")
        features = payload["features"]
        if any(
            not isinstance(feature, dict)
            or not isinstance(feature.get("properties"), dict)
            or not isinstance(feature.get("geometry"), dict)
            for feature in features
        ):
            raise LiveDataUnavailable(f"{kind.value} source returned malformed features")
        return features, bool(payload.get("exceededTransferLimit"))

    async def _refresh(self, kind: LiveResultKind) -> _CacheEntry:
        features: list[dict[str, Any]] = []
        offset = 0
        while True:
            page, exceeded = await self._fetch_page(kind, offset=offset)
            features.extend(page)
            if not exceeded and len(page) < 1000:
                break
            if not page:
                break
            offset += len(page)
        entry = _CacheEntry(
            fetched_monotonic=time.monotonic(),
            retrieved_at=datetime.now(UTC),
            features=tuple(features),
        )
        self._cache[kind] = entry
        return entry

    async def _features(self, kind: LiveResultKind) -> tuple[_CacheEntry, Freshness]:
        cached = self._cache.get(kind)
        if (
            cached is not None
            and time.monotonic() - cached.fetched_monotonic <= self.fresh_seconds
        ):
            return cached, Freshness.FRESH
        async with self._locks[kind]:
            cached = self._cache.get(kind)
            if (
                cached is not None
                and time.monotonic() - cached.fetched_monotonic <= self.fresh_seconds
            ):
                return cached, Freshness.FRESH
            try:
                return await self._refresh(kind), Freshness.FRESH
            except (
                httpx.HTTPError,
                ValueError,
                json.JSONDecodeError,
                LiveDataUnavailable,
            ) as exc:
                cached = self._cache.get(kind)
                if (
                    cached is not None
                    and time.monotonic() - cached.fetched_monotonic
                    <= self.stale_if_error_seconds
                ):
                    return cached, Freshness.STALE
                raise LiveDataUnavailable(f"{kind.value} source is unavailable") from exc

    def _to_result(
        self,
        kind: LiveResultKind,
        feature: dict[str, Any],
        *,
        retrieved_at: datetime,
        freshness: Freshness,
        location: tuple[float, float, float] | None = None,
    ) -> LiveResult:
        properties = feature["properties"]
        geometry = feature["geometry"]
        object_id = _property(properties, "OBJECTID", "objectid", "GlobalID", "FIRE_NUMBER")
        if object_id is None:
            object_id = hashlib.sha256(
                json.dumps(feature, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
        relation = GeometryRelation.UNKNOWN
        if location is not None:
            latitude, longitude, radius_km = location
            relation = geometry_relation(
                geometry,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            )
        updated = _timestamp(
            _property(
                properties,
                "LAST_UPDATED_TIMESTAMP",
                "DATE_MODIFIED",
                "LAST_UPDATED",
                "MODIFIED_ON",
                "LOAD_DATE",
                "TRACK_DATE",
                "FIRE_OUT_DATE",
                "IGNITION_DATE",
                "EVENT_START_DATE",
            )
        )
        if updated is None:
            raise ValueError("official live record has no usable source timestamp")
        size = _property(properties, "FIRE_SIZE_HECTARES", "CURRENT_SIZE", "SIZE_HA")
        return LiveResult(
            result_id=f"{kind.value}:{object_id}",
            kind=kind,
            authority=(
                "EmergencyInfoBC and issuing local authority"
                if kind == LiveResultKind.EVACUATION
                else "BC Wildfire Service"
            ),
            source_url=HttpUrl(LAYER_URLS[kind]),
            source_updated_at=updated,
            retrieved_at=retrieved_at,
            freshness=freshness,
            status=str(
                _property(
                    properties,
                    "FIRE_STATUS",
                    "ORDER_ALERT_STATUS",
                    "STATUS",
                    "EVENT_STATUS",
                )
                or "Official record"
            ),
            name=str(
                _property(
                    properties,
                    "INCIDENT_NAME",
                    "FIRE_NAME",
                    "EVENT_NAME",
                    "NAME",
                    "LOCATION_DESCRIPTION",
                )
                or "Unnamed official record"
            ),
            incident_number=(
                str(value)
                if (value := _property(properties, "FIRE_NUMBER", "INCIDENT_NUMBER"))
                is not None
                else None
            ),
            size_hectares=float(size) if isinstance(size, (int, float)) else None,
            issuer=(
                str(value)
                if (value := _property(properties, "ISSUING_AGENCY", "ISSUED_BY", "AGENCY"))
                is not None
                else None
            ),
            geometry_relation=relation,
            geometry=geometry,
        )

    async def map_results(
        self,
        *,
        layers: tuple[LiveResultKind, ...],
        bbox: tuple[float, float, float, float] | None = None,
    ) -> LiveMapResponse:
        results: list[LiveResult] = []
        unavailable: list[LiveResultKind] = []
        bounds = box(*bbox) if bbox is not None else None
        for kind in layers:
            try:
                entry, freshness = await self._features(kind)
            except LiveDataUnavailable:
                unavailable.append(kind)
                continue
            for feature in entry.features:
                properties = feature["properties"]
                status = str(
                    _property(
                        properties,
                        "FIRE_STATUS",
                        "ORDER_ALERT_STATUS",
                        "STATUS",
                        "EVENT_STATUS",
                    )
                    or ""
                ).casefold()
                if status in {"out", "inactive", "expired", "cancelled", "canceled", "rescinded"}:
                    continue
                if kind == LiveResultKind.EVACUATION:
                    event_type = str(_property(properties, "EVENT_TYPE") or "").casefold()
                    if event_type and "fire" not in event_type:
                        continue
                if bounds is not None:
                    try:
                        if not shape(feature["geometry"]).intersects(bounds):
                            continue
                    except (TypeError, ValueError):
                        continue
                try:
                    result = self._to_result(
                        kind,
                        feature,
                        retrieved_at=entry.retrieved_at,
                        freshness=freshness,
                    )
                except (TypeError, ValueError):
                    continue
                results.append(result)
        return LiveMapResponse(
            generated_at=datetime.now(UTC),
            results=results,
            unavailable_layers=unavailable,
            limitations=[
                "Official records can change quickly; confirm emergency directions with the issuing authority.",
                "No matching record is not a safety determination.",
            ],
        )

    async def nearby_results(self, location: LocationInput) -> LiveMapResponse:
        latitude, longitude = await self.resolve_location(location)
        response = await self.map_results(layers=tuple(LiveResultKind))
        related: list[LiveResult] = []
        for result in response.results:
            relation = geometry_relation(
                result.geometry,
                latitude=latitude,
                longitude=longitude,
                radius_km=location.radius_km,
            )
            if relation in {GeometryRelation.INSIDE, GeometryRelation.NEARBY}:
                related.append(result.model_copy(update={"geometry_relation": relation}))
        return response.model_copy(update={"results": related})
