"""Admit individually validated official records and retain coverage omissions."""

from __future__ import annotations

from typing import Any

from pydantic import HttpUrl
from shapely.geometry.base import BaseGeometry

from firelens.contracts import (
    LiveLayerStatus,
    LiveResult,
    LiveResultKind,
    freshness_for_observation,
)
from firelens.live_identity import record_ids
from firelens.live_support import (
    LiveDataUnavailable,
    _BBox,
    authority,
    map_geometry_state,
    property_value,
)


async def map_layer_results(
    self: Any,
    kind: LiveResultKind,
    *,
    bbox: _BBox | None,
    bounds: BaseGeometry | None,
    allow_partial_geometry: bool = False,
    evacuation_statuses: tuple[str, ...] = (),
) -> tuple[list[LiveResult], LiveLayerStatus, str | None]:
    try:
        entry, freshness = await self._features(kind, bbox=bbox)
    except LiveDataUnavailable as exc:
        return [], self._unavailable_status(kind), str(exc)
    results: list[LiveResult] = []
    omitted_geometry_count = 0
    omitted_status_count = 0
    for feature, result_id in zip(
        entry.features, record_ids(kind, entry.features), strict=True
    ):
        properties = feature["properties"]
        status = (
            str(
                property_value(
                    properties,
                    "FIRE_STATUS",
                    "ORDER_ALERT_STATUS",
                    "STATUS",
                    "EVENT_STATUS",
                )
                or ""
            )
            .strip()
            .casefold()
        )
        if status in {
            "out",
            "inactive",
            "expired",
            "cancelled",
            "canceled",
            "rescinded",
        }:
            continue
        if kind == LiveResultKind.EVACUATION:
            event_type = str(property_value(properties, "EVENT_TYPE") or "").casefold()
            if event_type and "fire" not in event_type:
                continue
        if kind == LiveResultKind.EVACUATION:
            if status in {"order", "alert", "tactical evacuation", "all clear"}:
                if evacuation_statuses and status not in evacuation_statuses:
                    continue
            else:
                omitted_status_count += 1
                continue
        state = map_geometry_state(feature.get("geometry"), bounds)
        if state == "outside":
            continue
        if state == "invalid":
            if allow_partial_geometry:
                omitted_geometry_count += 1
                continue
            limitation = f"{kind.value} source returned spatially invalid geometry"
            return [], self._unavailable_status(kind, invalid_geometry=True), limitation
        try:
            result = self._to_result(
                kind,
                feature,
                result_id=result_id,
                retrieved_at=entry.retrieved_at,
                freshness=freshness,
                source_updated_at=entry.source_updated_at,
            )
        except (TypeError, ValueError):
            limitation = f"{kind.value} source returned a record that did not match the live result contract"
            return [], self._unavailable_status(kind), limitation
        results.append(result)
    return (
        results,
        LiveLayerStatus(
            kind=kind,
            authority=authority(kind),
            source_url=HttpUrl(self._layer(kind).url),
            available=True,
            source_updated_at=entry.source_updated_at,
            retrieved_at=entry.retrieved_at,
            freshness=freshness_for_observation(
                freshness,
                source_updated_at=entry.source_updated_at,
                retrieved_at=entry.retrieved_at,
            ),
            matching_result_count=len(results),
            omitted_geometry_count=omitted_geometry_count,
            omitted_status_count=omitted_status_count,
        ),
        None,
    )
