"""Stable identity for official live records.

ArcGIS ``OBJECTID`` is reassigned whenever BC Wildfire Service republishes a
public view (observed: the same fire was ``1201`` at 02:20Z and ``1111`` at
02:31Z), so it cannot identify a record across conversation turns. Fires and
perimeters carry the official ``FIRE_NUMBER``. Evacuation rows carry no stable
key (``EMRG_OAA_SYSID`` equals ``OBJECTID`` in the public view), so their
identity is the official description a person reads: event, order/alert name,
issuing agency and status. Duplicate keys inside one fetch are numbered in
fetch order so no record is ever dropped or merged.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from firelens.live_contracts import LiveResultKind
from firelens.live_support import property_value as _property

_EVACUATION_DESCRIPTION_FIELDS = (
    "EVENT_NAME",
    "ORDER_ALERT_NAME",
    "ISSUING_AGENCY",
    "ORDER_ALERT_STATUS",
)


def _text(value: Any) -> str:
    return " ".join(str(value).split()).casefold() if value is not None else ""


def record_key(kind: LiveResultKind, properties: Mapping[str, Any]) -> str | None:
    """The stable official key of one feature, or None when the row has none."""

    if kind in {LiveResultKind.INCIDENT, LiveResultKind.PERIMETER}:
        fire_number = _property(properties, "FIRE_NUMBER", "INCIDENT_NUMBER")
        if fire_number is not None and str(fire_number).strip():
            return str(fire_number).strip().upper()
        global_id = _property(properties, "GlobalID")
        return str(global_id) if global_id is not None else None
    parts = [_text(_property(properties, field)) for field in _EVACUATION_DESCRIPTION_FIELDS]
    if not any(parts):
        return None
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _fallback_key(feature: Mapping[str, Any]) -> str:
    # Rows without an official key fall back to the row id, which is only
    # stable until the publisher rebuilds the view.
    object_id = _property(feature["properties"], "OBJECTID", "objectid")
    if object_id is not None:
        return str(object_id)
    return hashlib.sha256(
        repr(sorted(feature["properties"].items())).encode("utf-8")
    ).hexdigest()[:16]


def record_ids(kind: LiveResultKind, features: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """``"<kind>:<key>"`` for every feature of one fetched layer, in fetch order.

    A key shared by several rows (two polygons of one evacuation order) is
    suffixed ``#2``, ``#3`` … so each row keeps a distinct id.
    """

    keys = [
        record_key(kind, feature["properties"]) or _fallback_key(feature)
        for feature in features
    ]
    counts: dict[str, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    seen: dict[str, int] = {}
    ids: list[str] = []
    for key in keys:
        if counts[key] == 1:
            ids.append(f"{kind.value}:{key}")
            continue
        seen[key] = seen.get(key, 0) + 1
        suffix = "" if seen[key] == 1 else f"#{seen[key]}"
        ids.append(f"{kind.value}:{key}{suffix}")
    return tuple(ids)


def feature_identity(kind: LiveResultKind, feature: Mapping[str, Any]) -> str:
    """Row identity used only to detect repeated or stalled pages within one fetch."""

    properties = feature["properties"]
    object_id = _property(properties, "OBJECTID", "objectid", "GlobalID", "FIRE_NUMBER")
    if object_id is not None:
        return f"{kind.value}:{object_id}"
    return hashlib.sha256(json.dumps(feature, sort_keys=True).encode("utf-8")).hexdigest()
