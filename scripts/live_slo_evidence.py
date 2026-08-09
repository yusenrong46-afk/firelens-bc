#!/usr/bin/env python3
"""Launch the tested live-SLO evidence package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import live_slo_evidence_cli

if __name__ == "__main__":
    live_slo_evidence_cli.main()
else:
    sys.modules[__name__] = live_slo_evidence_cli
