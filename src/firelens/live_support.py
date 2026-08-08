"""Immutable official-layer policy and conservative live geometry helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import HttpUrl
from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from firelens.contracts import GeometryRelation, LiveResultKind

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
OFFICIAL_FALLBACK_URLS: tuple[HttpUrl, ...] = (
    HttpUrl("https://wildfiresituation.nrs.gov.bc.ca/map"),
    HttpUrl("https://www.emergencyinfobc.gov.bc.ca/"),
)

WGS84_GEOD = Geod(ellps="WGS84")

_BBox = tuple[float, float, float, float]
_CacheKey = tuple[LiveResultKind, _BBox | None]


class LiveDataErrorKind(StrEnum):
    TIMEOUT = "timeout"
    UPSTREAM_HTTP = "upstream_http"
    UNREACHABLE = "unreachable"
    INVALID_RESPONSE = "invalid_response"
    NOT_FOUND = "not_found"
    NOT_CONFIGURED = "not_configured"
    BOUNDED_LIMIT = "bounded_limit"
    UNKNOWN = "unknown"


class LiveDataUnavailable(RuntimeError):
    """Sanitized, classified failure from an official live-data dependency."""

    def __init__(
        self,
        message: str,
        *,
        kind: LiveDataErrorKind = LiveDataErrorKind.UNKNOWN,
    ) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class LayerDefinition:
    url: str
    expected_name: str
    required_fields: frozenset[str]


DEFAULT_LAYER_DEFINITIONS: dict[LiveResultKind, LayerDefinition] = {
    LiveResultKind.INCIDENT: LayerDefinition(
        url=ACTIVE_FIRES_URL,
        expected_name="BCWS_ActiveFires_Points",
        required_fields=frozenset({"OBJECTID", "FIRE_STATUS", "FIRE_NUMBER", "INCIDENT_NAME"}),
    ),
    LiveResultKind.PERIMETER: LayerDefinition(
        url=FIRE_PERIMETERS_URL,
        expected_name="Fire Perimeters",
        required_fields=frozenset(
            {"OBJECTID", "FIRE_STATUS", "FIRE_NUMBER", "FIRE_SIZE_HECTARES"}
        ),
    ),
    LiveResultKind.EVACUATION: LayerDefinition(
        url=EVACUATIONS_URL,
        expected_name="Evacuation Orders and Alerts - View",
        required_fields=frozenset(
            {"OBJECTID", "ORDER_ALERT_STATUS", "EVENT_TYPE", "DATE_MODIFIED"}
        ),
    ),
}
LAYER_URLS = {kind: definition.url for kind, definition in DEFAULT_LAYER_DEFINITIONS.items()}


@dataclass(frozen=True)
class CacheEntry:
    fetched_monotonic: float
    retrieved_at: datetime
    source_updated_at: datetime
    features: tuple[dict[str, Any], ...]


def property_value(properties: dict[str, Any], *names: str) -> Any:
    folded = {str(key).casefold(): value for key, value in properties.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value not in (None, ""):
            return value
    return None


def timestamp(value: Any) -> datetime | None:
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


def authority(kind: LiveResultKind) -> str:
    return (
        "EmergencyInfoBC and issuing local authority"
        if kind == LiveResultKind.EVACUATION
        else "BC Wildfire Service"
    )


def _geodesic_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    _forward, _back, distance_m = WGS84_GEOD.inv(*first, *second)
    return float(distance_m) / 1_000


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
            distance = _geodesic_km((longitude, latitude), (float(target.x), float(target.y)))
        else:
            if target.contains(point) or target.touches(point):
                return GeometryRelation.INSIDE
            nearest = nearest_points(point, target)[1]
            distance = _geodesic_km((longitude, latitude), (float(nearest.x), float(nearest.y)))
        if not math.isfinite(distance):
            return GeometryRelation.UNKNOWN
        return GeometryRelation.NEARBY if distance <= radius_km else GeometryRelation.OUTSIDE
    except (TypeError, ValueError):
        return GeometryRelation.UNKNOWN
