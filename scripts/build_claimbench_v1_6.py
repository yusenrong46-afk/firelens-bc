#!/usr/bin/env python3
"""Write the frozen V1.6 ClaimBench catalog. Run once during patch group 3."""

from __future__ import annotations

from pathlib import Path

from firelens.evaluation.claimbench_catalog import write_claimbench


def main() -> None:
    write_claimbench(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
