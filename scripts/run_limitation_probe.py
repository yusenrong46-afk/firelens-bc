#!/usr/bin/env python3
"""Launch the tested limitation-probe package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import limitation_cli

if __name__ == "__main__":
    limitation_cli.main()
else:
    sys.modules[__name__] = limitation_cli
