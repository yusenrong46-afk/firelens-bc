#!/usr/bin/env python3
"""Write or evaluate the frozen ClaimBench v2 catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from firelens.evaluation.claimbench_v2 import (
    evaluate_v2_catalog,
    load_claimbench_v2,
    write_claimbench_v2,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClaimBench v2 freeze and evaluate")
    parser.add_argument("command", choices=("write", "evaluate"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "write":
        print(json.dumps(write_claimbench_v2(root), indent=2, sort_keys=True))
        return
    catalog = load_claimbench_v2(root)
    summary = evaluate_v2_catalog(catalog)
    summary.pop("rows")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
