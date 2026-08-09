#!/usr/bin/env python3
"""Launch the tested candidate-evidence package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import candidate_evidence_cli

if __name__ == "__main__":
    raise SystemExit(candidate_evidence_cli.main())
else:
    sys.modules[__name__] = candidate_evidence_cli
