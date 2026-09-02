"""Load the frozen V1.6.4 product-coherence case manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CASES_RELATIVE = Path("data/evaluation/v1_6_4_product_coherence/cases.yaml")


def load_product_coherence_cases(root: Path | None = None) -> dict[str, Any]:
    base = root or Path(__file__).resolve().parents[3]
    payload = yaml.safe_load((base / CASES_RELATIVE).read_text("utf-8"))
    if not isinstance(payload, dict) or payload.get("frozen") is not True:
        raise ValueError("product-coherence cases must be a frozen mapping")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) < 10:
        raise ValueError("product-coherence cases are incomplete")
    return payload
