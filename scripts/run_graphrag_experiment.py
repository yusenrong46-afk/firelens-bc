#!/usr/bin/env python3
"""Prepare the isolated GraphRAG workspace; never alters the production index."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from firelens.config import FireLensConfig
from firelens.graphrag_experiment import prepare_graphrag_workspace
from firelens.runtime import load_corpus_resources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/experiments/graphrag"))
    parser.add_argument("--require-cli", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = FireLensConfig.from_env(root)
    chunks, _version = load_corpus_resources(config)
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    manifest = prepare_graphrag_workspace(
        chunks, output_dir=output_dir, openrouter_base_url=config.openrouter_base_url
    )
    cli = shutil.which("graphrag")
    status = {
        **manifest,
        "graphrag_cli": cli,
        "status": "ready_for_isolated_index" if cli else "excluded_dependency_missing",
        "next_command": (f"graphrag index --root {output_dir}" if cli else None),
    }
    print(json.dumps(status, indent=2, sort_keys=True))
    if args.require_cli and cli is None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
