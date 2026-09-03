"""Closed enums shared by the typed intent parser and its span helpers."""

from __future__ import annotations

from enum import StrEnum


class ClauseIntentKind(StrEnum):
    """Application-owned clause classes; none grants publication authority."""

    LIVE_RECORDS = "live_records"
    REVIEWED_GUIDANCE = "reviewed_guidance"
    PRODUCT_HELP = "product_help"
    STATIC_BACKGROUND = "static_background"
    OTHER = "other"


class TemporalScope(StrEnum):
    """Time ownership used to prevent historical/future text becoming live."""

    CURRENT = "current"
    NONCURRENT = "noncurrent"
    UNSPECIFIED = "unspecified"


class RecordOperation(StrEnum):
    """Bounded operations supported by deterministic live-record tools."""

    LIST = "list"
    LOCATE = "locate"
    STATUS = "status"
    ANALYZE = "analyze"
    PERIMETER = "perimeter"
    EVACUATION = "evacuation"
