#!/usr/bin/env python3
"""Launch the tested preview-qualification package CLI."""

from __future__ import annotations

import sys

from firelens.evaluation import preview_qualification_cli

if __name__ == "__main__":
    preview_qualification_cli.main()
else:
    sys.modules[__name__] = preview_qualification_cli
