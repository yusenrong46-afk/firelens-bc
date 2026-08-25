"""Immutable official-layer policy and conservative live geometry helpers."""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal

import httpx
from pydantic import HttpUrl
from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from firelens.contracts import GeometryRelation, LiveResultKind, LocationInput
from firelens.live_contracts import COORDINATE_ORDER as COORDINATE_ORDER
from firelens.live_contracts import DISTANCE_ALGORITHM as DISTANCE_ALGORITHM
from firelens.live_contracts import DISTANCE_UNIT as DISTANCE_UNIT
from firelens.live_contracts import GEODESIC_CRS as GEODESIC_CRS
from firelens.live_contracts import Freshness, bind_distance_derivation


def geojson_crs_is_wgs84(payload: dict[str, Any]) -> bool:
    """Reject a response that explicitly declares a non-WGS84 output CRS.

    ArcGIS GeoJSON normally omits CRS because the query requests ``outSR=4326``.
    When a server does declare one, accepting a projected or unknown declaration
    would make the downstream longitude/latitude geodesic contract false.
    """

    spatial_reference = payload.get("spatialReference")
    if spatial_reference is not None:
        if not isinstance(spatial_reference, dict):
            return False
        wkid = spatial_reference.get("latestWkid", spatial_reference.get("wkid"))
        if not isinstance(wkid, (int, str)):
            return False
        try:
            return int(wkid) == 4326
        except (TypeError, ValueError):
            return False

    crs = payload.get("crs")
    if crs is None:
        return True
    if not isinstance(crs, dict):
        return False
    properties = crs.get("properties")
    if not isinstance(properties, dict):
        return False
    name = properties.get("name")
    if not isinstance(name, str):
        return False
    normalized = name.strip().casefold().replace("::", ":")
    return normalized.endswith("epsg:4326") or normalized.endswith("crs84")


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

# The public ActiveFires view exposes FIRE_CENTRE as an integer without a
# coded-value domain. BCWS fire numbers expose the corresponding centre prefix,
# and the official Fire Zone Boundaries layer supplies the human-readable
# centre names for those prefixes. Keep the public response label-only: an
# unknown numeric code is omitted rather than rendered as if it were a place.
FIRE_CENTRE_CODE_NAMES = MappingProxyType(
    {
        2: "Coastal Fire Centre",
        3: "Northwest Fire Centre",
        4: "Prince George Fire Centre",
        5: "Kamloops Fire Centre",
        6: "Southeast Fire Centre",
        7: "Cariboo Fire Centre",
    }
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
            if name.casefold() in {"fire_centre", "fire_center"}:
                label = fire_centre_label(value)
                if label is not None:
                    return label
                continue
            return value
    return None


def fire_centre_label(value: Any) -> str | None:
    """Return an official human label, never an unexplained numeric code."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return FIRE_CENTRE_CODE_NAMES.get(value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return FIRE_CENTRE_CODE_NAMES.get(int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdecimal():
            return FIRE_CENTRE_CODE_NAMES.get(int(stripped))
        return stripped
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
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    return None


def _positions(coords: Any) -> list[tuple[float, float]]:
    if not isinstance(coords, (list, tuple)) or not coords:
        return []
    first = coords[0]
    if isinstance(first, (int, float)):
        if len(coords) < 2:
            return []
        return [(float(coords[0]), float(coords[1]))]
    positions: list[tuple[float, float]] = []
    for item in coords:
        positions.extend(_positions(item))
    return positions


def geometry_integrity_errors(geometry: dict[str, Any] | None) -> list[str]:
    """Return deterministic reasons a geometry cannot be used for measurement."""

    if not isinstance(geometry, dict):
        return ["null_geometry"]
    if geometry.get("coordinates") is None and geometry.get("type") != "GeometryCollection":
        return ["null_geometry"]
    errors: list[str] = []
    for longitude, latitude in _positions(geometry.get("coordinates")):
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            errors.append("non_finite_coordinate")
            break
        if 48.0 <= longitude <= 61.0 and -140.0 <= latitude <= -113.0:
            errors.append("latitude_longitude_reversal")
            break
        if abs(latitude) > 90.0 or abs(longitude) > 180.0:
            errors.append("out_of_range_coordinate")
            break
    try:
        target = shape(geometry)
    except (TypeError, ValueError, AttributeError):
        errors.append("malformed_geometry")
        return list(dict.fromkeys(errors))
    if target.is_empty:
        errors.append("empty_geometry")
    elif not target.is_valid:
        errors.append("invalid_geometry")
    return list(dict.fromkeys(errors))


def distance_basis_for(
    kind: LiveResultKind, geometry: dict[str, Any]
) -> Literal["incident_point", "perimeter_boundary"] | None:
    """Bind a distance label to both record kind and actual geometry type."""

    if geometry_integrity_errors(geometry):
        return None
    geom_type = geometry.get("type") if isinstance(geometry, dict) else None
    if kind == LiveResultKind.INCIDENT and geom_type == "Point":
        return "incident_point"
    if kind == LiveResultKind.PERIMETER and geom_type in {"Polygon", "MultiPolygon"}:
        return "perimeter_boundary"
    return None


def annotated_distance_fields(
    *,
    result_id: str,
    kind: LiveResultKind,
    geometry: dict[str, Any],
    latitude: float,
    longitude: float,
    freshness: Freshness,
) -> dict[str, object]:
    """Return canonical distance fields, or empty when measurement is not allowed."""

    if kind not in {LiveResultKind.INCIDENT, LiveResultKind.PERIMETER}:
        return {}
    basis = distance_basis_for(kind, geometry)
    if basis is None:
        return {}
    distance = distance_to_geometry_km(geometry, latitude=latitude, longitude=longitude)
    if distance is None:
        return {}
    rounded = round(float(distance), 1)
    return {
        "distance_km": rounded,
        "distance_basis": basis,
        "distance_derivation": bind_distance_derivation(
            result_id=result_id,
            distance_km=rounded,
            distance_basis=basis,
            calculated_at=datetime.now(UTC),
            extra_input_ids=(f"place:{latitude:.2f},{longitude:.2f}",),
            input_freshness=freshness,
        ),
    }


def authority(kind: LiveResultKind) -> str:
    return (
        "EmergencyInfoBC and issuing local authority"
        if kind == LiveResultKind.EVACUATION
        else "BC Wildfire Service"
    )


# A bare official locality currently scores 67 in the BC Address Geocoder. A
# server-side floor of 70 therefore removes valid communities before FireLens
# can inspect them. Ask only for locality candidates at a modest candidate
# floor, then require an exact normalized BC locality identity below.
GEOCODER_MIN_SCORE = 60
GEOCODER_ACCEPTED_PRECISIONS = frozenset({"LOCALITY"})
GEOCODER_MAX_CANDIDATES = 5

_HttpGet = Callable[..., Awaitable[httpx.Response]]


def _normalized_locality_name(value: str) -> str:
    normalized = " ".join(value.split()).casefold().strip(" .,?")
    normalized = re.sub(
        r"(?:,?\s+(?:bc|b\.c\.|british columbia|canada))+$",
        "",
        normalized,
    )
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def _exact_bc_locality(features: list[object], label: str) -> dict[str, Any] | None:
    requested = _normalized_locality_name(label)
    if not requested:
        return None
    for candidate in features:
        if not isinstance(candidate, dict):
            continue
        properties = candidate.get("properties")
        if not isinstance(properties, dict):
            continue
        score = properties.get("score")
        precision = properties.get("matchPrecision")
        province = properties.get("provinceCode")
        locality = properties.get("localityName")
        is_official = properties.get("isOfficial")
        if (
            not isinstance(score, (int, float))
            or score < GEOCODER_MIN_SCORE
            or not isinstance(precision, str)
            or precision.strip().upper() not in GEOCODER_ACCEPTED_PRECISIONS
            or not isinstance(province, str)
            or province.strip().upper() != "BC"
            or not isinstance(locality, str)
            or not (
                is_official is True
                or (isinstance(is_official, str) and is_official.strip().casefold() == "true")
            )
        ):
            continue
        official = _normalized_locality_name(locality)
        if official == requested or official.startswith(f"{requested} in "):
            return candidate
    return None


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
                "maxResults": GEOCODER_MAX_CANDIDATES,
                "outputSRS": 4326,
                "echo": "false",
                "minScore": GEOCODER_MIN_SCORE,
                "matchPrecision": "locality",
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
    first = _exact_bc_locality(features, location.label)
    if first is None:
        raise LiveDataUnavailable(
            "the place label did not exactly match a British Columbia community",
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

    if geometry_integrity_errors(geometry):
        return None
    try:
        target = shape(geometry)
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

    if geometry_integrity_errors(geometry):
        return GeometryRelation.UNKNOWN
    try:
        target = shape(geometry)
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

    if geometry is None or geometry_integrity_errors(geometry):
        return "invalid"
    try:
        candidate = shape(geometry)
        if bounds is not None and not candidate.intersects(bounds):
            return "outside"
        return "ok"
    except (TypeError, ValueError, AttributeError):
        return "invalid"
