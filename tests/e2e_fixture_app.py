"""Deterministic real-stack app for the built-frontend Playwright lane.

This module deliberately uses the production FastAPI composition root, public
agent, response contracts, serializer, and checked-in typed claim inventory.
Only upstream live-data I/O and static retrieval are replaced with bounded
fixtures. No provider, credential, or external network is used.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    AskResponse,
    CoarseResolvedLocation,
    EvidenceStatus,
    Freshness,
    LiveLayerStatus,
    LiveMapResponse,
    LivePagination,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapViewport,
    NearMeResponse,
    PublicClaim,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
)
from firelens.publication.compiler import compile_structured_claim
from firelens.publication.fallback import background_authority
from firelens.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 8, 24, 15, 2, tzinfo=UTC)
OFFICIAL_MAP = "https://wildfiresituation.nrs.gov.bc.ca/map"


def _incident(
    result_id: str,
    name: str,
    status: str,
    longitude: float,
    latitude: float,
    *,
    fire_centre: str,
) -> LiveResult:
    return LiveResult(
        result_id=result_id,
        kind=LiveResultKind.INCIDENT,
        source_url=f"https://example.test/official/{result_id}",
        source_updated_at=STAMP,
        retrieved_at=RETRIEVED,
        freshness=Freshness.FRESH,
        status=status,
        name=name,
        fire_centre=fire_centre,
        geometry={"type": "Point", "coordinates": [longitude, latitude]},
    )


MOUNTAIN_FIRE = _incident(
    "incident:mountain",
    "Mountain Fire",
    "Out of Control",
    -119.43,
    49.91,
    fire_centre="Kamloops Fire Centre",
)
BEAR_CREEK_FIRE = _incident(
    "incident:bear-creek",
    "Bear Creek Fire",
    "Being Held",
    -119.55,
    49.97,
    fire_centre="Kamloops Fire Centre",
)
SOUTH_OKANAGAN_FIRE = _incident(
    "incident:south-okanagan",
    "South Okanagan Fire",
    "Under Control",
    -119.57,
    49.49,
    fire_centre="Kamloops Fire Centre",
)
KOOTENAY_FIRE = _incident(
    "incident:kootenay",
    "Kootenay Fixture Fire",
    "Out of Control",
    -117.28,
    49.51,
    fire_centre="Southeast Fire Centre",
)
EVACUATION_RECORD = LiveResult(
    result_id="evacuation:kelowna-fixture",
    kind=LiveResultKind.EVACUATION,
    authority="Central Okanagan Emergency Operations",
    source_url="https://example.test/official/evacuation-kelowna",
    source_updated_at=STAMP,
    retrieved_at=RETRIEVED,
    freshness=Freshness.FRESH,
    status="Evacuation Alert",
    name="Kelowna fixture alert",
    issuer="Central Okanagan Emergency Operations",
    geometry={"type": "Point", "coordinates": [-119.47, 49.9]},
)


def _status(kind: LiveResultKind, *, available: bool, count: int) -> LiveLayerStatus:
    return LiveLayerStatus(
        kind=kind,
        authority=(
            "Central Okanagan Emergency Operations"
            if kind == LiveResultKind.EVACUATION
            else "BC Wildfire Service"
        ),
        source_url=f"https://example.test/layers/{kind.value}",
        available=available,
        source_updated_at=STAMP if available else None,
        retrieved_at=RETRIEVED if available else None,
        freshness=Freshness.FRESH if available else None,
        matching_result_count=count,
    )


class DeterministicLiveService:
    """Application-owned fixture with no HTTP client and no network path."""

    async def aclose(self) -> None:
        return None

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        label = (location.label or "").casefold()
        if "okanagan" in label:
            return 49.88, -119.49
        if "kelowna" in label:
            return 49.89, -119.5
        if "emptytown" in label:
            return 50.0, -120.0
        if "outage ridge" in label:
            return 49.75, -119.7
        # The grammar, not a hidden fixture place list, decides whether a label
        # reaches this adapter. Unknown labels remain unresolved and fetch none.
        from firelens.live import LiveDataErrorKind, LiveDataUnavailable

        raise LiveDataUnavailable(
            "fixture location was not resolved",
            kind=LiveDataErrorKind.NOT_FOUND,
        )

    @staticmethod
    def _records(label: str, layers: tuple[LiveResultKind, ...]) -> list[LiveResult]:
        lowered = label.casefold()
        candidates: list[LiveResult]
        if "emptytown" in lowered:
            candidates = []
        elif "okanagan" in lowered:
            candidates = [MOUNTAIN_FIRE, BEAR_CREEK_FIRE, SOUTH_OKANAGAN_FIRE]
        elif "outage ridge" in lowered:
            candidates = [MOUNTAIN_FIRE, BEAR_CREEK_FIRE]
        else:
            candidates = [MOUNTAIN_FIRE, BEAR_CREEK_FIRE, EVACUATION_RECORD]
        return [item for item in candidates if item.kind in layers]

    async def map_results(
        self,
        *,
        layers: tuple[LiveResultKind, ...],
        bbox: tuple[float, float, float, float] | None = None,
    ) -> LiveMapResponse:
        del bbox
        all_records = [
            MOUNTAIN_FIRE,
            BEAR_CREEK_FIRE,
            SOUTH_OKANAGAN_FIRE,
            KOOTENAY_FIRE,
            EVACUATION_RECORD,
        ]
        results = [item for item in all_records if item.kind in layers]
        counts = {kind: sum(item.kind == kind for item in results) for kind in layers}
        return LiveMapResponse(
            generated_at=RETRIEVED,
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
            layer_statuses=[
                _status(kind, available=True, count=counts[kind]) for kind in layers
            ],
            limitations=["No matching record is not a safety determination."],
        )

    async def nearby_page(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...],
        page: int = 1,
        page_size: int = 100,
    ) -> NearMeResponse:
        label = location.label or ""
        latitude, longitude = await self.resolve_location(location)
        unavailable = (
            [LiveResultKind.EVACUATION]
            if "outage ridge" in label.casefold() and LiveResultKind.EVACUATION in layers
            else []
        )
        available_layers = tuple(kind for kind in layers if kind not in unavailable)
        full_results = self._records(label, available_layers)
        start = (page - 1) * page_size
        results = full_results[start : start + page_size]
        total_pages = math.ceil(len(full_results) / page_size)
        counts = {
            kind: sum(item.kind == kind for item in full_results) for kind in available_layers
        }
        statuses = [
            _status(
                kind,
                available=kind not in unavailable,
                count=counts.get(kind, 0),
            )
            for kind in layers
        ]
        limitations = ["No matching record is not a safety determination."]
        if unavailable:
            limitations.append(
                "The evacuation layer is unavailable; the incident result remains available."
            )
        return NearMeResponse(
            generated_at=RETRIEVED,
            requested_radius_km=location.radius_km,
            requested_layers=list(layers),
            resolved_location=CoarseResolvedLocation(
                latitude=latitude,
                longitude=longitude,
            ),
            viewport=MapViewport(
                west=longitude - 0.7,
                south=latitude - 0.5,
                east=longitude + 0.7,
                north=latitude + 0.5,
            ),
            results=results,
            pagination=LivePagination(
                page=page,
                page_size=page_size,
                total_results=len(full_results),
                total_pages=total_pages,
                returned_results=len(results),
                has_previous=page > 1,
                has_next=page < total_pages,
            ),
            aggregate_freshness=aggregate_live_freshness(results),
            unavailable_layers=unavailable,
            layer_statuses=statuses,
            limitations=limitations,
            official_fallback_urls=[OFFICIAL_MAP],
        )


class DeterministicStaticService:
    """Return question-bound fixture answers; never invoke a model provider."""

    def __init__(self) -> None:
        evacuation = compile_structured_claim(
            typed_claim_id="TC-EVAC-ALERT-001",
            public_claim_id="C1",
            root=str(ROOT),
        ).response
        smoke = compile_structured_claim(
            typed_claim_id="TC-SMOKE-014-01",
            public_claim_id="C1",
            root=str(ROOT),
        ).response
        assert evacuation is not None
        assert smoke is not None
        self.evacuation = evacuation
        self.smoke = smoke

    @staticmethod
    def _background(question: str) -> AskResponse:
        claim = PublicClaim(
            claim_id="C1",
            text=(
                "This deterministic test fixture returns a general-background "
                "example, not reviewed FireLens guidance."
            ),
            evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            publication=background_authority(),
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=sha256(question.encode()).hexdigest()[:32],
            response_mode=ResponseMode.BACKGROUND,
            answer=claim.text,
            claims=[claim],
            limitations=[BACKGROUND_LIMITATION],
        )

    async def ask(
        self,
        request: QueryRequest,
        *,
        allow_live: bool = True,
        prefer_reviewed_quotes: bool = False,
    ) -> Any:
        del allow_live, prefer_reviewed_quotes
        question = request.question.casefold()
        if "malformed publication fixture" not in question:
            if "evacuation alert" in question:
                return self.evacuation
            if "wildfire smoke" in question:
                return self.smoke
            # The production service may publish validated and visibly labelled
            # background for an ordinary non-live question. The fixture models
            # that lane without pretending every question matched the one
            # reviewed evacuation claim it happens to compile.
            return self._background(request.question)

        # A deliberate test-only defect: all outer fields are shaped like an
        # AskResponse, but the nested public claim lacks PublicationAuthority.
        # Returning a plain attribute object forces FastAPI response-model
        # validation to exercise the wire boundary instead of trusting a model
        # instance built inside the fixture.
        fields = {
            name: getattr(self.evacuation, name) for name in type(self.evacuation).model_fields
        }
        fields["claims"] = [
            self.evacuation.claims[0].model_dump(mode="python", exclude={"publication"})
        ]
        fields["proof_cards"] = []
        return SimpleNamespace(**fields)


config = FireLensConfig.from_env(ROOT).model_copy(
    update={
        "openrouter_api_key": None,
        "deployment_environment": "local",
        "debug": False,
        "trace_content": False,
        "frontend_dist_path": ROOT / "apps/web/dist/client",
        "trace_dir": Path("/tmp/firelens-real-stack-traces"),
    }
)
runtime = Runtime(
    config=config,
    corpus_version="firelens.real-stack-fixture.v1",
    service=DeterministicStaticService(),  # type: ignore[arg-type]
    provider_configured=True,
    provider=None,
    candidate_binding_applied=True,
)
live_service = DeterministicLiveService()
app = create_app(
    config,
    runtime=runtime,
    live_service=live_service,  # type: ignore[arg-type]
)
