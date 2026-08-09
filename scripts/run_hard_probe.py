#!/usr/bin/env python3
"""Launch the tested hard-probe package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import hard_probe_cli

if __name__ == "__main__":
    raise SystemExit(hard_probe_cli.main())
else:
    sys.modules[__name__] = hard_probe_cli
