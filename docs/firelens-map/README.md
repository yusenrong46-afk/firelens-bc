# FireLens engineering map

Deterministic, offline navigation index for the current source content. It is not runtime, qualification, deployment, or release evidence. Source digest: `ffe4aa1d0d085f02468b7ab83ecb63268623f057bba53cf4cecfc7a60c60f926`.

Inventory: 212 production Python modules, 56 production TS/TSX modules,
200 test modules, and 2119 resolved internal import edges.

Generate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py`; validate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py`.
Inspect impact with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>`; inspect a planning trace with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "<question>"`.
Traces redact question- and location-derived values unless `--include-question` is explicitly supplied. Impact also accepts semantic owner IDs such as `location_resolution`.

Machine-generated JSON owns structure and graph facts. Semantic YAML is serialized as YAML
from curated declarations in `impact.py`; ownership cannot be inferred from fan-in alone.
Major-symbol flags are heuristic, and `statically_unreferenced` is a lead rather than proof of
dead code because framework, CLI, and dynamic entry points may not have import edges.

Fix the first structured divergence and preserve separate release authority.
