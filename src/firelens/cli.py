"""One command surface for setup checks, indexing, search, answers, and serving."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import uvicorn

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import QueryRequest, ResponseStatus
from firelens.providers.openrouter import OpenRouterProvider
from firelens.rag_evaluate import run_diagnostic
from firelens.retrieval.embeddings import build_vector_index
from firelens.runtime import load_corpus_resources, load_runtime


def _config(project_root: Path) -> FireLensConfig:
    return FireLensConfig.from_env(project_root.resolve())


def _print(payload) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


async def _build_index(config: FireLensConfig) -> int:
    chunks, corpus_version = load_corpus_resources(config)
    manifest = await build_vector_index(
        chunks,
        corpus_version=corpus_version,
        config=config,
        provider=OpenRouterProvider(config),
    )
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


async def _search_or_ask(config: FireLensConfig, question: str, command: str) -> int:
    runtime = load_runtime(config)
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


async def _evaluate(
    config: FireLensConfig, gold: Path, output: Path, limit: int | None
) -> int:
    runtime = load_runtime(config)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FireLens BC static RAG")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check corpus, index, and provider readiness")
    commands.add_parser("build-index", help="Build or update the OpenRouter embedding index")
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
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = _config(args.project_root)
    if args.command == "doctor":
        runtime = load_runtime(config)
        _print(runtime.health())
        raise SystemExit(0 if runtime.health().status == "ready" else 1)
    if args.command == "build-index":
        raise SystemExit(asyncio.run(_build_index(config)))
    if args.command in {"search", "ask"}:
        raise SystemExit(asyncio.run(_search_or_ask(config, args.question, args.command)))
    if args.command == "evaluate":
        gold = args.gold if args.gold.is_absolute() else config.project_root / args.gold
        output = (
            args.output if args.output.is_absolute() else config.project_root / args.output
        )
        raise SystemExit(asyncio.run(_evaluate(config, gold, output, args.limit)))
    if args.command == "serve":
        uvicorn.run(create_app(config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
