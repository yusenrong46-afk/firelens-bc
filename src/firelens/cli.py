"""One command surface for setup checks, indexing, search, answers, and serving."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import uvicorn

from firelens.api import create_app
from firelens.benchmark import run_benchmark, run_conversation_benchmark
from firelens.canary import run_variability_canary
from firelens.config import FireLensConfig
from firelens.contextual_retrieval_experiment import run_contextual_retrieval_comparison
from firelens.contracts import QueryRequest, ResponseStatus
from firelens.corpus import build_corpus
from firelens.corpus_audit import audit_corpus
from firelens.document_context import generate_document_context_sidecar
from firelens.ingestion.acquire import acquire_registered_sources
from firelens.model_bakeoff import run_model_bakeoff
from firelens.providers.fake import FakeProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.rag_evaluate import run_diagnostic
from firelens.retrieval.embeddings import build_vector_index
from firelens.retrieval_experiment import run_retrieval_comparison
from firelens.runtime import load_corpus_resources, load_runtime


def _config(project_root: Path) -> FireLensConfig:
    return FireLensConfig.from_env(project_root.resolve())


def _print(payload) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


async def _build_index(config: FireLensConfig) -> int:
    chunks, corpus_version = load_corpus_resources(config)
    provider = OpenRouterProvider(config)
    try:
        manifest = await build_vector_index(
            chunks,
            corpus_version=corpus_version,
            config=config,
            provider=provider,
        )
    finally:
        await provider.aclose()
    _print(
        {
            "status": "built",
            "chunk_count": len(manifest.chunk_ids),
            "dimensions": manifest.dimensions,
            "model": manifest.embedding_model,
            "corpus_version": manifest.corpus_version,
        }
    )
    return 0


async def _generate_document_contexts(config: FireLensConfig, output: Path) -> int:
    chunks, _corpus_version = load_corpus_resources(config)
    provider = OpenRouterProvider(config)
    try:
        records = await generate_document_context_sidecar(
            chunks, provider=provider, output_path=output
        )
    finally:
        await provider.aclose()
    _print(
        {
            "status": "generated",
            "output": str(output),
            "context_count": len(records),
            "models": sorted({record.model_id for record in records}),
            "prompt_sha256": records[0].prompt_sha256 if records else None,
        }
    )
    return 0


async def _search_or_ask(config: FireLensConfig, question: str, command: str) -> int:
    runtime = load_runtime(config)
    try:
        if runtime.service is None:
            _print(runtime.health())
            return 2
        request = QueryRequest(question=question)
        response = (
            await runtime.service.search(request)
            if command == "search"
            else await runtime.service.ask(request)
        )
        _print(response)
        return 2 if getattr(response, "status", None) == ResponseStatus.ERROR else 0
    finally:
        await runtime.aclose()


async def _evaluate(config: FireLensConfig, gold: Path, output: Path, limit: int | None) -> int:
    runtime = load_runtime(config)
    try:
        if runtime.service is None:
            _print(runtime.health())
            return 2
        report = await run_diagnostic(
            runtime,
            gold_path=gold,
            output_path=output,
            limit=limit,
        )
        _print(
            {
                "status": "saved",
                "output": str(output),
                "question_count": report["question_count"],
                "status_counts": report["status_counts"],
            }
        )
        return 0 if not report["status_counts"].get("error") else 2
    finally:
        await runtime.aclose()


def _bootstrap_corpus(config: FireLensConfig) -> int:
    registry = config.project_root / "data/sources/source_registry.yaml"
    repairs = config.project_root / "data/repairs/text_overrides.yaml"
    acquired = acquire_registered_sources(registry, config.project_root)
    _, manifest = build_corpus(
        config.project_root,
        registry_path=registry,
        repairs_path=repairs,
        output_dir=config.project_root / "data/processed",
    )
    _print(
        {
            "status": "built",
            "acquired_source_count": len(acquired),
            "included_source_count": manifest["included_source_count"],
            "chunk_count": manifest["combined_chunk_count"],
        }
    )
    return 0


async def _doctor(config: FireLensConfig) -> int:
    runtime = load_runtime(config)
    try:
        health = runtime.health()
        _print(health)
        return 0 if health.status == "ready" else 1
    finally:
        await runtime.aclose()


async def _benchmark(
    config: FireLensConfig,
    dataset: Path,
    output: Path,
    review_packet: Path,
    splits: list[str] | None,
    max_cost_usd: float | None,
) -> int:
    runtime = load_runtime(config)
    try:
        if runtime.service is None:
            _print(runtime.health())
            return 2
        report = await run_benchmark(
            runtime,
            dataset_path=dataset,
            output_path=output,
            review_packet_path=review_packet,
            splits=set(splits or []),
            max_cost_usd=max_cost_usd,
        )
        _print(
            {
                "status": "saved",
                "output": str(output),
                "review_packet": str(review_packet),
                "case_count": report["case_count"],
                "complete": report["complete"],
                "metrics": report["metrics"],
            }
        )
        return 0 if report["complete"] and report["metrics"]["provider_error_rate"] == 0 else 2
    finally:
        await runtime.aclose()


def _vector_dimensions(config: FireLensConfig) -> int:
    manifest = json.loads(config.vector_manifest_path.read_text(encoding="utf-8"))
    dimensions = manifest.get("dimensions")
    if not isinstance(dimensions, int) or dimensions <= 0:
        raise ValueError("Vector manifest has no valid dimensions value")
    return dimensions


async def _conversation_benchmark(
    config: FireLensConfig,
    dataset: Path,
    output: Path,
    review_packet: Path,
    splits: list[str] | None,
    max_cost_usd: float | None,
    *,
    offline: bool,
) -> int:
    provider = FakeProvider(dimensions=_vector_dimensions(config)) if offline else None
    runtime = load_runtime(config, provider=provider)
    try:
        if runtime.service is None:
            _print(runtime.health())
            return 2
        report = await run_conversation_benchmark(
            runtime,
            dataset_path=dataset,
            output_path=output,
            review_packet_path=review_packet,
            splits=set(splits or []),
            max_cost_usd=max_cost_usd,
            execution_mode="offline_fake" if offline else "live_provider",
        )
        _print(
            {
                "status": "saved",
                "execution_mode": report["execution_mode"],
                "output": str(output),
                "review_packet": str(review_packet),
                "case_count": report["case_count"],
                "complete": report["complete"],
                "metrics": report["metrics"],
            }
        )
        return (
            0 if report["complete"] and report["metrics"]["provider_failure_rate"] == 0 else 2
        )
    finally:
        await runtime.aclose()


async def _tune_retrieval(
    config: FireLensConfig,
    dataset: Path,
    output: Path,
    max_cost_usd: float | None,
) -> int:
    report = await run_retrieval_comparison(
        config,
        dataset_path=dataset,
        output_path=output,
        max_cost_usd=max_cost_usd,
    )
    _print(
        {
            "status": "saved",
            "output": str(output),
            "selected": report["selected"],
            "selection_reason": report["selection_reason"],
            "reported_cost_usd": report["reported_cost_usd"],
            "candidates": report["candidates"],
        }
    )
    complete = all(item["complete"] for item in report["candidates"].values())
    return 0 if complete else 2


async def _compare_contextual_retrieval(
    config: FireLensConfig,
    dataset: Path,
    output: Path,
    experiment_dir: Path,
) -> int:
    report = await run_contextual_retrieval_comparison(
        config,
        dataset_path=dataset,
        output_path=output,
        experiment_dir=experiment_dir,
    )
    _print(
        {
            "status": "saved",
            "output": str(output),
            "case_count": report["case_count"],
            "selected_retrieval_text_strategy": report["selected_retrieval_text_strategy"],
            "selection_reason": report["selection_reason"],
            "reported_cost_usd": report["reported_cost_usd"],
            "candidates": report["candidates"],
        }
    )
    return 0 if report["safety_checks"]["passed"] else 2


async def _canary(
    config: FireLensConfig,
    question: str,
    calls: int,
    output: Path,
    max_cost_usd: float,
) -> int:
    runtime = load_runtime(config)
    try:
        report = await run_variability_canary(
            runtime,
            question=question,
            calls=calls,
            output_path=output,
            max_cost_usd=max_cost_usd,
        )
        _print({key: value for key, value in report.items() if key != "rows"})
        return (
            0
            if report["complete"]
            and not report["status_variance"]
            and report["all_structurally_accepted"]
            else 2
        )
    finally:
        await runtime.aclose()


async def _model_bakeoff(
    config: FireLensConfig,
    dataset: Path,
    output: Path,
    review_packet: Path,
    case_limit: int,
    max_cost_usd: float,
) -> int:
    report = await run_model_bakeoff(
        config,
        dataset_path=dataset,
        output_path=output,
        review_packet_path=review_packet,
        case_limit=case_limit,
        max_cost_usd=max_cost_usd,
    )
    _print({key: value for key, value in report.items() if key != "rows"})
    return 0 if report["complete"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FireLens BC static RAG")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check corpus, index, and provider readiness")
    commands.add_parser(
        "bootstrap-corpus", help="Download hash-pinned sources and rebuild the corpus"
    )
    corpus_audit = commands.add_parser(
        "corpus-audit", help="Audit source coverage and PDF layout candidates"
    )
    corpus_audit.add_argument(
        "--output", type=Path, default=Path("data/evaluation/corpus_quality_v1.json")
    )
    commands.add_parser("build-index", help="Build or update the OpenRouter embedding index")
    contexts = commands.add_parser(
        "generate-document-contexts",
        help="Generate the offline document_context_v2 retrieval sidecar",
    )
    contexts.add_argument("--output", type=Path)
    for command in ("search", "ask"):
        subparser = commands.add_parser(command)
        subparser.add_argument("question")
    evaluate = commands.add_parser("evaluate", help="Run the diagnostic question set")
    evaluate.add_argument(
        "--gold", type=Path, default=Path("data/evaluation/gold_questions.yaml")
    )
    evaluate.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation/rag_v1_diagnostic.json"),
    )
    evaluate.add_argument("--limit", type=int)
    benchmark = commands.add_parser(
        "benchmark", help="Run the strict V1 benchmark and create a review packet"
    )
    benchmark.add_argument(
        "--dataset", type=Path, default=Path("data/evaluation/benchmark_v1.yaml")
    )
    benchmark.add_argument(
        "--output", type=Path, default=Path("output/benchmark/v1_report.json")
    )
    benchmark.add_argument(
        "--review-packet",
        type=Path,
        default=Path("output/benchmark/v1_semantic_review.md"),
    )
    benchmark.add_argument(
        "--split",
        action="append",
        choices=("development", "holdout", "red_team"),
    )
    benchmark.add_argument(
        "--max-cost-usd",
        type=float,
        help="Stop before the next case once provider-reported cost reaches this value",
    )
    conversation_benchmark = commands.add_parser(
        "benchmark-conversation",
        help="Run the strict V1.1 conversation addendum with direct observations",
    )
    conversation_benchmark.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/benchmark_v1_1_conversation.yaml"),
    )
    conversation_benchmark.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_1_conversation_report.json"),
    )
    conversation_benchmark.add_argument(
        "--review-packet",
        type=Path,
        default=Path("output/benchmark/v1_1_conversation_review.md"),
    )
    conversation_benchmark.add_argument(
        "--split",
        action="append",
        choices=("development", "holdout", "red_team"),
    )
    conversation_benchmark.add_argument(
        "--max-cost-usd",
        type=float,
        help="Stop before the next case once provider-reported cost reaches this value",
    )
    conversation_benchmark.add_argument(
        "--offline",
        action="store_true",
        help="Use the deterministic fake provider; performs no paid or network calls",
    )
    tune = commands.add_parser(
        "tune-retrieval", help="Compare the four locked retrieval configurations"
    )
    tune.add_argument("--dataset", type=Path, default=Path("data/evaluation/benchmark_v1.yaml"))
    tune.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_retrieval_comparison.json"),
    )
    tune.add_argument("--max-cost-usd", type=float, default=1.25)
    contextual = commands.add_parser(
        "compare-contextual-retrieval",
        help="Compare raw, planned, and deterministic contextual retrieval",
    )
    contextual.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/benchmark_v1_1_conversation.yaml"),
    )
    contextual.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_1_contextual_retrieval.json"),
    )
    contextual.add_argument(
        "--experiment-dir",
        type=Path,
        default=Path("output/benchmark/contextual_retrieval_experiment"),
    )
    canary = commands.add_parser("canary", help="Run the repeated-generation V1 canary")
    canary.add_argument(
        "--question",
        default="What does an evacuation alert mean, and what should I prepare?",
    )
    canary.add_argument("--calls", type=int, default=30)
    canary.add_argument("--output", type=Path, default=Path("output/benchmark/v1_canary.json"))
    canary.add_argument("--max-cost-usd", type=float, default=0.50)
    bakeoff = commands.add_parser(
        "bakeoff-models", help="Compare generation models on identical evidence packets"
    )
    bakeoff.add_argument(
        "--dataset", type=Path, default=Path("data/evaluation/benchmark_v1.yaml")
    )
    bakeoff.add_argument(
        "--output", type=Path, default=Path("output/benchmark/v1_model_bakeoff.json")
    )
    bakeoff.add_argument(
        "--review-packet",
        type=Path,
        default=Path("output/benchmark/v1_model_bakeoff_review.md"),
    )
    bakeoff.add_argument("--case-limit", type=int, default=12)
    bakeoff.add_argument("--max-cost-usd", type=float, default=0.50)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = _config(args.project_root)
    if args.command == "doctor":
        raise SystemExit(asyncio.run(_doctor(config)))
    if args.command == "bootstrap-corpus":
        raise SystemExit(_bootstrap_corpus(config))
    if args.command == "corpus-audit":
        output = (
            config.document_context_path
            if args.output is None
            else args.output
            if args.output.is_absolute()
            else config.project_root / args.output
        )
        report = audit_corpus(config.project_root, output)
        _print(
            {
                "status": "saved",
                "output": str(output),
                "included_source_count": report["included_source_count"],
                "layout_candidate_count": len(report["layout_review_candidates"]),
                "extraction_flag_count": len(report["extraction_quality_flags"]),
            }
        )
        raise SystemExit(0)
    if args.command == "build-index":
        raise SystemExit(asyncio.run(_build_index(config)))
    if args.command == "generate-document-contexts":
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        raise SystemExit(asyncio.run(_generate_document_contexts(config, output)))
    if args.command in {"search", "ask"}:
        raise SystemExit(asyncio.run(_search_or_ask(config, args.question, args.command)))
    if args.command == "evaluate":
        gold = args.gold if args.gold.is_absolute() else config.project_root / args.gold
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        raise SystemExit(asyncio.run(_evaluate(config, gold, output, args.limit)))
    if args.command == "benchmark":
        dataset = (
            args.dataset if args.dataset.is_absolute() else config.project_root / args.dataset
        )
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        review_packet = (
            args.review_packet
            if args.review_packet.is_absolute()
            else config.project_root / args.review_packet
        )
        raise SystemExit(
            asyncio.run(
                _benchmark(
                    config,
                    dataset,
                    output,
                    review_packet,
                    args.split,
                    args.max_cost_usd,
                )
            )
        )
    if args.command == "benchmark-conversation":
        dataset = (
            args.dataset if args.dataset.is_absolute() else config.project_root / args.dataset
        )
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        review_packet = (
            args.review_packet
            if args.review_packet.is_absolute()
            else config.project_root / args.review_packet
        )
        raise SystemExit(
            asyncio.run(
                _conversation_benchmark(
                    config,
                    dataset,
                    output,
                    review_packet,
                    args.split,
                    args.max_cost_usd,
                    offline=args.offline,
                )
            )
        )
    if args.command == "tune-retrieval":
        dataset = (
            args.dataset if args.dataset.is_absolute() else config.project_root / args.dataset
        )
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        raise SystemExit(
            asyncio.run(_tune_retrieval(config, dataset, output, args.max_cost_usd))
        )
    if args.command == "compare-contextual-retrieval":
        dataset = (
            args.dataset if args.dataset.is_absolute() else config.project_root / args.dataset
        )
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        experiment_dir = (
            args.experiment_dir
            if args.experiment_dir.is_absolute()
            else config.project_root / args.experiment_dir
        )
        raise SystemExit(
            asyncio.run(_compare_contextual_retrieval(config, dataset, output, experiment_dir))
        )
    if args.command == "canary":
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        raise SystemExit(
            asyncio.run(
                _canary(
                    config,
                    args.question,
                    args.calls,
                    output,
                    args.max_cost_usd,
                )
            )
        )
    if args.command == "bakeoff-models":
        dataset = (
            args.dataset if args.dataset.is_absolute() else config.project_root / args.dataset
        )
        output = args.output if args.output.is_absolute() else config.project_root / args.output
        review_packet = (
            args.review_packet
            if args.review_packet.is_absolute()
            else config.project_root / args.review_packet
        )
        raise SystemExit(
            asyncio.run(
                _model_bakeoff(
                    config,
                    dataset,
                    output,
                    review_packet,
                    args.case_limit,
                    args.max_cost_usd,
                )
            )
        )
    if args.command == "serve":
        uvicorn.run(create_app(config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
