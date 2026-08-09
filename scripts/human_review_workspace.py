#!/usr/bin/env python3
"""Launch the tested human-review workspace package CLI."""

from __future__ import annotations

import sys

from firelens.review_workspace import cli

if __name__ == "__main__":
    raise SystemExit(cli.main())
else:
    sys.modules[__name__] = cli
