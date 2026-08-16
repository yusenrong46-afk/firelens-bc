"""Immutable official-layer policy and conservative live geometry helpers."""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import HttpUrl
from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from firelens.contracts import GeometryRelation, LiveResultKind, LocationInput

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


# BC Geocoder match-quality gate. Scores below this are fuzzy guesses, and
# PROVINCE/STREET-precision matches mean the label was not a specific BC
# community (e.g. "Calgary" fuzzy-matching a street, or "hectares" matching
# the province centroid). Test doubles may omit these fields; absent fields
# are accepted so only a present-but-poor match fails closed.
GEOCODER_MIN_SCORE = 70
GEOCODER_ACCEPTED_PRECISIONS = frozenset(
    {"LOCALITY", "CIVIC_NUMBER", "BLOCK", "SITE", "UNIT", "INTERSECTION", "OCCUPANT"}
)

_HttpGet = Callable[..., Awaitable[httpx.Response]]


async def resolve_bc_location(get: _HttpGet, location: LocationInput) -> tuple[float, float]:
    """Resolve a coarse label to rounded BC coordinates, failing closed."""

    if location.latitude is not None and location.longitude is not None:
        return location.latitude, location.longitude
    if location.label is None:
        raise LiveDataUnavailable("a coarse location is required for a nearby query")
    try:
        response = await get(
            BC_GEOCODER_URL,
            params={
                "addressString": location.label,
                "maxResults": 1,
                "outputSRS": 4326,
                "echo": "false",
                "minScore": GEOCODER_MIN_SCORE,
            },
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LiveDataUnavailable(
            "the official place service timed out",
            kind=LiveDataErrorKind.TIMEOUT,
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise LiveDataUnavailable(
            "the official place service returned an error",
            kind=LiveDataErrorKind.UPSTREAM_HTTP,
        ) from exc
    except httpx.HTTPError as exc:
        raise LiveDataUnavailable(
            "the official place service could not be reached",
            kind=LiveDataErrorKind.UNREACHABLE,
        ) from exc
    try:
        payload = response.json()
    except (UnicodeDecodeError, ValueError) as exc:
        raise LiveDataUnavailable(
            "the official place service returned invalid data",
            kind=LiveDataErrorKind.INVALID_RESPONSE,
        ) from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        raise LiveDataUnavailable(
            "the place label could not be resolved",
            kind=LiveDataErrorKind.NOT_FOUND,
        )
    first = features[0]
    properties = first.get("properties") if isinstance(first, dict) else None
    if isinstance(properties, dict):
        score = properties.get("score")
        if isinstance(score, (int, float)) and score < GEOCODER_MIN_SCORE:
            raise LiveDataUnavailable(
                "the place label did not confidently match a British Columbia place",
                kind=LiveDataErrorKind.NOT_FOUND,
            )
        precision = properties.get("matchPrecision")
        if (
            isinstance(precision, str)
            and precision.strip()
            and precision.strip().upper() not in GEOCODER_ACCEPTED_PRECISIONS
        ):
            raise LiveDataUnavailable(
                "the place label did not match a specific British Columbia community",
                kind=LiveDataErrorKind.NOT_FOUND,
            )
    geometry = first.get("geometry") if isinstance(first, dict) else None
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise LiveDataUnavailable(
            "the official place service returned invalid coordinates",
            kind=LiveDataErrorKind.INVALID_RESPONSE,
        )
    try:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
    except (TypeError, ValueError) as exc:
        raise LiveDataUnavailable(
            "the official place service returned invalid coordinates",
            kind=LiveDataErrorKind.INVALID_RESPONSE,
        ) from exc
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not 48.0 <= latitude <= 61.0
        or not -140.0 <= longitude <= -113.0
    ):
        raise LiveDataUnavailable(
            "the official place service returned coordinates outside British Columbia",
            kind=LiveDataErrorKind.INVALID_RESPONSE,
        )
    return round(latitude, 2), round(longitude, 2)


def _geodesic_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    _forward, _back, distance_m = WGS84_GEOD.inv(*first, *second)
    return float(distance_m) / 1_000


def distance_to_geometry_km(
    geometry: dict[str, Any], *, latitude: float, longitude: float
) -> float | None:
    """Return geodesic distance to a point or nearest valid geometry boundary."""

    try:
        target = shape(geometry)
        if target.is_empty or not target.is_valid:
            return None
        point = Point(longitude, latitude)
        if isinstance(target, Point):
            distance = _geodesic_km((longitude, latitude), (float(target.x), float(target.y)))
        elif target.contains(point) or target.touches(point):
            return 0.0
        else:
            nearest = nearest_points(point, target)[1]
            distance = _geodesic_km((longitude, latitude), (float(nearest.x), float(nearest.y)))
        return distance if math.isfinite(distance) else None
    except (TypeError, ValueError):
        return None


def geometry_relation(
    geometry: dict[str, Any], *, latitude: float, longitude: float, radius_km: float
) -> GeometryRelation:
    """Compute a conservative relation with boundary points treated as inside."""

    try:
        target = shape(geometry)
        if target.is_empty or not target.is_valid:
            return GeometryRelation.UNKNOWN
        point = Point(longitude, latitude)
        if not isinstance(target, Point) and (target.contains(point) or target.touches(point)):
            return GeometryRelation.INSIDE
        distance = distance_to_geometry_km(geometry, latitude=latitude, longitude=longitude)
        if distance is None:
            return GeometryRelation.UNKNOWN
        return GeometryRelation.NEARBY if distance <= radius_km else GeometryRelation.OUTSIDE
    except (TypeError, ValueError):
        return GeometryRelation.UNKNOWN


def map_geometry_state(geometry: dict[str, Any] | None, bounds: BaseGeometry | None) -> str:
    """Classify a feature as ok, spatially invalid, or outside the requested bbox."""

    if not isinstance(geometry, dict):
        return "invalid"
    try:
        candidate = shape(geometry)
        if candidate.is_empty or not candidate.is_valid:
            return "invalid"
        if bounds is not None and not candidate.intersects(bounds):
            return "outside"
        return "ok"
    except (TypeError, ValueError, AttributeError):
        return "invalid"
