#!/usr/bin/env python3
"""Run the hash-bound ProductBench v2 evaluation.

`--refresh-manifest` re-binds the unsealed manifest to the current raw catalog
and to the executable contracts derived from the product's own deterministic
parser. A parser change legitimately changes those hashes; the manifest is a
snapshot, not a seal, and is rewritten here rather than hand-edited. The runner
itself refuses to execute against a stale manifest.
"""

from __future__ import annotations

import sys

from firelens.evaluation import productbench_v2 as pb
from firelens.evaluation import productbench_v2_identity as identity


def refresh_manifest() -> dict[str, object]:
    catalog = identity.load_raw_catalog(pb.CATALOG_PATH)
    contract_rows = pb.contracts(catalog["cases"])
    manifest = identity.rewrite_manifest(
        manifest_path=pb.MANIFEST_PATH,
        catalog=catalog,
        contract_rows=contract_rows,
        raw_catalog_sha256=pb.file_sha256(pb.CATALOG_PATH),
        contract_sha256=pb.canonical_sha256(contract_rows),
        executable_catalog_schema=pb.EXECUTABLE_CATALOG_SCHEMA,
        executable_catalog_sha256=pb.canonical_sha256(
            pb.executable_catalog_payload(catalog, contract_rows)
        ),
        tiers=[pb.OFFLINE_TIER, pb.PROVIDER_TIER],
    )
    pb.load_catalog_and_manifest()
    return manifest


def main(argv: list[str]) -> int:
    if argv == ["--refresh-manifest"]:
        manifest = refresh_manifest()
        print(f"refreshed {pb.MANIFEST_PATH} contract_sha256={manifest['contract_sha256']}")
        return 0
    return pb.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
else:
    sys.modules[__name__] = pb
