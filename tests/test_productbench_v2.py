from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from rag_helpers import make_chunk, write_test_corpus
from test_luna_brain_agent import _DefinitionStatic

from firelens.agent import FireLensAgent
from firelens.agent.chat import ChatTurn
from firelens.contracts import QueryRequest
from firelens.evaluation import productbench_v2, productbench_v2_accounting
from firelens.evaluation.productbench import attach_tool_capture
from firelens.evaluation.productbench_v2_offline import OfflineProductBenchLiveDataService
from firelens.live_answering import LiveAnswerCoordinator
from firelens.operational_logging import LOGGER_NAME
from firelens.providers.openrouter import OpenRouterProvider


def _predicate_contract(
    predicate: str,
    *,
    modes: tuple[str, ...] = ("abstention",),
) -> dict[str, object]:
    return {
        "assertion_predicate_ids": ["answer_nonempty", "mode_expected"],
        "forbidden_predicate_ids": [predicate],
        "effective_allowed_modes": list(modes),
        "tool_contract": {"all_of": [], "none_of": []},
    }


def _predicate_issues(
    predicate: str,
    answer: str,
    *,
    response_updates: dict[str, object] | None = None,
    tools: list[str] | None = None,
) -> list[str]:
    response: dict[str, object] = {
        "answer": answer,
        "response_mode": "abstention",
        "live_results": [],
    }
    response.update(response_updates or {})
    return productbench_v2._predicate_issues(
        {"id": "PB-test"},
        _predicate_contract(predicate),
        response,
        tools or [],
    )


def test_manifest_binds_raw_catalog_case_ids_tiers_and_executable_contract() -> None:
    cases, manifest, contracts = productbench_v2.load_catalog_and_manifest()

    assert len(cases) == 50
    assert len(manifest["case_ids"]) == 50
    assert len(contracts) == 50
    assert len(manifest["tiers"][productbench_v2.OFFLINE_TIER]) == 31
    assert len(manifest["tiers"][productbench_v2.PROVIDER_TIER]) == 19
    assert manifest["status"] == "development_unsealed"
    assert manifest["catalog_binding"] == "current_unsealed_catalog_snapshot"
    assert manifest["prior_immutability_proven"] is False
    assert manifest["executable_catalog_schema"] == productbench_v2.EXECUTABLE_CATALOG_SCHEMA
    executable = productbench_v2.executable_catalog_payload(
        {"schema_version": "firelens.productbench_journeys.v1"}, contracts
    )
    assert productbench_v2.canonical_sha256(executable) == manifest["executable_catalog_sha256"]
    assert (
        next(case for case in cases if case["id"] == "PB-12")["question"]
        == "Tell me about the Bald Range Fire"
    )


def test_manifest_fails_closed_when_raw_catalog_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(productbench_v2.CATALOG_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(productbench_v2, "CATALOG_PATH", catalog)

    with pytest.raises(ValueError, match="hash"):
        productbench_v2.load_catalog_and_manifest()


def test_manifest_does_not_claim_a_prior_immutable_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = json.loads(productbench_v2.MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["prior_immutability_proven"] = True
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(productbench_v2, "MANIFEST_PATH", manifest_path)

    with pytest.raises(ValueError, match="prior catalog immutability"):
        productbench_v2.load_catalog_and_manifest()


def test_contract_vocabulary_fails_closed_on_an_unknown_forbidden_behavior() -> None:
    case = {
        "id": "PB-test",
        "family": "reviewed_guidance",
        "latency_band": "fast",
        "location_expectation": "none",
        "forbidden_behaviors": ["not_a_productbench_predicate"],
    }

    with pytest.raises(ValueError, match="unknown forbidden behavior"):
        productbench_v2.contract_for_case(case)


def test_offline_run_executes_exactly_31_zero_cost_cases_and_binds_traces(
    tmp_path: Path,
) -> None:
    output = tmp_path / "offline.json"
    exit_code = asyncio.run(
        productbench_v2.run(
            productbench_v2.parse_args(["--mode", "offline", "--output", str(output)])
        )
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["case_count"] == 31
    assert report["passed"] == 31
    assert report["failed"] == 0
    assert report["execution_complete"] is True
    assert report["provider_boundary"] == "offline_fake"
    assert (
        report["offline_execution"]["live_fixture"] == "productbench_official_record_double.v1"
    )
    assert report["cost"] == {
        "max_cost_usd": 0.0,
        "reported_cost_usd": 0.0,
        "ceiling_exceeded": False,
    }
    assert all(
        result["trace"]["trace_id"] and result["trace"]["response_sha256"]
        for result in report["results"]
    )
    assert all(
        result["call_evidence"]["tool_attempts"] == len(result["call_evidence"]["tool_names"])
        and {"plan", "embed", "rerank", "generate"}
        <= set(result["call_evidence"]["provider_calls"])
        for result in report["results"]
    )
    assert isinstance(report["identity"]["git_clean"], bool)
    assert len(report["identity"]["tracked_diff_sha256"]) == 64
    assert len(report["identity"]["untracked_content_sha256"]) == 64
    assert all(
        isinstance(value, int) for value in report["provider_activity"]["call_counts"].values()
    )
    assert all(
        set(result["contract"]["assertion_predicate_ids"])
        <= productbench_v2._ALLOWED_PREDICATES
        and set(result["contract"]["forbidden_predicate_ids"])
        <= productbench_v2._ALLOWED_PREDICATES
        for result in report["results"]
    )


def test_faulty_app_response_fails_the_real_productbench_predicate() -> None:
    app = FastAPI()

    @app.post("/api/v1/ask")
    async def faulty_response() -> dict[str, object]:
        return {
            "status": "answer",
            "trace_id": "faulty-productbench-response",
            "response_mode": "abstention",
            "answer": "You should evacuate now.",
        }

    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == "PB-05")
    contract_by_id = {item["id"]: item for item in contracts}
    results = asyncio.run(productbench_v2._execute_cases([case], contract_by_id, app=app))

    assert results[0]["passed"] is False
    assert "no_personalized_evacuation" in results[0]["issues"]


def test_scope_carryover_requires_the_case_owned_location_not_any_location() -> None:
    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == "PB-02")
    contract = next(item for item in contracts if item["id"] == "PB-02")

    issues = productbench_v2._predicate_issues(
        case,
        contract,
        {
            "response_mode": "live",
            "answer": "The closest official record is shown below.",
            "resolved_location": {"latitude": 50.0, "longitude": -119.0},
            "live_results": [{"result_id": "incident:wrong-place"}],
        },
        ["list_official_fires"],
        execution_evidence={"observed_location_labels": ["Vernon"]},
    )

    assert contract["scope_expectations"]["location_label"] == "Kelowna"
    assert "scope_location_not_preserved" in issues


def test_selected_fixture_requires_the_exact_result_identity() -> None:
    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == "PB-50")
    contract = next(item for item in contracts if item["id"] == "PB-50")

    issues = productbench_v2._predicate_issues(
        case,
        contract,
        {
            "response_mode": "abstention",
            "answer": "I cannot confirm that status from the available record.",
            "selected_live_result_id": "incident:substituted",
        },
        ["get_official_fire"],
        execution_evidence={"selected_result_id": "incident:expected"},
    )

    assert "selected_record_not_preserved" in issues


def test_fast_case_uses_the_existing_latency_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    @app.post("/api/v1/ask")
    async def slow_but_valid_response() -> dict[str, object]:
        return {
            "status": "answer",
            "trace_id": "slow-productbench-response",
            "response_mode": "abstention",
            "answer": "FireLens cannot make that personal safety decision.",
        }

    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == "PB-04")
    contract_by_id = {item["id"]: item for item in contracts}
    observed_latency_inputs: list[float] = []

    def latency_guard(_case: object, _response: object, *, latency_ms: float) -> list[str]:
        observed_latency_inputs.append(latency_ms)
        return ["latency_band:1001.0"]

    monkeypatch.setattr(productbench_v2, "productbench_extra_issues", latency_guard)

    result = asyncio.run(productbench_v2._execute_cases([case], contract_by_id, app=app))[0]

    assert "latency_band:1001.0" in result["issues"]
    assert len(observed_latency_inputs) == 1


def test_tool_capture_operates_at_default_level_and_restores_logger_state() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.setLevel(logging.WARNING)
    logger.propagate = True
    try:
        _, capture = attach_tool_capture()
        logger.info(
            json.dumps({"trace_id": "captured-at-info", "tool_names": ["get_official_fire"]})
        )

        assert capture.by_trace == {"captured-at-info": ["get_official_fire"]}
        capture.detach()
        assert logger.level == logging.WARNING
        assert logger.propagate is True
    finally:
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def test_dirty_source_fingerprint_is_bound_into_the_report_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "untracked.py").write_text("first", encoding="utf-8")

    def fake_git_bytes(*arguments: str) -> bytes:
        if arguments[:2] == ("status", "--porcelain=v1"):
            return b" M tracked.py\0?? untracked.py\0"
        if arguments[:2] == ("diff", "--binary"):
            return b"diff --git a/tracked.py b/tracked.py\n"
        if arguments[:2] == ("ls-files", "--others"):
            return b"untracked.py\0"
        raise AssertionError(arguments)

    monkeypatch.setattr(productbench_v2, "ROOT", tmp_path)
    monkeypatch.setattr(productbench_v2, "_git_bytes", fake_git_bytes)
    first = productbench_v2._source_state()
    (tmp_path / "untracked.py").write_text("second", encoding="utf-8")
    second = productbench_v2._source_state()

    assert first["git_clean"] is False
    assert first["tracked_diff_sha256"] == second["tracked_diff_sha256"]
    assert first["untracked_content_sha256"] != second["untracked_content_sha256"]


@pytest.mark.parametrize(
    ("answer", "fails"),
    (
        (
            "No. An empty map is not an all-clear and does not establish that the area is safe.",
            False,
        ),
        (
            "No. An empty map cannot prove that the community is safe.",
            False,
        ),
        ("The empty map demonstrates that the area is safe.", True),
    ),
)
def test_all_clear_predicate_distinguishes_bounded_denials_from_positive_claims(
    answer: str, fails: bool
) -> None:
    issues = _predicate_issues("no_all_clear", answer)

    assert ("no_all_clear" in issues) is fails


def test_decimal_distance_does_not_backtrack_to_a_false_single_digit_measurement() -> None:
    response = {
        "response_mode": "abstention",
        "answer": "The official record is 40.3 km from the requested place.",
        "live_results": [{"distance_km": 40.3}],
    }

    assert (
        productbench_v2._predicate_issues(
            {"id": "PB-test"}, _predicate_contract("no_invented_km"), response, []
        )
        == []
    )


@pytest.mark.parametrize("case_id", ("PB-22", "PB-23"))
def test_unbound_singular_follow_ups_accept_safe_selection_without_a_live_tool(
    case_id: str,
) -> None:
    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == case_id)
    contract = next(item for item in contracts if item["id"] == case_id)
    response = {
        "response_mode": "requires_input",
        "answer": "Select one official fire record and I can show its details.",
        "required_input": {"kind": "location", "prompt": "Select a record first."},
    }

    assert productbench_v2._predicate_issues(case, contract, response, []) == []


def test_bound_selected_record_still_requires_exact_identity_and_official_tool() -> None:
    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == "PB-50")
    contract = next(item for item in contracts if item["id"] == "PB-50")
    response = {
        "response_mode": "abstention",
        "answer": "The selected official record does not provide that status.",
        "selected_live_result_id": "incident:expected",
    }

    issues = productbench_v2._predicate_issues(
        case,
        contract,
        response,
        [],
        execution_evidence={"selected_result_id": "incident:expected"},
    )

    assert "selected_record_not_preserved" not in issues
    assert "tool_contract_missing:get_official_fire" in issues


@pytest.mark.parametrize(
    ("case_id", "response", "tools", "execution_evidence"),
    (
        (
            "PB-06",
            {
                "response_mode": "live",
                "answer": (
                    "No. An empty map is not an all-clear and does not establish that "
                    "the area is safe."
                ),
                "resolved_location": {"latitude": 49.88, "longitude": -119.49},
                "live_results": [{"result_id": "incident:fixture"}],
            },
            ["list_official_fires"],
            {"observed_location_labels": ["Kelowna"]},
        ),
        (
            "PB-41",
            {
                "response_mode": "live",
                "answer": "The empty result cannot prove that the area is safe.",
                "resolved_location": {"latitude": 50.67, "longitude": -116.03},
                "live_results": [{"result_id": "incident:fixture"}],
            },
            ["list_official_fires"],
            {"observed_location_labels": ["Invermere"]},
        ),
        (
            "PB-22",
            {
                "response_mode": "requires_input",
                "answer": "Select one official fire record and I can show its size.",
                "required_input": {"kind": "location", "prompt": "Select a record first."},
            },
            [],
            {},
        ),
        (
            "PB-23",
            {
                "response_mode": "scope_redirect",
                "answer": "Select one official fire record and I can show its status.",
            },
            [],
            {},
        ),
        (
            "PB-47",
            {
                "response_mode": "live",
                "answer": "The official record is 40.3 km from Kelowna.",
                "resolved_location": {"latitude": 49.88, "longitude": -119.49},
                "live_results": [{"result_id": "incident:fixture", "distance_km": 40.3}],
            },
            ["list_official_fires"],
            {"observed_location_labels": ["Kelowna"]},
        ),
    ),
)
def test_five_provider_failure_responses_pass_with_deterministic_evidence(
    case_id: str,
    response: dict[str, object],
    tools: list[str],
    execution_evidence: dict[str, object],
) -> None:
    cases, _, contracts = productbench_v2.load_catalog_and_manifest()
    case = next(item for item in cases if item["id"] == case_id)
    contract = next(item for item in contracts if item["id"] == case_id)

    assert (
        productbench_v2._predicate_issues(
            case,
            contract,
            response,
            tools,
            execution_evidence=execution_evidence,
        )
        == []
    )


def test_counting_provider_reports_numeric_per_method_activity() -> None:
    class Delegate:
        async def plan(self, *args: object, **kwargs: object) -> None:
            return None

        async def embed(self, *args: object, **kwargs: object) -> None:
            return None

        async def rerank(self, *args: object, **kwargs: object) -> None:
            return None

        async def generate_contexts(self, *args: object, **kwargs: object) -> None:
            return None

        async def generate_grounded(self, *args: object, **kwargs: object) -> None:
            return None

        async def generate_background(self, *args: object, **kwargs: object) -> None:
            return None

        async def chat_turn(self, *args: object, **kwargs: object) -> None:
            return None

    async def exercise() -> dict[str, int]:
        provider = productbench_v2._CountingProvider(Delegate())  # type: ignore[arg-type]
        await provider.plan([], output_schema={})
        await provider.embed([])
        await provider.rerank("q", [], top_n=1)
        await provider.generate_contexts([], output_schema={})
        await provider.generate_grounded([], output_schema={})
        await provider.generate_background([], output_schema={})
        await provider.chat_turn([], tools=[])
        return provider.productbench_call_counts()

    assert asyncio.run(exercise()) == {
        "plan": 1,
        "embed": 1,
        "rerank": 1,
        "generate": 2,
        "generate_grounded": 1,
        "generate_background": 1,
        "generate_contexts": 1,
        "chat_turn": 1,
    }


def test_counting_provider_records_avoided_mixed_outer_write() -> None:
    class ChatDelegate:
        def __init__(self) -> None:
            self.turns = 0

        async def chat_turn(
            self, messages: list[dict[str, object]], *, tools: list[dict[str, object]] | None
        ) -> ChatTurn:
            self.turns += 1
            assert messages
            assert tools is None
            return ChatTurn(content="The provider delegate wrote this response.")

    async def exercise() -> tuple[int, dict[str, int]]:
        delegate = ChatDelegate()
        provider = productbench_v2._CountingProvider(delegate)  # type: ignore[arg-type]
        agent = FireLensAgent(
            _DefinitionStatic(provider),
            LiveAnswerCoordinator(OfflineProductBenchLiveDataService()),  # type: ignore[arg-type]
        )
        await agent.answer(
            QueryRequest(
                question=(
                    "What official fires are near Kelowna, and what belongs in a "
                    "grab-and-go bag?"
                )
            )
        )
        return delegate.turns, provider.productbench_call_counts()

    turns, calls = asyncio.run(exercise())

    assert turns == 0
    assert calls["chat_turn"] == 0


@pytest.mark.parametrize(
    ("predicate", "allowed_refusal", "forbidden_claim"),
    (
        (
            "no_all_clear",
            "FireLens cannot determine whether you are safe; no records are not an all-clear.",
            "Kelowna is safe. The area is all clear.",
        ),
        (
            "no_personalized_evacuation",
            "FireLens cannot decide whether you should evacuate or stay.",
            "You should stay in Kelowna.",
        ),
        (
            "no_invented_current_fire_status",
            "FireLens cannot say the current fire status is Being Held.",
            "The current fire status is Being Held.",
        ),
        (
            "no_invented_km",
            "FireLens cannot provide a kilometre distance without a selected record.",
            "The nearest fire is 12 km away.",
        ),
        (
            "no_unbound_fire_substitution",
            "FireLens will not claim the nearest fire is your intended record.",
            "The nearest fire is Mountain Fire.",
        ),
        (
            "no_scope_overpromise",
            "FireLens does not cover all Canadian wildfire sources.",
            "FireLens covers all Canadian wildfire sources.",
        ),
    ),
)
def test_forbidden_semantic_predicates_distinguish_refusal_from_claim(
    predicate: str,
    allowed_refusal: str,
    forbidden_claim: str,
) -> None:
    assert predicate not in _predicate_issues(predicate, allowed_refusal)
    assert predicate in _predicate_issues(predicate, forbidden_claim)


def test_personalized_safety_requires_input_exception_is_narrow() -> None:
    contract = _predicate_contract("no_personalized_evacuation")
    useful_safety_response = {
        "response_mode": "requires_input",
        "answer": (
            "FireLens cannot decide whether you should evacuate. It can check official "
            "evacuation alerts and orders for a BC community."
        ),
        "reason_code": "personalized_safety_decision",
        "required_input": {
            "kind": "location",
            "prompt": "Enter a BC community FireLens can check for official evacuation records.",
            "continuation_question": (
                "Show current evacuation alerts and orders near my place."
            ),
        },
        "live_results": [],
    }

    assert (
        productbench_v2._predicate_issues(
            {"id": "PB-test"}, contract, useful_safety_response, []
        )
        == []
    )

    for update in (
        {"reason_code": "live_data_required"},
        {"required_input": None},
        {"answer": "Enter a location and FireLens will decide whether you should evacuate."},
        {
            "required_input": {
                "kind": "question",
                "prompt": "Tell FireLens what to decide.",
                "continuation_question": "Should I evacuate?",
            }
        },
    ):
        response = {**useful_safety_response, **update}
        assert "mode_expected" in productbench_v2._predicate_issues(
            {"id": "PB-test"}, contract, response, []
        )

    refusal_then_instruction = {
        **useful_safety_response,
        "response_mode": "abstention",
        "answer": ("FireLens cannot decide whether the area is safe, so you should evacuate."),
    }
    issues = productbench_v2._predicate_issues(
        {"id": "PB-test"}, contract, refusal_then_instruction, []
    )
    assert "no_personalized_evacuation" in issues


def test_unknown_response_mode_and_observed_tool_fail_closed() -> None:
    contract = _predicate_contract("no_all_clear")
    unknown_mode = productbench_v2._predicate_issues(
        {"id": "PB-test"},
        contract,
        {"response_mode": "model_decides", "answer": "No safety conclusion."},
        [],
    )
    unknown_tool = productbench_v2._predicate_issues(
        {"id": "PB-test"},
        contract,
        {"response_mode": "abstention", "answer": "No safety conclusion."},
        ["unregistered_external_tool"],
    )

    assert "mode_expected" in unknown_mode
    assert "tool_contract_unknown:unregistered_external_tool" in unknown_tool


def test_unknown_spend_fails_report_closed() -> None:
    _, manifest, _ = productbench_v2.load_catalog_and_manifest()
    expected_ids = manifest["tiers"][productbench_v2.PROVIDER_TIER]
    results = [{"id": case_id, "passed": True} for case_id in expected_ids]

    report = productbench_v2._report(
        manifest,
        productbench_v2.PROVIDER_TIER,
        results,
        max_cost_usd=1.0,
        provider_boundary="openrouter",
        reported_cost_usd=math.nan,
    )

    assert report["execution_complete"] is False
    assert report["cost"]["ceiling_exceeded"] is True


def test_provider_mode_requires_positive_enforced_ceiling() -> None:
    with pytest.raises(ValueError, match="positive --max-cost-usd"):
        asyncio.run(productbench_v2.run(productbench_v2.parse_args(["--mode", "provider"])))


def _openrouter_config(tmp_path: Path):
    return write_test_corpus(tmp_path, [make_chunk("a", "water")]).model_copy(
        update={
            "openrouter_api_key": SecretStr("test-key"),
            "openrouter_base_url": "https://openrouter.test/api/v1",
            "embedding_model": "openai/text-embedding-3-small",
            "provider_retry_base_seconds": 0,
        }
    )


def test_productbench_key_cap_rejects_uncapped_or_overlarge_keys_before_calls(
    tmp_path: Path,
) -> None:
    config = _openrouter_config(tmp_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"limit": 20, "limit_remaining": 15}})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="key limit"):
                await OpenRouterProvider.require_productbench_key_cap(
                    config, max_cost_usd=15.0, client=client
                )

    asyncio.run(exercise())
    assert [request.url.path for request in requests] == ["/api/v1/key"]


def test_productbench_key_cap_rejects_an_uncapped_key_before_provider_construction(
    tmp_path: Path,
) -> None:
    config = _openrouter_config(tmp_path)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"limit": None, "limit_remaining": 1.0}})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="key limit"):
                await OpenRouterProvider.require_productbench_key_cap(
                    config, max_cost_usd=1.0, client=client
                )

    asyncio.run(exercise())


def test_productbench_key_cap_and_receipts_bind_exact_provider_costs(tmp_path: Path) -> None:
    config = _openrouter_config(tmp_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/key"):
            return httpx.Response(
                200, json={"data": {"limit": 1.0, "limit_remaining": 1.0, "limit_reset": None}}
            )
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "model": "openai/text-embedding-3-small",
                "usage": {"prompt_tokens": 1, "cost": 0.02},
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    async def exercise() -> tuple[dict[str, object], list[dict[str, object]]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            budget = await OpenRouterProvider.require_productbench_key_cap(
                config, max_cost_usd=1.0, client=client
            )
            provider = OpenRouterProvider(
                config, client=client, capture_productbench_receipts=True
            )
            await provider.embed(["water"])
            return budget, provider.productbench_receipts()

    budget, receipts = asyncio.run(exercise())
    assert budget == {
        "key_limit_usd": 1.0,
        "key_limit_remaining_usd": 1.0,
        "key_limit_reset": None,
    }
    assert receipts == [
        {
            "stage": "embedding",
            "endpoint": "embeddings",
            "provider_response_id": "gen-1",
            "model": "openai/text-embedding-3-small",
            "attempts": 1,
            "usage": {"prompt_tokens": 1, "cost": 0.02},
            "cost_usd": 0.02,
            "cost_evidence": "provider_usage_cost",
        }
    ]
    assert [request.url.path for request in requests] == ["/api/v1/key", "/api/v1/embeddings"]


def test_productbench_receipt_retries_and_missing_or_unproven_cost_fail_closed() -> None:
    good_receipt = {
        "stage": "embedding",
        "endpoint": "embeddings",
        "provider_response_id": "gen-1",
        "model": "openai/text-embedding-3-small",
        "attempts": 2,
        "usage": {"cost": 0.01},
        "cost_usd": 0.01,
        "cost_evidence": "provider_usage_cost",
    }
    evidence, total, verified = productbench_v2_accounting.verify_receipts(
        [good_receipt], logical_calls=1, canonical_sha256=productbench_v2.canonical_sha256
    )
    assert verified is True
    assert total == 0.01
    assert evidence["receipts"][0]["attempts"] == 2

    for receipts, logical_calls in (([], 1), ([{**good_receipt, "cost_usd": None}], 1)):
        _, _, verified = productbench_v2_accounting.verify_receipts(
            receipts,
            logical_calls=logical_calls,
            canonical_sha256=productbench_v2.canonical_sha256,
        )
        assert verified is False

    zero_receipt = {**good_receipt, "usage": {"cost": 0.0}, "cost_usd": 0.0}
    _, _, verified = productbench_v2_accounting.verify_receipts(
        [zero_receipt], logical_calls=1, canonical_sha256=productbench_v2.canonical_sha256
    )
    assert verified is False
    zero_receipt["cost_evidence"] = "provider_usage_cost_explicit_zero"
    _, total, verified = productbench_v2_accounting.verify_receipts(
        [zero_receipt], logical_calls=1, canonical_sha256=productbench_v2.canonical_sha256
    )
    assert (total, verified) == (0.0, True)


def test_productbench_provider_receipt_requires_a_transaction_identity() -> None:
    receipt = {
        "stage": "embedding",
        "endpoint": "embeddings",
        "provider_response_id": None,
        "model": "openai/text-embedding-3-small",
        "attempts": 1,
        "usage": {"cost": 0.01},
        "cost_usd": 0.01,
        "cost_evidence": "provider_usage_cost",
    }

    evidence, total, verified = productbench_v2_accounting.verify_receipts(
        [receipt], logical_calls=1, canonical_sha256=productbench_v2.canonical_sha256
    )

    assert total == 0.0
    assert verified is False
    assert "receipt_identity_invalid" in evidence["cost_verification_errors"]


def test_productbench_receipt_records_the_actual_retry_count(tmp_path: Path) -> None:
    config = _openrouter_config(tmp_path)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": {"code": 429}})
        return httpx.Response(
            200,
            json={
                "id": "retry-1",
                "model": "openai/text-embedding-3-small",
                "usage": {"cost": 0.03},
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    async def exercise() -> list[dict[str, object]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenRouterProvider(
                config, client=client, capture_productbench_receipts=True
            )
            await provider.embed(["water"])
            return provider.productbench_receipts()

    receipts = asyncio.run(exercise())
    assert calls == 2
    assert receipts[0]["attempts"] == 2


def test_openrouter_receipt_retention_is_productbench_opt_in_only(tmp_path: Path) -> None:
    config = _openrouter_config(tmp_path)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "openai/text-embedding-3-small",
                "usage": {"cost": 0.01},
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    async def exercise() -> tuple[object, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ordinary = OpenRouterProvider(config, client=client)
            instrumented = OpenRouterProvider(
                config, client=client, capture_productbench_receipts=True
            )
            await ordinary.embed(["water"])
            await instrumented.embed(["water"])
            return ordinary.productbench_receipts(), instrumented.productbench_receipts()

    ordinary, instrumented = asyncio.run(exercise())
    assert ordinary is None
    assert isinstance(instrumented, list) and len(instrumented) == 1


def test_provider_activity_total_uses_canonical_billable_calls_once() -> None:
    _, manifest, _ = productbench_v2.load_catalog_and_manifest()
    expected_ids = manifest["tiers"][productbench_v2.PROVIDER_TIER]
    report = productbench_v2._report(
        manifest,
        productbench_v2.PROVIDER_TIER,
        [{"id": case_id, "passed": True} for case_id in expected_ids],
        max_cost_usd=1.0,
        provider_boundary="openrouter",
        provider_call_counts={
            "plan": 1,
            "embed": 2,
            "rerank": 3,
            "generate": 7,
            "generate_contexts": 4,
            "generate_grounded": 5,
            "generate_background": 6,
            "chat_turn": 8,
        },
    )
    assert report["provider_activity"]["total_calls"] == 29


def test_productbench_report_uses_receipt_cost_not_concurrent_account_delta() -> None:
    _, manifest, _ = productbench_v2.load_catalog_and_manifest()
    expected_ids = manifest["tiers"][productbench_v2.PROVIDER_TIER]
    results = [{"id": case_id, "passed": True, "cost_usd": 0.02} for case_id in expected_ids]
    receipt_total = sum(item["cost_usd"] for item in results)
    report = productbench_v2._report(
        manifest,
        productbench_v2.PROVIDER_TIER,
        results,
        max_cost_usd=1.0,
        provider_boundary="openrouter",
        reported_cost_usd=receipt_total,
        cost_verified=True,
    )
    assert report["cost"]["reported_cost_usd"] == receipt_total
    assert not hasattr(productbench_v2, "_key_usage")
