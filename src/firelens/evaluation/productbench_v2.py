"""Hash-bound, two-tier ProductBench v2 evaluation runner.

ProductBench is development coverage, not a sealed or release-qualification set.
The offline tier is intentionally a deterministic contract exercise; provider runs
are opt-in, execute all provider cases, and fail closed on missing cost evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.evaluation import (
    productbench_predicates,
    productbench_v2_accounting,
    productbench_v2_identity,
    productbench_v2_report,
)
from firelens.evaluation.productbench import (
    attach_tool_capture,
    load_productbench_cases,
    productbench_extra_issues,
)
from firelens.evaluation.productbench_v2_offline import OfflineProductBenchLiveDataService
from firelens.live import LiveDataService
from firelens.live_contracts import LocationInput
from firelens.providers.base import AIProvider
from firelens.providers.fake import FakeProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data/evaluation/productbench_journeys_50.json"
MANIFEST_PATH = ROOT / "data/evaluation/productbench_v2.manifest.json"
DEFAULT_OUTPUT = ROOT / "output/productbench"

EXECUTABLE_CATALOG_SCHEMA = "firelens.productbench_executable_catalog.v2"

# Preserve the runner's import surface while keeping all closed predicate logic
# in the pure evaluator module.
OFFLINE_TIER = productbench_predicates.OFFLINE_TIER
PROVIDER_TIER = productbench_predicates.PROVIDER_TIER
_ALLOWED_TIERS = productbench_predicates.ALLOWED_TIERS
_ALLOWED_TOOLS = productbench_predicates.ALLOWED_TOOLS
_ALLOWED_PREDICATES = productbench_predicates.ALLOWED_PREDICATES
tier_for_case = productbench_predicates.tier_for_case
contract_for_case = productbench_predicates.contract_for_case
contracts = productbench_predicates.contracts
_predicate_issues = productbench_predicates.predicate_issues


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _git_value(revision: str) -> str | None:
    return productbench_v2_identity.git_value(ROOT, revision)


def _git_bytes(*arguments: str) -> bytes:
    return productbench_v2_identity.git_bytes(ROOT, *arguments)


def _source_state() -> dict[str, Any]:
    return productbench_v2_identity.source_state(
        root=ROOT, git_bytes=_git_bytes, canonical_sha256=canonical_sha256
    )


def _load_raw_catalog() -> dict[str, Any]:
    return productbench_v2_identity.load_raw_catalog(CATALOG_PATH)


def executable_catalog_payload(
    catalog: dict[str, Any], contract_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    return productbench_v2_identity.executable_catalog_payload(
        schema=EXECUTABLE_CATALOG_SCHEMA,
        catalog=catalog,
        catalog_path=CATALOG_PATH,
        file_sha256=file_sha256,
        contract_rows=contract_rows,
    )


def load_catalog_and_manifest() -> tuple[
    list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]
]:
    catalog = _load_raw_catalog()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = catalog["cases"]
    raw_ids = [str(case["id"]) for case in cases]
    if manifest.get("schema_version") != "firelens.productbench_manifest.v2":
        raise ValueError("unexpected ProductBench v2 manifest schema")
    if manifest.get("raw_catalog_schema") != catalog["schema_version"]:
        raise ValueError("ProductBench manifest raw schema mismatch")
    if manifest.get("raw_catalog_sha256") != file_sha256(CATALOG_PATH):
        raise ValueError("ProductBench raw catalog hash mismatch")
    if manifest.get("case_count") != 50 or manifest.get("case_ids") != raw_ids:
        raise ValueError("ProductBench manifest case IDs/count mismatch")
    if manifest.get("status") != "development_unsealed":
        raise ValueError("ProductBench status must remain development_unsealed")
    if manifest.get("catalog_binding") != "current_unsealed_catalog_snapshot":
        raise ValueError("ProductBench manifest must bind the current unsealed catalog")
    if manifest.get("prior_immutability_proven") is not False:
        raise ValueError("ProductBench manifest must not claim prior catalog immutability")
    expected_contracts = contracts(cases)
    if manifest.get("contract_sha256") != canonical_sha256(expected_contracts):
        raise ValueError("ProductBench executable contract hash mismatch")
    executable_catalog = executable_catalog_payload(catalog, expected_contracts)
    if manifest.get("executable_catalog_schema") != EXECUTABLE_CATALOG_SCHEMA:
        raise ValueError("ProductBench executable catalog schema mismatch")
    if manifest.get("executable_catalog_sha256") != canonical_sha256(executable_catalog):
        raise ValueError("ProductBench executable catalog hash mismatch")
    tiers = manifest.get("tiers")
    if not isinstance(tiers, dict) or set(tiers) != _ALLOWED_TIERS:
        raise ValueError("ProductBench manifest tiers are incomplete")
    for tier in _ALLOWED_TIERS:
        expected_ids = [item["id"] for item in expected_contracts if item["tier"] == tier]
        if tiers.get(tier) != expected_ids:
            raise ValueError(f"ProductBench manifest {tier} IDs mismatch")
    if len(tiers[OFFLINE_TIER]) != 31 or len(tiers[PROVIDER_TIER]) != 19:
        raise ValueError("ProductBench tier split must remain 31 offline and 19 provider cases")
    return cases, manifest, expected_contracts


def _identity(manifest: dict[str, Any], *, tier: str) -> dict[str, Any]:
    return productbench_v2_identity.identity(
        root=ROOT,
        catalog_path=CATALOG_PATH,
        manifest_path=MANIFEST_PATH,
        manifest=manifest,
        tier=tier,
        git_value=_git_value,
        file_sha256=file_sha256,
        source_state_value=_source_state(),
    )


class _ScopeCapturingLiveService:
    """Record the normalized live scope used by one ProductBench request."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.observed_location_labels: list[str] = []

    def reset_case(self) -> None:
        self.observed_location_labels.clear()

    def evidence(self, *, selected_result_id: str | None = None) -> dict[str, Any]:
        return {
            "observed_location_labels": list(self.observed_location_labels),
            "selected_result_id": selected_result_id,
        }

    def _record(self, location: LocationInput) -> None:
        if location.label and location.label not in self.observed_location_labels:
            self.observed_location_labels.append(location.label)

    async def aclose(self) -> None:
        await self._delegate.aclose()

    async def map_results(self, **kwargs: Any) -> Any:
        return await self._delegate.map_results(**kwargs)

    async def resolve_location(self, location: LocationInput) -> tuple[float, float]:
        self._record(location)
        return cast(tuple[float, float], await self._delegate.resolve_location(location))

    async def nearby_results(self, location: LocationInput, **kwargs: Any) -> Any:
        self._record(location)
        return await self._delegate.nearby_results(location, **kwargs)

    async def nearby_page(self, location: LocationInput, **kwargs: Any) -> Any:
        self._record(location)
        return await self._delegate.nearby_page(location, **kwargs)


class _CountingProvider:
    """Count every AIProvider boundary call without changing provider routing."""

    def __init__(self, delegate: AIProvider) -> None:
        self._delegate = delegate
        self._calls = {
            "plan": 0,
            "embed": 0,
            "rerank": 0,
            "generate": 0,
            "generate_grounded": 0,
            "generate_background": 0,
            "generate_contexts": 0,
            "chat_turn": 0,
        }

    def productbench_call_counts(self) -> dict[str, int]:
        return dict(self._calls)

    def productbench_receipts(self) -> list[dict[str, object]] | None:
        reader = getattr(self._delegate, "productbench_receipts", None)
        values = reader() if callable(reader) else None
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            return None
        return [dict(item) for item in values]

    async def plan(self, messages: Any, *, output_schema: dict[str, Any]) -> Any:
        self._calls["plan"] += 1
        return await self._delegate.plan(messages, output_schema=output_schema)

    async def embed(self, texts: Any) -> Any:
        self._calls["embed"] += 1
        return await self._delegate.embed(texts)

    async def rerank(self, query: str, documents: Any, *, top_n: int) -> Any:
        self._calls["rerank"] += 1
        return await self._delegate.rerank(query, documents, top_n=top_n)

    async def generate_contexts(self, messages: Any, *, output_schema: dict[str, Any]) -> Any:
        self._calls["generate_contexts"] += 1
        return await self._delegate.generate_contexts(messages, output_schema=output_schema)

    async def generate_grounded(self, messages: Any, *, output_schema: dict[str, Any]) -> Any:
        self._calls["generate"] += 1
        self._calls["generate_grounded"] += 1
        return await self._delegate.generate_grounded(messages, output_schema=output_schema)

    async def generate_background(self, messages: Any, *, output_schema: dict[str, Any]) -> Any:
        self._calls["generate"] += 1
        self._calls["generate_background"] += 1
        return await self._delegate.generate_background(messages, output_schema=output_schema)

    async def chat_turn(self, messages: Any, *, tools: Any = None) -> Any:
        """Preserve the outer Luna path instead of falling back to heuristic writing."""

        self._calls["chat_turn"] += 1
        chat = getattr(self._delegate, "chat_turn", None)
        if not callable(chat):
            raise RuntimeError("ProductBench provider does not implement chat_turn")
        return await chat(messages, tools=tools)

    def operational_state(self) -> Any:
        state_reader = getattr(self._delegate, "operational_state", None)
        return state_reader() if callable(state_reader) else "configured_unprobed"

    async def aclose(self) -> None:
        close = getattr(self._delegate, "aclose", None)
        if close is not None:
            await close()


def _provider_call_counts(provider: Any) -> dict[str, int] | None:
    recorded = getattr(provider, "productbench_call_counts", None)
    if callable(recorded):
        values = recorded()
        if isinstance(values, dict) and all(
            isinstance(name, str) and isinstance(value, int) and value >= 0
            for name, value in values.items()
        ):
            return cast(dict[str, int], values)
    names = ("plan", "embed", "rerank", "generate")
    values = {name: getattr(provider, f"{name}_calls", None) for name in names}
    if not all(isinstance(value, int) and value >= 0 for value in values.values()):
        return None
    return {name: cast(int, value) for name, value in values.items()}


def _provider_call_delta(
    before: dict[str, int] | None, after: dict[str, int] | None
) -> dict[str, int] | None:
    if before is None or after is None or set(before) != set(after):
        return None
    return {name: after[name] - before[name] for name in before}


def _provider_receipts(provider: Any) -> list[dict[str, object]] | None:
    reader = getattr(provider, "productbench_receipts", None)
    values = reader() if callable(reader) else None
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        return None
    return [dict(item) for item in values]


async def _execute_cases(
    cases: list[dict[str, Any]],
    contracts_by_id: dict[str, dict[str, Any]],
    *,
    app: Any,
    tool_capture: Any | None = None,
    scope_capture: _ScopeCapturingLiveService | None = None,
    provider: Any | None = None,
) -> list[dict[str, Any]]:
    """Exercise the actual ASGI request path and score its unmodified payloads."""

    results: list[dict[str, Any]] = []
    productbench_cases_by_id = {item.id: item for item in load_productbench_cases()}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://productbench.test"
    ) as client:
        for case in cases:
            if scope_capture is not None:
                scope_capture.reset_case()
            calls_before = _provider_call_counts(provider)
            started = time.perf_counter()
            http_response = await client.post(
                "/api/v1/ask",
                json={
                    "question": case["question"],
                    "history": case.get("history") or [],
                    "context": {},
                },
            )
            response = http_response.json()
            tools = (
                tool_capture.by_trace.get(str(response.get("trace_id") or ""), [])
                if tool_capture is not None
                else []
            )
            latency_ms = round((time.perf_counter() - started) * 1_000, 1)
            execution_evidence = scope_capture.evidence() if scope_capture is not None else {}
            issues = _predicate_issues(
                case,
                contracts_by_id[case["id"]],
                response,
                tools,
                execution_evidence=execution_evidence,
            )
            product_case = productbench_cases_by_id[case["id"]]
            # ProductBench v2 deliberately reuses the existing fast-lane
            # enforcement rather than silently omitting its latency gate.  Its
            # safety-disposition labels are already represented by v2's closed
            # response-mode predicates, so only the latency finding is added.
            issues.extend(
                issue
                for issue in productbench_extra_issues(
                    product_case,
                    response,
                    latency_ms=latency_ms,
                )
                if issue.startswith("latency_band:")
            )
            if http_response.status_code != 200:
                issues.append(f"http_{http_response.status_code}")
            calls_after = _provider_call_counts(provider)
            results.append(
                {
                    "id": case["id"],
                    "passed": not issues,
                    "issues": issues,
                    "contract": contracts_by_id[case["id"]],
                    "latency_ms": latency_ms,
                    "call_evidence": {
                        "tool_names": tools,
                        "tool_attempts": len(tools),
                        "provider_calls": _provider_call_delta(calls_before, calls_after),
                    },
                    "scope_evidence": execution_evidence,
                    "trace": {
                        "trace_id": response.get("trace_id"),
                        "tool_names": tools,
                        "response_sha256": canonical_sha256(response),
                    },
                    "cost_usd": 0.0,
                }
            )
    return results


async def _offline_report(
    cases: list[dict[str, Any]],
    manifest: dict[str, Any],
    contracts_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    config = FireLensConfig.from_env(ROOT).model_copy(update={"anonymous_rate_limit": 1_000})
    vector_manifest = json.loads(config.vector_manifest_path.read_text(encoding="utf-8"))
    fake_provider = FakeProvider(dimensions=int(vector_manifest["dimensions"]))
    provider = _CountingProvider(fake_provider)
    runtime = load_runtime(config, provider=provider)
    live_service = _ScopeCapturingLiveService(OfflineProductBenchLiveDataService())
    app = create_app(config, runtime=runtime, live_service=cast(LiveDataService, live_service))
    logger, capture = attach_tool_capture()
    try:
        results = await _execute_cases(
            cases,
            contracts_by_id,
            app=app,
            tool_capture=capture,
            scope_capture=live_service,
            provider=provider,
        )
    finally:
        capture.detach()
        await runtime.aclose()
        await live_service.aclose()
    return _report(
        manifest,
        OFFLINE_TIER,
        results,
        max_cost_usd=0.0,
        provider_boundary="offline_fake",
        offline_execution={
            "live_fixture": "productbench_official_record_double.v1",
            "fake_provider_calls": {
                "plan": fake_provider.plan_calls,
                "embed": fake_provider.embed_calls,
                "rerank": fake_provider.rerank_calls,
                "generate": fake_provider.generate_calls,
            },
        },
        provider_call_counts=provider.productbench_call_counts(),
    )


async def _provider_report(
    cases: list[dict[str, Any]],
    manifest: dict[str, Any],
    contracts_by_id: dict[str, dict[str, Any]],
    *,
    max_cost_usd: float,
) -> dict[str, Any]:
    config = FireLensConfig.from_env(ROOT).model_copy(update={"anonymous_rate_limit": 1_000})
    key_budget = await OpenRouterProvider.require_productbench_key_cap(
        config, max_cost_usd=max_cost_usd
    )
    provider = _CountingProvider(OpenRouterProvider(config, capture_productbench_receipts=True))
    runtime = load_runtime(config, provider=provider)
    live_service = _ScopeCapturingLiveService(LiveDataService())
    app = create_app(config, runtime=runtime, live_service=cast(LiveDataService, live_service))
    logger, capture = attach_tool_capture()
    results: list[dict[str, Any]] = []
    receipt_total = 0.0
    receipts_verified = True
    productbench_cases_by_id = {item.id: item for item in load_productbench_cases()}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://productbench.test"
        ) as client:
            for case in cases:
                if receipt_total >= max_cost_usd:
                    raise RuntimeError(
                        "provider receipt cost ceiling reached before complete ProductBench run"
                    )
                live_service.reset_case()
                calls_before = _provider_call_counts(provider)
                receipts_before = _provider_receipts(provider)
                started = time.perf_counter()
                context: dict[str, str] = {}
                selected: str | None = None
                if case.get("context_fixture") == "first_incident":
                    map_response = await client.get(
                        "/api/v1/live/map?layers=incidents,perimeters,evacuations"
                    )
                    if map_response.status_code == 200:
                        selected = next(
                            (
                                item.get("result_id")
                                for item in map_response.json().get("results", [])
                                if isinstance(item, dict)
                                and item.get("kind") == "incident"
                                and isinstance(item.get("result_id"), str)
                            ),
                            None,
                        )
                        if selected:
                            context["selected_live_result_id"] = selected
                http_response = await client.post(
                    "/api/v1/ask",
                    json={
                        "question": case["question"],
                        "history": case.get("history") or [],
                        "context": context,
                    },
                )
                response = http_response.json()
                tools = capture.by_trace.get(str(response.get("trace_id") or ""), [])
                latency_ms = round((time.perf_counter() - started) * 1_000, 1)
                execution_evidence = live_service.evidence(selected_result_id=selected)
                issues = _predicate_issues(
                    case,
                    contracts_by_id[case["id"]],
                    response,
                    tools,
                    execution_evidence=execution_evidence,
                )
                issues.extend(
                    issue
                    for issue in productbench_extra_issues(
                        productbench_cases_by_id[case["id"]],
                        response,
                        latency_ms=latency_ms,
                    )
                    if issue.startswith("latency_band:")
                )
                if http_response.status_code != 200:
                    issues.append(f"http_{http_response.status_code}")
                calls_after = _provider_call_counts(provider)
                calls_delta = _provider_call_delta(calls_before, calls_after)
                receipt_evidence, case_cost, case_receipts_verified = (
                    productbench_v2_accounting.verify_receipts(
                        productbench_v2_accounting.receipt_delta(
                            receipts_before, _provider_receipts(provider)
                        ),
                        logical_calls=productbench_v2_accounting.billable_call_count(
                            calls_delta
                        ),
                        canonical_sha256=canonical_sha256,
                    )
                )
                if not case_receipts_verified:
                    issues.append("cost_unverified")
                receipt_total += case_cost
                if receipt_total > max_cost_usd:
                    issues.append("cost_ceiling_exceeded")
                receipts_verified = receipts_verified and case_receipts_verified
                results.append(
                    {
                        "id": case["id"],
                        "passed": not issues,
                        "issues": issues,
                        "contract": contracts_by_id[case["id"]],
                        "latency_ms": latency_ms,
                        "call_evidence": {
                            "tool_names": tools,
                            "tool_attempts": len(tools),
                            "provider_calls": calls_delta,
                        },
                        "scope_evidence": execution_evidence,
                        "trace": {
                            "trace_id": response.get("trace_id"),
                            "tool_names": tools,
                            "response_sha256": canonical_sha256(response),
                        },
                        "cost_usd": case_cost,
                        "receipt_evidence": receipt_evidence,
                    }
                )
    finally:
        capture.detach()
        await runtime.aclose()
        await live_service.aclose()
    report = _report(
        manifest,
        PROVIDER_TIER,
        results,
        max_cost_usd=max_cost_usd,
        provider_boundary="openrouter",
        reported_cost_usd=receipt_total,
        provider_call_counts=provider.productbench_call_counts(),
        cost_verified=receipts_verified,
        provider_budget=key_budget,
    )
    if receipt_total > max_cost_usd:
        report["execution_complete"] = False
        report["cost"]["ceiling_exceeded"] = True
    return report


def _report(
    manifest: dict[str, Any],
    tier: str,
    results: list[dict[str, Any]],
    *,
    max_cost_usd: float,
    provider_boundary: str,
    reported_cost_usd: float = 0.0,
    offline_execution: dict[str, Any] | None = None,
    provider_call_counts: dict[str, int] | None = None,
    cost_verified: bool | None = None,
    provider_budget: dict[str, object] | None = None,
) -> dict[str, Any]:
    return productbench_v2_report.build(
        manifest,
        tier,
        results,
        max_cost_usd=max_cost_usd,
        provider_boundary=provider_boundary,
        identity=lambda value: _identity(value, tier=tier),
        reported_cost_usd=reported_cost_usd,
        offline_execution=offline_execution,
        provider_call_counts=provider_call_counts,
        cost_verified=cost_verified,
        provider_budget=provider_budget,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "provider"), default="offline")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    raw_cases, manifest, contract_rows = load_catalog_and_manifest()
    tier: Literal["offline_fake", "provider_manual"] = (
        OFFLINE_TIER if args.mode == "offline" else PROVIDER_TIER
    )
    if args.mode == "offline" and args.max_cost_usd not in {None, 0}:
        raise ValueError("offline ProductBench has a fixed zero-dollar ceiling")
    if args.mode == "provider" and (args.max_cost_usd is None or args.max_cost_usd <= 0):
        raise ValueError("provider ProductBench requires a positive --max-cost-usd ceiling")
    cases = [case for case in raw_cases if tier_for_case(case) == tier]
    contracts_by_id = {row["id"]: row for row in contract_rows}
    report = (
        await _offline_report(cases, manifest, contracts_by_id)
        if args.mode == "offline"
        else await _provider_report(
            cases, manifest, contracts_by_id, max_cost_usd=args.max_cost_usd
        )
    )
    output = args.output or DEFAULT_OUTPUT / f"{args.mode}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"saved {output} passed={report['passed']}/{report['case_count']} complete={report['execution_complete']}"
    )
    return 0 if report["execution_complete"] and report["failed"] == 0 else 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))
