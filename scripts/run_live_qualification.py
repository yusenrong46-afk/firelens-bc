#!/usr/bin/env python3
"""Launch the tested live-qualification package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import live_qualification_cli

if __name__ == "__main__":
    live_qualification_cli.main()
else:
    sys.modules[__name__] = live_qualification_cli
