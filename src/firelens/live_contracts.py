"""Coarse-location and official live-data public contracts."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, HttpUrl, field_validator, model_validator

from firelens.contract_base import FrozenStrictModel
from firelens.safety_profile import (
    PublicationState,
    TruthClass,
    freshness_token,
    live_freshness_is_explicitly_fresh,
)

GEODESIC_CRS = "EPSG:4326"
COORDINATE_ORDER = "longitude_latitude"
DISTANCE_UNIT = "km"
DISTANCE_ALGORITHM = "pyproj.Geod.inv WGS84 after shapely nearest_points"
SOURCE_CLOCK_SKEW_ALLOWANCE = timedelta(minutes=5)


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
        # A small explicit set preserves genuine numeric BC community names
        # without weakening the default rejection of civic addresses.
        numeric_bc_communities = frozenset({"100 mile house"})
        digit_label_is_allowed = lowered in numeric_bc_communities
        if (
            any(character.isdigit() for character in normalized) and not digit_label_is_allowed
        ) or any(term in f" {lowered} " for term in street_terms):
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


class DerivationValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


_UNKNOWN_INPUT_FRESHNESS = "unknown"
_PLACE_INPUT_PREFIX = "place:"


def stored_input_freshness(value: Any) -> str:
    """Canonicalize observed input freshness for derivation binding."""

    return freshness_token(value) or _UNKNOWN_INPUT_FRESHNESS


def canonical_validation_status(value: Any) -> DerivationValidationStatus:
    token = str(getattr(value, "value", value)).strip().casefold()
    if token == DerivationValidationStatus.VALID.value:
        return DerivationValidationStatus.VALID
    return DerivationValidationStatus.INVALID


def derivation_cites_record_and_place(input_source_ids: Sequence[str]) -> bool:
    """Point-to-record distance needs both the official record and a place input."""

    has_place = False
    has_record = False
    for item in input_source_ids:
        if not isinstance(item, str) or not item.strip():
            continue
        if item.startswith(_PLACE_INPUT_PREFIX):
            has_place = True
        else:
            has_record = True
    return has_place and has_record


def derivation_publication_state(
    *,
    validation_status: DerivationValidationStatus | Any,
    input_freshness: Any = None,
    input_source_ids: Sequence[str] | None = None,
) -> PublicationState:
    """VERIFIED requires valid calculation, exact fresh input, and record+place ids."""

    if canonical_validation_status(validation_status) != DerivationValidationStatus.VALID:
        return PublicationState.REJECTED
    if not live_freshness_is_explicitly_fresh(input_freshness):
        return PublicationState.REVIEW
    if input_source_ids is not None and not derivation_cites_record_and_place(input_source_ids):
        return PublicationState.REVIEW
    return PublicationState.VERIFIED


def require_aware_utc(value: datetime, *, label: str = "timestamp") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def source_observation_is_future(source_updated_at: datetime, retrieved_at: datetime) -> bool:
    """True when the source clock is later than retrieval beyond allowed skew."""

    return source_updated_at > retrieved_at + SOURCE_CLOCK_SKEW_ALLOWANCE


def derivation_calculated_at_is_future(
    calculated_at: datetime, *, reference: datetime | None = None
) -> bool:
    """True when derivation time is materially later than generation/reference."""

    compared = reference or datetime.now(UTC)
    return require_aware_utc(calculated_at, label="derivation calculated_at") > (
        require_aware_utc(compared, label="derivation reference time")
        + SOURCE_CLOCK_SKEW_ALLOWANCE
    )


def freshness_for_observation(
    freshness: Freshness,
    *,
    source_updated_at: datetime,
    retrieved_at: datetime,
) -> Freshness:
    """Quarantine far-future source clocks so they cannot remain FRESH."""

    if source_observation_is_future(source_updated_at, retrieved_at):
        return Freshness.STALE
    return freshness


class DistanceDerivation(FrozenStrictModel):
    """Deterministic geodesic binding. Models cannot assign or elevate these fields."""

    truth_class: TruthClass
    publication_state: PublicationState
    input_source_ids: list[str] = Field(min_length=1, max_length=8)
    algorithm: str = Field(min_length=1, max_length=160)
    crs: str = Field(min_length=1, max_length=32)
    coordinate_order: str = Field(min_length=1, max_length=32)
    units: str = Field(min_length=1, max_length=16)
    calculated_at: datetime
    validation_status: DerivationValidationStatus
    input_freshness: str = Field(min_length=1, max_length=80)
    distance_km: float = Field(ge=0)
    distance_basis: Literal["incident_point", "perimeter_boundary"]

    @field_validator("calculated_at")
    @classmethod
    def calculated_at_is_aware(cls, value: datetime) -> datetime:
        return require_aware_utc(value, label="derivation calculated_at")

    @model_validator(mode="after")
    def derivation_is_canonical(self) -> Self:
        if self.truth_class is not TruthClass.DETERMINISTIC_DERIVATION:
            raise ValueError("distance derivation truth class must be deterministic_derivation")
        if self.crs != GEODESIC_CRS:
            raise ValueError("unsupported CRS cannot be emitted as supported")
        if self.units != DISTANCE_UNIT:
            raise ValueError("unsupported distance unit cannot be emitted as supported")
        if self.algorithm != DISTANCE_ALGORITHM:
            raise ValueError("distance algorithm must be the canonical geodesic binding")
        if self.coordinate_order != COORDINATE_ORDER:
            raise ValueError("coordinate order must be longitude_latitude")
        expected = derivation_publication_state(
            validation_status=self.validation_status,
            input_freshness=self.input_freshness,
            input_source_ids=self.input_source_ids,
        )
        if self.publication_state != expected:
            raise ValueError("distance derivation publication must match input freshness")
        if derivation_calculated_at_is_future(self.calculated_at) and (
            self.validation_status == DerivationValidationStatus.VALID
            or self.publication_state == PublicationState.VERIFIED
        ):
            raise ValueError("derivation calculated_at cannot be materially in the future")
        return self


def bind_distance_derivation(
    *,
    result_id: str,
    distance_km: float,
    distance_basis: Literal["incident_point", "perimeter_boundary"],
    calculated_at: datetime,
    extra_input_ids: tuple[str, ...] = (),
    validation_status: DerivationValidationStatus = DerivationValidationStatus.VALID,
    input_freshness: Any = None,
) -> DistanceDerivation:
    """Construct canonical derivation metadata. Callers cannot choose CRS or units."""

    stored_freshness = stored_input_freshness(input_freshness)
    status = canonical_validation_status(validation_status)
    if derivation_calculated_at_is_future(calculated_at):
        status = DerivationValidationStatus.INVALID
    input_source_ids = [result_id, *extra_input_ids]
    return DistanceDerivation(
        truth_class=TruthClass.DETERMINISTIC_DERIVATION,
        publication_state=derivation_publication_state(
            validation_status=status,
            input_freshness=stored_freshness,
            input_source_ids=input_source_ids,
        ),
        input_source_ids=input_source_ids,
        algorithm=DISTANCE_ALGORITHM,
        crs=GEODESIC_CRS,
        coordinate_order=COORDINATE_ORDER,
        units=DISTANCE_UNIT,
        calculated_at=calculated_at,
        validation_status=status,
        input_freshness=stored_freshness,
        distance_km=distance_km,
        distance_basis=distance_basis,
    )


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
    fire_of_note: bool = False
    geometry_relation: GeometryRelation = GeometryRelation.UNKNOWN
    geometry: dict[str, Any]
    distance_km: float | None = Field(default=None, ge=0)
    distance_basis: Literal["incident_point", "perimeter_boundary"] | None = None
    distance_derivation: DistanceDerivation | None = None

    @model_validator(mode="after")
    def distance_fields_are_consistent(self) -> Self:
        if (self.distance_km is None) != (self.distance_basis is None):
            raise ValueError(
                "live distance and its measurement basis must be provided together"
            )
        if (self.distance_km is None) != (self.distance_derivation is None):
            raise ValueError("live distance and derivation binding must be provided together")
        if self.distance_basis == "incident_point" and self.kind != LiveResultKind.INCIDENT:
            raise ValueError("incident-point distance requires an incident result")
        if (
            self.distance_basis == "perimeter_boundary"
            and self.kind != LiveResultKind.PERIMETER
        ):
            raise ValueError("perimeter-boundary distance requires a perimeter result")
        geom_type = self.geometry.get("type") if isinstance(self.geometry, dict) else None
        if self.distance_basis == "incident_point" and geom_type != "Point":
            raise ValueError("incident-point distance requires point geometry")
        if self.distance_basis == "perimeter_boundary" and geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError("perimeter-boundary distance requires perimeter geometry")
        if self.distance_derivation is not None:
            if (
                self.distance_derivation.distance_km != self.distance_km
                or self.distance_derivation.distance_basis != self.distance_basis
            ):
                raise ValueError("distance derivation must match the published measurement")
            if self.result_id not in self.distance_derivation.input_source_ids:
                raise ValueError("distance derivation must cite the live record as an input")
            expected = derivation_publication_state(
                validation_status=self.distance_derivation.validation_status,
                input_freshness=self.freshness,
                input_source_ids=self.distance_derivation.input_source_ids,
            )
            if self.distance_derivation.publication_state != expected:
                raise ValueError("distance derivation publication must match input freshness")
            stored = stored_input_freshness(self.distance_derivation.input_freshness)
            if stored != stored_input_freshness(self.freshness):
                raise ValueError(
                    "distance derivation input freshness must match the live record"
                )
        return self

    @field_validator("source_updated_at", "retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return require_aware_utc(value, label="live timestamps")

    @model_validator(mode="after")
    def future_source_clock_cannot_be_fresh(self) -> Self:
        if (
            source_observation_is_future(self.source_updated_at, self.retrieved_at)
            and self.freshness is Freshness.FRESH
        ):
            raise ValueError("future source observation cannot be classified fresh")
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

    @field_validator("source_updated_at", "retrieved_at")
    @classmethod
    def layer_timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware_utc(value, label="live layer timestamps")

    @model_validator(mode="after")
    def availability_fields_are_consistent(self) -> Self:
        observations = (self.source_updated_at, self.retrieved_at, self.freshness)
        if self.available and any(value is None for value in observations):
            raise ValueError("available live layers require source-level freshness metadata")
        if not self.available and (
            any(value is not None for value in observations) or self.matching_result_count != 0
        ):
            raise ValueError("unavailable live layers cannot claim observations or results")
        if (
            self.available
            and self.source_updated_at is not None
            and self.retrieved_at is not None
            and source_observation_is_future(self.source_updated_at, self.retrieved_at)
            and self.freshness is Freshness.FRESH
        ):
            raise ValueError("future source observation cannot be classified fresh")
        return self


def stale_observation_limitations(
    layer_statuses: list[LiveLayerStatus],
    results: list[LiveResult],
) -> list[str]:
    """Distinguish cache-stale refresh failure from quarantined future source clocks."""

    refresh_stale = False
    clock_quarantine = False
    for status in layer_statuses:
        if not status.available:
            continue
        future = (
            status.source_updated_at is not None
            and status.retrieved_at is not None
            and source_observation_is_future(status.source_updated_at, status.retrieved_at)
        )
        if future:
            clock_quarantine = True
        elif status.freshness is Freshness.STALE:
            refresh_stale = True
    for result in results:
        if source_observation_is_future(result.source_updated_at, result.retrieved_at):
            clock_quarantine = True
        elif result.freshness is Freshness.STALE:
            refresh_stale = True
    notes: list[str] = []
    if refresh_stale:
        notes.append(
            "A refresh failed; cached records are stale and are not current conditions."
        )
    if clock_quarantine:
        notes.append(
            "An official source timestamp was later than retrieval and is not treated as current."
        )
    return notes


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

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_aware(cls, value: datetime) -> datetime:
        return require_aware_utc(value, label="map generated_at")

    @model_validator(mode="after")
    def validate_aggregate_freshness(self) -> Self:
        expected = aggregate_live_freshness(self.results)
        if self.aggregate_freshness != expected:
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

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_aware(cls, value: datetime) -> datetime:
        return require_aware_utc(value, label="near-me generated_at")

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
        if self.aggregate_freshness != aggregate_live_freshness(self.results):
            raise ValueError("aggregate freshness must match the returned live records")
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


class LiveCurrentSummary(FrozenStrictModel):
    """Zero-generation current-state summary. Unavailable layers stay null."""

    incident_record_count: int | None = Field(default=None, ge=0)
    evacuation_record_count: int | None = Field(default=None, ge=0)
    source_status: str = Field(min_length=1, max_length=80)
    retrieved_at: datetime | None = None
    freshness: AggregateFreshness | None = None
    limitation: str = Field(min_length=1, max_length=300)
