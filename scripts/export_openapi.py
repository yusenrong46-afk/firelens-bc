"""Export the versioned FastAPI schema without starting provider clients."""

from __future__ import annotations

import json
from pathlib import Path

from firelens.api import create_app
from firelens.config import DEFAULT_RELEASE_VERSION, FireLensConfig
from firelens.storage import atomic_text_writer


def build_export_config(root: Path) -> FireLensConfig:
    """Build a reproducible schema config independent of local runtime overrides."""

    return FireLensConfig.from_env(root).model_copy(
        update={
            "frontend_dist_path": None,
            "release_version": DEFAULT_RELEASE_VERSION,
        }
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = build_export_config(root)
    schema = create_app(config).openapi()
    output = root / "docs/openapi.v1.json"
    with atomic_text_writer(output) as stream:
        stream.write(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
