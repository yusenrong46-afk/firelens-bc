#!/usr/bin/env python3
"""Integrate confirmed V1.6 human decisions into the typed inventory."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import yaml

from firelens.answering.claim_integration import build_integrated_inventory

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=ROOT / "data/typed_claims/high_risk_v1.yaml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs/reports/V1_6_RC_INTEGRATION_MANIFEST.json",
    )
    args = parser.parse_args()
    inventory, manifest = build_integrated_inventory(ROOT)
    rendered = yaml.safe_dump(inventory, sort_keys=False, allow_unicode=True)
    manifest["integrated_inventory_sha256"] = sha256(rendered.encode("utf-8")).hexdigest()
    args.inventory.write_text(rendered, encoding="utf-8")
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
