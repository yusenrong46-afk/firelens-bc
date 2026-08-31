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

from rag_helpers import make_chunk, make_runtime

from firelens.agent import AgentTool, FireLensAgent
from firelens.answering.context import build_evidence_packet
from firelens.answering.grounded import GroundedAnswerEngine
from firelens.config import FireLensConfig
from firelens.contracts import (
    CoarseResolvedLocation,
    ConversationTurn,
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
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.vector import retrieval_hit_from_chunk
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/evaluation/v1_6_user_end_questions_50.json"
TARGET_IDS = frozenset(
    {
        "UQ-E03",
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


class _FixtureProvinceLiveService(_FixtureLiveService):
    """Live fixture that also supports the deliberate BC-wide roster lane."""

    async def map_results(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.map_calls += 1
        return type(
            "MapFixture",
            (),
            {
                "results": self.results,
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": None,
                "pagination": type("Pagination", (), {"total_results": len(self.results)})(),
            },
        )()


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


def test_selected_catalog_cases_remain_the_thirteen_explicit_structural_fixtures() -> None:
    cases = _catalog_cases()

    assert TARGET_IDS <= cases.keys()
    assert len(cases) == 50
    assert cases["UQ-M04"]["location_expectation"] == "required"
    assert cases["UQ-M01"]["expected_modes"] == ["mixed", "partial"]
    assert cases["UQ-VH06"]["forbidden_behaviors"] == [
        "confirm_safety_from_empty_results",
        "hide_unavailable_layer",
    ]


def test_uq_e03_returns_reviewed_build_claim_plus_first_exact_contents_checklist() -> None:
    question = _question("UQ-E03")
    chunks = load_chunk_records(ROOT / "data/processed/firelens_static_corpus.chunks.jsonl")
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    retrieval_order = (
        "preparedbc_wildfire_guide:page:4:chunk:3",
        "preparedbc_wildfire_guide:page:5:chunk:1",
        "preparedbc_wildfire_guide:page:6:chunk:1",
        "preparedbc_wildfire_guide:page:6:chunk:2",
        "preparedbc_wildfire_guide:page:6:chunk:3",
    )
    hits = [
        retrieval_hit_from_chunk(by_id[chunk_id], rerank_rank=rank)
        for rank, chunk_id in enumerate(retrieval_order, start=1)
    ]
    packet = build_evidence_packet(
        question,
        hits,
        chunks,
        corpus_version="v1-6-uq-e03-fixture.v1",
        config=FireLensConfig.from_env(ROOT),
    )
    provider = FakeProvider()

    outcome = asyncio.run(
        GroundedAnswerEngine(provider).answer(
            question,
            packet,
            trace_id="fixture-UQ-E03",
        )
    )
    response = outcome.response
    quote_only = [
        claim
        for claim in response.claims
        if claim.publication is not None
        and claim.publication.kind.value == "official_quote_only"
    ]

    assert response.response_mode == ResponseMode.PARTIAL
    assert response.validation is not None and response.validation.accepted
    assert _publication_kinds(response) == {
        "structured_reviewed",
        "official_quote_only",
    }
    assert any(
        claim.publication is not None
        and claim.publication.typed_claim_id == "TC-FIRESMART-021-01"
        for claim in response.claims
    )
    assert len(quote_only) == 1
    assert quote_only[0].supports[0].quote == by_id[retrieval_order[1]].text
    assert "personal medications" not in (response.answer or "").casefold()
    assert "at work" not in (response.answer or "").casefold()
    assert "pets are part of the family" not in (response.answer or "").casefold()
    assert outcome.attempts == 0
    assert _provider_calls(provider) == (0, 0, 0, 0)


def test_uq_e03_actual_corpus_retrieval_selects_repaired_checklist_before_pets() -> None:
    async def run() -> None:
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            execution = await runtime.service.execute_ask(
                QueryRequest(question=_question("UQ-E03"))
            )
        finally:
            await runtime.aclose()

        packet = execution.search.evidence_packet
        assert packet is not None
        assert execution.plan.normalized_question == (
            "wildfire grab-and-go bag contents checklist"
        )
        assert [request.query for request in execution.plan.retrieval_requests] == [
            "wildfire grab-and-go bag contents checklist"
        ]
        assert execution.plan.required_aspects == [_question("UQ-E03")]
        assert execution.retrieval.reranked_hits[0].chunk_id == (
            "preparedbc_wildfire_guide:page:5:chunk:1"
        )
        assert packet.items[0].primary_chunk_ids == ["preparedbc_wildfire_guide:page:5:chunk:1"]

        response = execution.response
        quote_only = [
            claim
            for claim in response.claims
            if claim.publication is not None
            and claim.publication.kind.value == "official_quote_only"
        ]
        assert response.response_mode == ResponseMode.PARTIAL
        assert response.validation is not None and response.validation.accepted
        assert _publication_kinds(response) == {
            "structured_reviewed",
            "official_quote_only",
        }
        assert any(
            claim.publication is not None
            and claim.publication.typed_claim_id == "TC-FIRESMART-021-01"
            for claim in response.claims
        )
        assert len(quote_only) == 1
        assert quote_only[0].supports[0].quote == packet.items[0].primary_text
        assert "pets are part of the family" not in (response.answer or "").casefold()
        assert execution.generations == ()
        assert provider.generate_calls == 0

    asyncio.run(run())


def test_static_packet_fixtures_preserve_quote_only_conditions_and_supported_bounds() -> None:
    chunks = load_chunk_records(ROOT / "data/processed/firelens_static_corpus.chunks.jsonl")
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    config = FireLensConfig.from_env(ROOT)
    cases = {
        "UQ-E04": (
            (
                "preparedbc_wildfire_guide:page:10:chunk:4",
                "preparedbc_wildfire_guide:page:11:chunk:2",
            ),
            ("alert", "order"),
            {ResponseMode.GROUNDED, ResponseMode.PARTIAL},
            {"structured_reviewed"},
        ),
        "UQ-E06": (
            ("preparedbc_wildfire_guide:page:13:chunk:2",),
            ("reviewed structured claim",),
            {ResponseMode.SCOPE_REDIRECT},
            set(),
        ),
        "UQ-M10": (
            ("preparedbc_wildfire_guide:page:12:chunk:1",),
            ("follow instructions", "local authority"),
            {ResponseMode.PARTIAL},
            {"official_quote_only"},
        ),
        "UQ-M11": (
            ("preparedbc_wildfire_guide:page:12:chunk:1",),
            ("natural gas", "evacuation order"),
            {ResponseMode.PARTIAL},
            {"official_quote_only"},
        ),
        "UQ-H12": (
            ("preparedbc_wildfire_guide:page:12:chunk:1",),
            ("gas", "evacuation order"),
            {ResponseMode.PARTIAL},
            {"official_quote_only"},
        ),
        "UQ-VH11": (
            ("preparedbc_wildfire_guide:page:5:chunk:1",),
            ("reviewed structured claim",),
            {ResponseMode.SCOPE_REDIRECT},
            set(),
        ),
    }

    async def run() -> None:
        engine = GroundedAnswerEngine(FakeProvider())
        for case_id, (chunk_ids, required_text, modes, kinds) in cases.items():
            selected = [by_id[chunk_id] for chunk_id in chunk_ids]
            hits = [
                retrieval_hit_from_chunk(chunk, rerank_rank=rank)
                for rank, chunk in enumerate(selected, start=1)
            ]
            packet = build_evidence_packet(
                _question(case_id),
                hits,
                selected,
                corpus_version="v1-6-e2e-fixture.v1",
                config=config,
            )
            response = (
                await engine.answer(_question(case_id), packet, trace_id=f"fixture-{case_id}")
            ).response
            answer = (response.answer or "").casefold()
            assert response.response_mode in modes, case_id
            assert all(fragment in answer for fragment in required_text), case_id
            assert "prescrib" not in answer
            assert _publication_kinds(response) == kinds, case_id
            if "official_quote_only" in kinds:
                assert all(
                    item.primary_chunk_ids and item.primary_chunk_ids[0] in by_id
                    for item in packet.items
                )

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


def test_actual_runtime_keeps_generic_kit_and_pet_continuation_in_reviewed_lane() -> None:
    """Exercise typed static context through the real corpus and agent tool path."""

    async def run() -> None:
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        try:
            mixed = await FireLensAgent(
                runtime.service,
                LiveAnswerCoordinator(_FixtureProvinceLiveService([_fire()])),
            ).answer(
                QueryRequest(
                    question=(
                        "List active BC fires and summarize their reported status, "
                        "then give general kit guidance."
                    )
                )
            )
            assert mixed.response.response_mode == ResponseMode.MIXED
            assert {section.kind.value for section in mixed.response.answer_sections} >= {
                "current_records",
                "reviewed_guidance",
            }
            assert _publication_kinds(mixed.response) == {"official_quote_only"}
            assert AgentTool.LIST_OFFICIAL_FIRES in mixed.tools
            assert AgentTool.SEARCH_REVIEWED_GUIDANCE in mixed.tools
            assert any(
                "Grab-and-Go Bag" in claim.text for claim in mixed.response.claims
            )

            pets = await FireLensAgent(
                runtime.service,
                LiveAnswerCoordinator(_FixtureLiveService([])),
            ).answer(
                QueryRequest(
                    question="What about pets?",
                    history=[
                        ConversationTurn(
                            role="user",
                            content="What belongs in a wildfire emergency kit?",
                        )
                    ],
                )
            )
            assert pets.response.response_mode == ResponseMode.PARTIAL
            assert _publication_kinds(pets.response) == {"official_quote_only"}
            assert AgentTool.SEARCH_REVIEWED_GUIDANCE in pets.tools
            assert any(
                "Pets are part of the family" in claim.text
                for claim in pets.response.claims
            )
        finally:
            await runtime.aclose()

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


def test_population_specific_smoke_question_never_substitutes_another_group() -> None:
    async def run() -> None:
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            response = await runtime.service.ask(
                QueryRequest(question="What should I do about wildfire smoke if I am pregnant?")
            )
        finally:
            await runtime.aclose()

        answer = (response.answer or "").casefold()
        assert "asthma" not in answer
        assert "copd" not in answer
        assert all(
            claim.publication is None
            or claim.publication.typed_claim_id != "TC-VULNERABLE-023-01"
            for claim in response.claims
        )
        assert response.response_mode in {ResponseMode.PARTIAL, ResponseMode.SCOPE_REDIRECT}

    asyncio.run(run())
