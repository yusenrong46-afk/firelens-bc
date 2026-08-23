"""Zero-cost structural sentinels for selected V1.6 user-end questions.

These fixtures deliberately use local packets, the deterministic FakeProvider,
and app-owned live stubs.  They verify public routing and authority boundaries,
not the semantic quality of generated prose.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.agent import AgentTool, FireLensAgent
from firelens.answering.context import build_evidence_packet
from firelens.answering.grounded import GroundedAnswerEngine
from firelens.contracts import (
    CoarseResolvedLocation,
    Freshness,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapContext,
    QueryRequest,
    ResponseMode,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.providers.fake import FakeProvider
from firelens.publication.compiler import compile_structured_claim
from firelens.retrieval.vector import retrieval_hit_from_chunk

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/evaluation/v1_6_user_end_questions_50.json"
TARGET_IDS = frozenset(
    {
        "UQ-E04",
        "UQ-E06",
        "UQ-E12",
        "UQ-M01",
        "UQ-M04",
        "UQ-M10",
        "UQ-M11",
        "UQ-H01",
        "UQ-H12",
        "UQ-VH01",
        "UQ-VH06",
        "UQ-VH11",
    }
)


def _catalog_cases() -> dict[str, dict[str, object]]:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {str(case["id"]): case for case in payload["cases"]}


def _question(case_id: str) -> str:
    question = _catalog_cases()[case_id]["question"]
    assert isinstance(question, str)
    return question


def _publication_kinds(response: Any) -> set[str]:
    kinds: set[str] = set()
    for claim in response.claims:
        publication = getattr(claim, "publication", None)
        kind = getattr(publication, "kind", None)
        if kind is not None:
            kinds.add(getattr(kind, "value", str(kind)))
    return kinds


def _provider_calls(provider: FakeProvider) -> tuple[int, int, int, int]:
    return (
        provider.plan_calls,
        provider.embed_calls,
        provider.rerank_calls,
        provider.generate_calls,
    )


def _fire() -> LiveResult:
    stamp = datetime(2026, 8, 20, tzinfo=UTC)
    return LiveResult(
        result_id="incident:kelowna-fixture",
        kind=LiveResultKind.INCIDENT,
        source_url="https://example.test/live/kelowna-fixture",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name="Kelowna Fixture Fire",
        geometry={"type": "Point", "coordinates": [-119.49, 49.88]},
    )


class _FixtureLiveService:
    def __init__(self, results: list[LiveResult]) -> None:
        self.results = results
        self.nearby_calls = 0
        self.map_calls = 0
        self.resolve_calls = 0

    async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.nearby_calls += 1
        return type(
            "NearbyFixture",
            (),
            {
                "results": self.results,
                "limitations": ["No matching official records were returned."]
                if not self.results
                else [],
                "unavailable_layers": [],
                "resolved_location": CoarseResolvedLocation(latitude=49.88, longitude=-119.49),
                "pagination": type("Pagination", (), {"total_results": len(self.results)})(),
            },
        )()

    async def map_results(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.map_calls += 1
        raise AssertionError("this fixture should use the coarse-location live path")

    async def resolve_location(self, *args: Any, **kwargs: Any) -> tuple[float, float]:
        del args, kwargs
        self.resolve_calls += 1
        return 49.88, -119.49


class _UnexpectedStatic:
    """Static facade with a provider counter for provider-free boundaries."""

    def __init__(self) -> None:
        self.provider = FakeProvider()

    async def ask(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("this boundary must not call static RAG")


class _StructuredKitStatic:
    async def ask(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return compile_structured_claim(
            typed_claim_id="TC-FIRESMART-021-01", public_claim_id="C1"
        ).response


def test_selected_catalog_cases_remain_the_twelve_explicit_structural_fixtures() -> None:
    cases = _catalog_cases()

    assert TARGET_IDS <= cases.keys()
    assert len(cases) == 50
    assert cases["UQ-M04"]["location_expectation"] == "required"
    assert cases["UQ-M01"]["expected_modes"] == ["mixed", "partial"]
    assert cases["UQ-VH06"]["forbidden_behaviors"] == [
        "confirm_safety_from_empty_results",
        "hide_unavailable_layer",
    ]


def test_static_packet_fixtures_preserve_quote_only_conditions_and_supported_bounds(
    tmp_path: Path,
) -> None:
    cases = {
        "UQ-E04": (
            "An evacuation alert means be ready to leave. An evacuation order means you "
            "are at risk and must leave immediately.",
            ("alert", "order"),
        ),
        "UQ-E06": (
            "Reduce wildfire smoke exposure by keeping windows and doors closed when "
            "appropriate. Seek medical advice for symptoms that concern you.",
            ("smoke", "closed"),
        ),
        "UQ-M10": (
            "Before leaving during an evacuation order, follow the directions of the "
            "issuing authority and take your emergency kit.",
            ("before leaving", "issuing authority"),
        ),
        "UQ-M11": (
            "Do not shut off natural gas for an evacuation order unless you smell gas "
            "or the gas authority directs you to do so. If you smell gas, leave "
            "immediately and call the emergency gas number.",
            ("unless", "smell gas"),
        ),
        "UQ-H12": (
            "If you smell gas, leave immediately and call the emergency gas number. Do "
            "not shut off natural gas for an evacuation order unless the gas authority "
            "directs you to do so.",
            ("smell gas", "leave immediately"),
        ),
        "UQ-VH11": (
            "Store at least four litres of water per person per day for emergency "
            "planning. Household needs can vary, so this is not a universal prescription.",
            ("four litres", "household needs can vary"),
        ),
    }

    async def run() -> None:
        for case_id, (source_text, required_text) in cases.items():
            chunk = make_chunk(case_id.lower(), source_text)
            config = write_test_corpus(tmp_path / case_id, [chunk])
            packet = build_evidence_packet(
                _question(case_id),
                [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
                [chunk],
                corpus_version="v1-6-e2e-fixture.v1",
                config=config,
            )
            response = (
                await GroundedAnswerEngine(FakeProvider()).answer(
                    _question(case_id), packet, trace_id=f"fixture-{case_id}"
                )
            ).response
            answer = (response.answer or "").casefold()
            assert response.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
            assert all(fragment in answer for fragment in required_text)
            assert "prescrib" not in answer
            if case_id in {"UQ-M11", "UQ-H12", "UQ-VH11"}:
                assert response.response_mode == ResponseMode.PARTIAL
                assert "official_quote_only" in _publication_kinds(response)

    asyncio.run(run())


def test_agent_fixtures_keep_mixed_authority_separate_and_require_coarse_location() -> None:
    async def run() -> None:
        mixed_live = _FixtureLiveService([_fire()])
        mixed = await FireLensAgent(
            cast(Any, _StructuredKitStatic()),
            LiveAnswerCoordinator(cast(Any, mixed_live)),
        ).answer(QueryRequest(question=_question("UQ-M01")))
        response = mixed.response
        assert response.response_mode == ResponseMode.MIXED
        assert response.live_results
        assert response.claims
        assert "structured_reviewed" in _publication_kinds(response)
        assert {section.kind.value for section in response.answer_sections} >= {
            "current_records",
            "reviewed_guidance",
        }
        assert AgentTool.LIST_OFFICIAL_FIRES in mixed.tools
        assert AgentTool.SEARCH_REVIEWED_GUIDANCE in mixed.tools

        location_static = _UnexpectedStatic()
        location_live = _FixtureLiveService([_fire()])
        location = await FireLensAgent(
            cast(Any, location_static),
            LiveAnswerCoordinator(cast(Any, location_live)),
        ).answer(
            QueryRequest(
                question=_question("UQ-M04"),
                context=MapContext(selected_live_result_id="incident:kelowna-fixture"),
            )
        )
        assert location.response.response_mode == ResponseMode.REQUIRES_INPUT
        assert location.response.required_input is not None
        assert location.response.required_input.kind.value == "location"
        assert location.response.selected_live_result_id == "incident:kelowna-fixture"
        assert _provider_calls(location_static.provider) == (0, 0, 0, 0)
        assert (
            location_live.nearby_calls,
            location_live.map_calls,
            location_live.resolve_calls,
        ) == (
            0,
            0,
            0,
        )

    asyncio.run(run())


def test_safety_and_empty_map_fixtures_do_not_make_a_personal_safety_claim() -> None:
    async def run() -> None:
        for case_id in ("UQ-H01", "UQ-VH01"):
            static = _UnexpectedStatic()
            live = _FixtureLiveService([])
            execution = await FireLensAgent(
                cast(Any, static), LiveAnswerCoordinator(cast(Any, live))
            ).answer(QueryRequest(question=_question(case_id)))
            assert execution.response.response_mode == ResponseMode.ABSTENTION
            assert _provider_calls(static.provider) == (0, 0, 0, 0)
            assert (live.nearby_calls, live.map_calls, live.resolve_calls) == (0, 0, 0)
            assert "is safe" not in (execution.response.answer or "").casefold()

        # UQ-VH06 must not turn a zero-result live packet into an all-clear.  This
        # intentionally exercises the public agent path with the catalog question
        # and an explicit coarse opt-in, rather than treating a missing map record
        # as evidence that an area is safe.
        empty_live = _FixtureLiveService([])
        empty = await FireLensAgent(
            cast(Any, _UnexpectedStatic()),
            LiveAnswerCoordinator(cast(Any, empty_live)),
        ).answer(
            QueryRequest(
                question=_question("UQ-VH06"),
                location=LocationInput(label="Kelowna"),
            )
        )
        empty_text = " ".join(
            [empty.response.answer or "", *empty.response.limitations]
        ).casefold()
        assert empty.response.response_mode in {
            ResponseMode.LIVE,
            ResponseMode.PARTIAL,
            ResponseMode.SCOPE_REDIRECT,
            ResponseMode.ABSTENTION,
        }
        assert "not a safety determination" in empty_text or "not an all-clear" in empty_text

    asyncio.run(run())


def test_trust_explanation_uses_only_the_catalogued_capability_or_grounded_lane(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        runtime, provider, _ = await make_runtime(
            tmp_path,
            chunks=[
                make_chunk(
                    "trust-boundary",
                    "FireLens separates current official records, reviewed preparedness "
                    "guidance, and ordinary background. Automated checks do not replace "
                    "human review.",
                )
            ],
        )
        try:
            response = await runtime.service.ask(QueryRequest(question=_question("UQ-E12")))
        finally:
            await runtime.aclose()

        assert response.response_mode in {ResponseMode.CAPABILITY, ResponseMode.GROUNDED}
        assert response.response_mode != ResponseMode.BACKGROUND
        assert provider.generate_calls <= 1

    asyncio.run(run())
