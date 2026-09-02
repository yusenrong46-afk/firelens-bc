"""Bounded official live-map and Near Me routes."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from firelens.api.responses import ERROR_RESPONSES, deadline_response, error_response
from firelens.config import FireLensConfig
from firelens.contracts import (
    LiveCurrentSummary,
    LiveMapResponse,
    LiveResultKind,
    NearMeRequest,
    NearMeResponse,
    ResponseMode,
    ResponseStatus,
)
from firelens.live import LiveDataErrorKind, LiveDataService, LiveDataUnavailable
from firelens.operational_logging import log_operation

_LAYER_ALIASES = {
    "incidents": LiveResultKind.INCIDENT,
    "perimeters": LiveResultKind.PERIMETER,
    "evacuations": LiveResultKind.EVACUATION,
}


def _requested_layers(layers: str) -> tuple[tuple[LiveResultKind, ...], list[str]]:
    names = [part.strip() for part in layers.split(",") if part.strip()]
    unknown = sorted(set(names) - _LAYER_ALIASES.keys())
    requested = tuple(
        dict.fromkeys(_LAYER_ALIASES[name] for name in names if name in _LAYER_ALIASES)
    )
    return requested, unknown


def _parsed_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    values = tuple(float(value) for value in bbox.split(","))
    if (
        len(values) != 4
        or not all(math.isfinite(value) for value in values)
        or not (-180 <= values[0] < values[2] <= 180)
        or not (-90 <= values[1] < values[3] <= 90)
    ):
        raise ValueError
    return values


def _live_failure_response(
    exc: LiveDataUnavailable,
    *,
    config: FireLensConfig,
    request_started: float,
    route: str,
) -> JSONResponse:
    trace_id = uuid4().hex
    status_code = {
        LiveDataErrorKind.NOT_FOUND: 404,
        LiveDataErrorKind.INVALID_RESPONSE: 502,
    }.get(exc.kind, 503)
    log_operation(
        trace_id=trace_id,
        route=route,
        response_mode=ResponseMode.ABSTENTION.value,
        status=ResponseStatus.ERROR.value,
        latency_ms=(perf_counter() - request_started) * 1_000,
        error_category=f"live_{exc.kind.value}",
        release_version=config.release_version,
        build_commit=config.build_commit,
        deployment_environment=config.deployment_environment,
    )
    return error_response(
        status_code,
        trace_id=trace_id,
        error_kind=f"live_{exc.kind.value}",
        message=str(exc),
        retryable=exc.kind
        in {
            LiveDataErrorKind.TIMEOUT,
            LiveDataErrorKind.UPSTREAM_HTTP,
            LiveDataErrorKind.UNREACHABLE,
        },
    )


def install_live_routes(
    app: FastAPI,
    config: FireLensConfig,
    current_live_service: Callable[[], LiveDataService],
) -> None:
    async def map_request(
        bbox: str | None,
        layers: str,
    ) -> LiveMapResponse | JSONResponse:
        requested, unknown = _requested_layers(layers)
        if not requested or unknown:
            detail = " Unsupported layers: " + ", ".join(unknown) + "." if unknown else ""
            return error_response(
                400,
                trace_id=uuid4().hex,
                error_kind="invalid_request",
                message="Select only supported live map layers." + detail,
            )
        try:
            parsed_bbox = _parsed_bbox(bbox)
        except ValueError:
            return error_response(
                400,
                trace_id=uuid4().hex,
                error_kind="invalid_request",
                message="bbox must be minLongitude,minLatitude,maxLongitude,maxLatitude.",
            )
        return await current_live_service().map_results(layers=requested, bbox=parsed_bbox)

    @app.get(
        "/api/v1/live/map",
        response_model=LiveMapResponse,
        responses=ERROR_RESPONSES,
    )
    async def live_map(
        bbox: str | None = Query(default=None, max_length=100),
        layers: str = Query(default="incidents,perimeters,evacuations", max_length=100),
    ) -> LiveMapResponse | JSONResponse:
        request_started = perf_counter()
        try:
            async with asyncio.timeout(config.public_request_deadline_seconds):
                return await map_request(bbox, layers)
        except TimeoutError:
            return deadline_response(config, "live_map")
        except LiveDataUnavailable as exc:
            return _live_failure_response(
                exc,
                config=config,
                request_started=request_started,
                route="live_map",
            )

    @app.get(
        "/api/v1/live/summary", response_model=LiveCurrentSummary, responses=ERROR_RESPONSES
    )
    async def live_summary() -> LiveCurrentSummary | JSONResponse:
        request_started = perf_counter()
        try:
            async with asyncio.timeout(config.public_request_deadline_seconds):
                payload = await current_live_service().map_results(
                    layers=(LiveResultKind.INCIDENT, LiveResultKind.EVACUATION)
                )
        except TimeoutError:
            return deadline_response(config, "live_summary")
        except LiveDataUnavailable as exc:
            return _live_failure_response(
                exc,
                config=config,
                request_started=request_started,
                route="live_summary",
            )
        unavailable = set(payload.unavailable_layers)
        incident_count = (
            None
            if LiveResultKind.INCIDENT in unavailable
            else sum(item.kind == LiveResultKind.INCIDENT for item in payload.results)
        )
        evacuation_count = (
            None
            if LiveResultKind.EVACUATION in unavailable
            else sum(item.kind == LiveResultKind.EVACUATION for item in payload.results)
        )
        limitation = (
            "These are returned official records, not a claim that every fire or "
            "evacuation in B.C. is shown. Unavailable layers are not zero."
        )
        if incident_count is None or evacuation_count is None:
            missing = ", ".join(layer.value for layer in payload.unavailable_layers)
            limitation = (
                f"Official {missing} records were unavailable. That is not an all-clear "
                "and is not a zero count."
            )
        return LiveCurrentSummary(
            incident_record_count=incident_count,
            evacuation_record_count=evacuation_count,
            source_status=(
                "partial"
                if unavailable
                else (
                    payload.aggregate_freshness.value
                    if payload.aggregate_freshness
                    else "returned"
                )
            ),
            retrieved_at=payload.generated_at,
            freshness=payload.aggregate_freshness,
            limitation=limitation,
        )

    @app.post(
        "/api/v1/live/nearby",
        response_model=NearMeResponse,
        responses=ERROR_RESPONSES,
    )
    async def live_nearby(payload: NearMeRequest) -> NearMeResponse | JSONResponse:
        request_started = perf_counter()
        try:
            async with asyncio.timeout(config.public_request_deadline_seconds):
                result = await current_live_service().nearby_page(
                    payload.location,
                    layers=tuple(payload.layers),
                    page=payload.page,
                    page_size=payload.page_size,
                )
            log_operation(
                trace_id=uuid4().hex,
                route="live_nearby",
                response_mode=ResponseMode.LIVE.value,
                status=ResponseStatus.ANSWER.value,
                latency_ms=(perf_counter() - request_started) * 1_000,
                live_result_count=len(result.results),
                release_version=config.release_version,
                build_commit=config.build_commit,
                deployment_environment=config.deployment_environment,
            )
            return result
        except TimeoutError:
            return deadline_response(config, "live_nearby")
        except LiveDataUnavailable as exc:
            return _live_failure_response(
                exc,
                config=config,
                request_started=request_started,
                route="live_nearby",
            )
