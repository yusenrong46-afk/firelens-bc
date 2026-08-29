"""Private, content-free OpenRouter accounting primitives for ProductBench."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import httpx


def _finite_nonnegative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


async def require_productbench_key_cap(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: Mapping[str, str],
    max_cost_usd: float,
) -> dict[str, object]:
    """Read the current-key metadata and require a server-enforced run ceiling.

    OpenRouter's ``GET /api/v1/key`` response exposes both the configured key
    ``limit`` and ``limit_remaining``.  ProductBench needs the configured cap,
    rather than an account-wide usage delta, to make a requested run budget a
    provider-enforced boundary before any billable call begins.
    """

    if (
        isinstance(max_cost_usd, bool)
        or not isinstance(max_cost_usd, int | float)
        or not math.isfinite(float(max_cost_usd))
        or max_cost_usd <= 0
    ):
        raise ValueError("ProductBench requires a finite positive cost ceiling")
    try:
        response = await client.get(f"{base_url.rstrip('/')}/key", headers=dict(headers))
    except httpx.HTTPError as exc:
        raise ValueError(
            "ProductBench could not read the current OpenRouter key limit"
        ) from exc
    if response.status_code != 200:
        raise ValueError("ProductBench could not verify the current OpenRouter key limit")
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("ProductBench received invalid current-key metadata") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("ProductBench received invalid current-key metadata")
    limit = _finite_nonnegative(data.get("limit"))
    remaining = _finite_nonnegative(data.get("limit_remaining"))
    if (
        limit is None
        or remaining is None
        or limit <= 0
        or remaining <= 0
        or remaining > limit
        or limit > float(max_cost_usd)
        or remaining > float(max_cost_usd)
    ):
        raise ValueError(
            "ProductBench requires a finite positive OpenRouter key limit and "
            "remaining limit no greater than --max-cost-usd"
        )
    reset = data.get("limit_reset")
    return {
        "key_limit_usd": limit,
        "key_limit_remaining_usd": remaining,
        "key_limit_reset": reset if isinstance(reset, str) or reset is None else None,
    }


def _safe_usage(value: object) -> dict[str, str | int | float | bool | None]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str)
        and isinstance(item, str | int | float | bool | type(None))
        and (not isinstance(item, float) or math.isfinite(item))
    }


def receipt(
    *,
    stage: str,
    endpoint: str,
    body: dict[str, Any],
    attempts: int,
) -> dict[str, object]:
    """Return a sanitized success receipt without retaining model output text."""

    usage = _safe_usage(body.get("usage"))
    cost = _finite_nonnegative(usage.get("cost"))
    response_id = body.get("id")
    model = body.get("model")
    return {
        "stage": stage,
        "endpoint": endpoint,
        "provider_response_id": response_id if isinstance(response_id, str) else None,
        "model": model if isinstance(model, str) else None,
        "attempts": attempts,
        "usage": usage,
        "cost_usd": cost,
        "cost_evidence": (
            "provider_usage_cost_explicit_zero"
            if cost == 0.0
            else "provider_usage_cost"
            if cost is not None
            else "missing"
        ),
    }
