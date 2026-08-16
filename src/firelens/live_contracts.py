"""Coarse-location and official live-data public contracts."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, HttpUrl, field_validator, model_validator

from firelens.contract_base import FrozenStrictModel


class LocationInput(FrozenStrictModel):
    """Coarse, opt-in location used only for the current live-data request."""

    label: str | None = Field(default=None, min_length=2, max_length=120)
    latitude: float | None = Field(default=None, ge=48.0, le=61.0)
    longitude: float | None = Field(default=None, ge=-140.0, le=-113.0)
    radius_km: float = Field(default=50.0, ge=1.0, le=200.0)

    @field_validator("label")
    @classmethod
    def reject_exact_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        lowered = normalized.casefold()
        street_terms = (
            " street",
            " st ",
            " avenue",
            " ave ",
            " road",
            " rd ",
            " boulevard",
        )
        if any(character.isdigit() for character in normalized) or any(
            term in f" {lowered} " for term in street_terms
        ):
            raise ValueError("use a community or place label, not an exact address")
        return normalized

    @field_validator("latitude", "longitude")
    @classmethod
    def round_coordinates(cls, value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @model_validator(mode="after")
    def require_one_location_form(self) -> Self:
        has_label = self.label is not None
        has_coordinates = self.latitude is not None or self.longitude is not None
        if has_label == has_coordinates:
            raise ValueError("provide either a place label or coordinates")
        if has_coordinates and (self.latitude is None or self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class LiveResultKind(StrEnum):
    INCIDENT = "incident"
    PERIMETER = "perimeter"
    EVACUATION = "evacuation"


class GeometryRelation(StrEnum):
    INSIDE = "inside"
    NEARBY = "nearby"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class AggregateFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    MIXED = "mixed"


class LiveResult(FrozenStrictModel):
    result_id: str = Field(min_length=1, max_length=200)
    kind: LiveResultKind
    authority: str = "BC Wildfire Service"
    source_url: HttpUrl
    source_updated_at: datetime
    retrieved_at: datetime
    freshness: Freshness
    status: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=300)
    incident_number: str | None = Field(default=None, max_length=100)
    size_hectares: float | None = Field(default=None, ge=0)
    fire_centre: str | None = Field(default=None, max_length=200)
    fire_zone: str | None = Field(default=None, max_length=200)
    issuer: str | None = Field(default=None, max_length=300)
    geometry_relation: GeometryRelation = GeometryRelation.UNKNOWN
    geometry: dict[str, Any]
    distance_km: float | None = Field(default=None, ge=0)
    distance_basis: Literal["incident_point", "perimeter_boundary"] | None = None

    @model_validator(mode="after")
    def distance_fields_are_consistent(self) -> Self:
        if (self.distance_km is None) != (self.distance_basis is None):
            raise ValueError(
                "live distance and its measurement basis must be provided together"
            )
        if self.distance_basis == "incident_point" and self.kind != LiveResultKind.INCIDENT:
            raise ValueError("incident-point distance requires an incident result")
        if (
            self.distance_basis == "perimeter_boundary"
            and self.kind != LiveResultKind.PERIMETER
        ):
            raise ValueError("perimeter-boundary distance requires a perimeter result")
        return self


class LiveLayerStatus(FrozenStrictModel):
    """Source-level freshness and availability, including zero-result layers."""

    kind: LiveResultKind
    authority: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    available: bool
    source_updated_at: datetime | None = None
    retrieved_at: datetime | None = None
    freshness: Freshness | None = None
    matching_result_count: int = Field(ge=0)

    @model_validator(mode="after")
    def availability_fields_are_consistent(self) -> Self:
        observations = (self.source_updated_at, self.retrieved_at, self.freshness)
        if self.available and any(value is None for value in observations):
            raise ValueError("available live layers require source-level freshness metadata")
        if not self.available and (
            any(value is not None for value in observations) or self.matching_result_count != 0
        ):
            raise ValueError("unavailable live layers cannot claim observations or results")
        return self


def aggregate_live_freshness(results: list[LiveResult]) -> AggregateFreshness | None:
    freshnesses = {item.freshness for item in results}
    if not freshnesses:
        return None
    if freshnesses == {Freshness.FRESH}:
        return AggregateFreshness.FRESH
    if freshnesses == {Freshness.STALE}:
        return AggregateFreshness.STALE
    return AggregateFreshness.MIXED


class LiveMapResponse(FrozenStrictModel):
    generated_at: datetime
    results: list[LiveResult]
    aggregate_freshness: AggregateFreshness | None = None
    unavailable_layers: list[LiveResultKind] = Field(default_factory=list)
    layer_statuses: list[LiveLayerStatus] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aggregate_freshness(self) -> Self:
        expected = aggregate_live_freshness(self.results)
        if self.aggregate_freshness is not None and self.aggregate_freshness != expected:
            raise ValueError("aggregate freshness must match the returned live records")
        if self.layer_statuses:
            kinds = [status.kind for status in self.layer_statuses]
            if len(kinds) != len(set(kinds)):
                raise ValueError("live layer statuses must be unique")
            unavailable = [
                status.kind for status in self.layer_statuses if not status.available
            ]
            if unavailable != self.unavailable_layers:
                raise ValueError("live unavailable layers must match layer statuses")
            result_counts = Counter(result.kind for result in self.results)
            if any(
                status.matching_result_count != result_counts[status.kind]
                for status in self.layer_statuses
            ):
                raise ValueError("live layer result counts must match returned records")
        return self


class MapViewport(FrozenStrictModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def ordered_bounds(self) -> Self:
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("map viewport coordinates must be ordered")
        return self


class CoarseResolvedLocation(FrozenStrictModel):
    latitude: float = Field(ge=48.0, le=61.0)
    longitude: float = Field(ge=-140.0, le=-113.0)

    @field_validator("latitude", "longitude")
    @classmethod
    def remain_coarse(cls, value: float) -> float:
        rounded = round(value, 2)
        if value != rounded:
            raise ValueError("resolved locations must remain rounded to two decimals")
        return rounded


class LivePagination(FrozenStrictModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total_results: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    returned_results: int = Field(ge=0, le=200)
    has_previous: bool
    has_next: bool

    @model_validator(mode="after")
    def derived_fields_are_consistent(self) -> Self:
        expected_pages = math.ceil(self.total_results / self.page_size)
        if self.total_pages != expected_pages:
            raise ValueError("live pagination total_pages must be derived from total_results")
        if self.returned_results > self.page_size:
            raise ValueError("live pagination cannot return more than page_size")
        if self.has_previous != (self.page > 1):
            raise ValueError("live pagination has_previous is inconsistent")
        if self.has_next != (self.page < self.total_pages):
            raise ValueError("live pagination has_next is inconsistent")
        return self


class NearMeRequest(FrozenStrictModel):
    location: LocationInput
    layers: list[LiveResultKind] = Field(
        default_factory=lambda: list(LiveResultKind), max_length=3
    )
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=100, ge=1, le=200)

    @field_validator("layers")
    @classmethod
    def require_unique_layers(cls, value: list[LiveResultKind]) -> list[LiveResultKind]:
        if not value:
            raise ValueError("near-me requires at least one official layer")
        if len(value) != len(set(value)):
            raise ValueError("near-me layers must be unique")
        return value


class NearMeResponse(FrozenStrictModel):
    generated_at: datetime
    requested_radius_km: float = Field(ge=1.0, le=200.0)
    requested_layers: list[LiveResultKind] = Field(min_length=1, max_length=3)
    resolved_location: CoarseResolvedLocation
    viewport: MapViewport
    results: list[LiveResult] = Field(max_length=200)
    pagination: LivePagination
    aggregate_freshness: AggregateFreshness | None = None
    unavailable_layers: list[LiveResultKind] = Field(default_factory=list)
    layer_statuses: list[LiveLayerStatus] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)
    official_fallback_urls: list[HttpUrl] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def page_contract_is_consistent(self) -> Self:
        if len(self.results) != self.pagination.returned_results:
            raise ValueError("near-me result count must match pagination")
        if len(self.requested_layers) != len(set(self.requested_layers)):
            raise ValueError("near-me requested layers must be unique")
        if len(self.unavailable_layers) != len(set(self.unavailable_layers)):
            raise ValueError("near-me unavailable layers must be unique")
        if any(layer not in self.requested_layers for layer in self.unavailable_layers):
            raise ValueError("near-me unavailable layers must have been requested")
        if self.layer_statuses:
            status_kinds = [status.kind for status in self.layer_statuses]
            if status_kinds != self.requested_layers:
                raise ValueError("near-me layer statuses must match requested layer order")
            if [
                status.kind for status in self.layer_statuses if not status.available
            ] != self.unavailable_layers:
                raise ValueError("near-me unavailable layers must match layer statuses")
            if (
                sum(status.matching_result_count for status in self.layer_statuses)
                != self.pagination.total_results
            ):
                raise ValueError("near-me layer counts must match the full result roster")
        return self
