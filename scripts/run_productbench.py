#!/usr/bin/env python3
"""Run the hash-bound ProductBench v2 evaluation."""

from __future__ import annotations

import sys

from firelens.evaluation import productbench_v2

if __name__ == "__main__":
    raise SystemExit(productbench_v2.main())
else:
    sys.modules[__name__] = productbench_v2
