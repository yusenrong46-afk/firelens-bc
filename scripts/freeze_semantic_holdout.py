#!/usr/bin/env python3
"""Launch the tested semantic-holdout freeze package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import semantic_holdout_freeze_cli

if __name__ == "__main__":
    raise SystemExit(semantic_holdout_freeze_cli.main())
else:
    sys.modules[__name__] = semantic_holdout_freeze_cli
