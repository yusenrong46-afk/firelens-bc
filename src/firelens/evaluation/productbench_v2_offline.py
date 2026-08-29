"""Deterministic official-record double for ProductBench's offline tier."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import HttpUrl

from firelens.contracts import (
    CoarseResolvedLocation,
    Freshness,
    GeometryRelation,
    LiveMapResponse,
    LivePagination,
    LiveResult,
    LiveResultKind,
    MapViewport,
    NearMeResponse,
    aggregate_live_freshness,
)
from firelens.live import LAYER_URLS
from firelens.live_contracts import LocationInput
from firelens.live_support import OFFICIAL_FALLBACK_URLS


class OfflineProductBenchLiveDataService:
    """Network-free official-record fixture used only by ProductBench offline mode."""

    _NOW = datetime(2026, 1, 1, tzinfo=UTC)

    async def aclose(self) -> None:
        return None

    async def map_results(
        self,
        *,
        layers: tuple[LiveResultKind, ...],
        bbox: tuple[float, float, float, float] | None = None,
    ) -> LiveMapResponse:
        del bbox
        results = [
            LiveResult(
                result_id=f"{kind.value}:productbench-offline-record",
                kind=kind,
                authority=(
                    "EmergencyInfoBC and issuing local authority"
                    if kind == LiveResultKind.EVACUATION
                    else "BC Wildfire Service"
                ),
                source_url=HttpUrl(LAYER_URLS[kind]),
                source_updated_at=self._NOW,
                retrieved_at=self._NOW,
                freshness=Freshness.FRESH,
                status="Controlled offline official record",
                name="ProductBench offline fixture",
                geometry_relation=GeometryRelation.UNKNOWN,
                geometry={"type": "Point", "coordinates": [-119.5, 50.0]},
            )
            for kind in layers
        ]
        return LiveMapResponse(
            generated_at=self._NOW,
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def nearby_results(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...] = tuple(LiveResultKind),
    ) -> LiveMapResponse:
        del location
        response = await self.map_results(layers=layers)
        return response.model_copy(
            update={
                "results": [
                    result.model_copy(update={"geometry_relation": GeometryRelation.NEARBY})
                    for result in response.results
                ]
            }
        )

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        del location
        return 49.88, -119.49

    async def nearby_page(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...] = tuple(LiveResultKind),
        page: int = 1,
        page_size: int = 100,
    ) -> NearMeResponse:
        mapped = await self.nearby_results(location, layers=layers)
        total = len(mapped.results)
        return NearMeResponse(
            generated_at=self._NOW,
            requested_radius_km=location.radius_km,
            requested_layers=list(layers) or list(LiveResultKind),
            resolved_location=CoarseResolvedLocation(latitude=49.88, longitude=-119.49),
            viewport=MapViewport(west=-120.0, south=49.0, east=-119.0, north=50.5),
            results=mapped.results,
            pagination=LivePagination(
                page=page,
                page_size=page_size,
                total_results=total,
                total_pages=1 if total else 0,
                returned_results=total,
                has_previous=False,
                has_next=False,
            ),
            aggregate_freshness=mapped.aggregate_freshness,
            unavailable_layers=list(mapped.unavailable_layers),
            layer_statuses=list(mapped.layer_statuses),
            limitations=list(mapped.limitations),
            official_fallback_urls=list(OFFICIAL_FALLBACK_URLS),
        )
