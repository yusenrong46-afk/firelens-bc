"""Privacy-safe structured operational events."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

LOGGER_NAME = "firelens.operations"


def log_operation(
    *,
    trace_id: str,
    route: str,
    response_mode: str,
    latency_ms: float,
    provider_stages: Sequence[str] = (),
    error_category: str | None = None,
) -> None:
    """Log only the allowlisted operational fields; never accept request content."""

    event = {
        "event": "firelens_request",
        "trace_id": trace_id,
        "route": route,
        "response_mode": response_mode,
        "latency_ms": round(max(latency_ms, 0.0), 1),
        "provider_stages": sorted(set(provider_stages)),
        "error_category": error_category,
    }
    logging.getLogger(LOGGER_NAME).info(
        json.dumps(event, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    )
