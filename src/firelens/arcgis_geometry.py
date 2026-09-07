"""Decode native ArcGIS polygon rings without modifying any coordinates.

Esri exterior rings are clockwise, interior rings counterclockwise. The
official GeoJSON exporter can lose that relationship. Decode it before the
existing geometry validator; never fix, simplify, union or buffer boundaries.
"""

import json
from typing import Any

from shapely.geometry import Polygon

from firelens.contracts import LiveResultKind
from firelens.live_support import (
    LiveDataUnavailable,
    geojson_crs_is_wgs84,
    geometry_integrity_errors,
)


def polygon_geojson(geometry: dict[str, Any]) -> dict[str, Any]:
    """Reject ambiguous or invalid rings instead of inventing a polygon."""

    if (
        not geojson_crs_is_wgs84(geometry)
        or "curveRings" in geometry
        or geometry.get("hasZ")
        or geometry.get("hasM")
    ):
        raise ValueError("unsupported native polygon representation")
    rings = geometry.get("rings")
    # Bound containment work as well as the adapter's existing byte limits.
    if not isinstance(rings, list) or not 1 <= len(rings) <= 512:
        raise ValueError("invalid or excessive native polygon rings")
    shells: list[tuple[list[Any], Polygon]] = []
    holes: list[tuple[list[Any], Polygon]] = []
    for ring in rings:
        if (
            not isinstance(ring, list)
            or len(ring) < 4
            or ring[0] != ring[-1]
            or any(not isinstance(p, list) or len(p) != 2 for p in ring)
            or geometry_integrity_errors({"type": "Polygon", "coordinates": [ring]})
        ):
            raise ValueError("invalid native polygon ring")
        polygon = Polygon(ring)
        (holes if polygon.exterior.is_ccw else shells).append((ring, polygon))
    if not shells:
        raise ValueError("native polygon has no exterior")
    coordinates = [[ring] for ring, _ in shells]
    for ring, hole in holes:
        owners = [i for i, (_, shell) in enumerate(shells) if shell.covers(hole)]
        if not owners:
            raise ValueError("native interior ring has no containing exterior")
        # Nested islands may have their own holes. The smallest containing
        # exterior owns a hole; final topology validation rejects overlaps.
        owner = min(owners, key=lambda i: shells[i][1].area)
        coordinates[owner].append(ring)
    result = (
        {"type": "Polygon", "coordinates": coordinates[0]}
        if len(coordinates) == 1
        else {"type": "MultiPolygon", "coordinates": coordinates}
    )
    if geometry_integrity_errors(result):
        raise ValueError("invalid native polygon topology")
    return result


def decode_features(
    payload: Any, kind: LiveResultKind, max_feature_geometry_bytes: int
) -> tuple[list[dict[str, Any]], bool]:
    """Normalize native polygons or retain the existing GeoJSON contract."""
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise LiveDataUnavailable(f"{kind.value} source returned an invalid schema")
    if not geojson_crs_is_wgs84(payload):
        raise LiveDataUnavailable(f"{kind.value} source declared an unsupported output CRS")
    features = payload["features"]
    if payload.get("geometryType") == "esriGeometryPolygon":
        if (
            payload.get("spatialReference") is None
            or payload.get("hasZ")
            or payload.get("hasM")
        ):
            raise LiveDataUnavailable(
                f"{kind.value} source declared unsupported polygon coordinates"
            )
        converted = []
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
                raise LiveDataUnavailable(f"{kind.value} source returned malformed features")
            geometry = feature.get("geometry")
            if isinstance(geometry, dict):
                if len(json.dumps(geometry).encode("utf-8")) > max_feature_geometry_bytes:
                    raise LiveDataUnavailable(
                        f"{kind.value} source exceeded the per-feature geometry limit"
                    )
                try:
                    geometry = polygon_geojson(geometry)
                except ValueError:
                    # Retain the invalid native geometry for quarantine,
                    # identity and byte accounting. Never synthesize a shape.
                    pass
            converted.append(
                {
                    "type": "Feature",
                    "properties": feature["attributes"],
                    "geometry": geometry,
                }
            )
        features = converted
    if any(
        not isinstance(feature, dict)
        or not isinstance(feature.get("properties"), dict)
        or not isinstance(feature.get("geometry"), dict)
        for feature in features
    ):
        raise LiveDataUnavailable(f"{kind.value} source returned malformed features")
    return features, bool(payload.get("exceededTransferLimit"))
