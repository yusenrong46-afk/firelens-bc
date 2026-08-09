#!/usr/bin/env python3
"""Launch the tested FireLens V1.5-2 benchmark CLI package."""

from __future__ import annotations

import sys

from firelens.evaluation import upgrade_cli

if __name__ == "__main__":
    upgrade_cli.main()
else:
    # Preserve the historical import path while keeping this executable thin.
    sys.modules[__name__] = upgrade_cli
