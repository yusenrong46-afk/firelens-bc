# FireLens engineering map

Deterministic, offline navigation index for the current source content. It is not runtime, qualification, deployment, or release evidence. Source digest: `119660041925338764f52e32128080ad3c7beaca2e3486a72172083b560b2d70`.

Inventory: 212 production Python modules, 56 production TS/TSX modules,
200 test modules, and 2129 resolved internal import edges.

Generate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py`; validate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py`.
Inspect impact with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>`; inspect a planning trace with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "<question>"`.
Traces redact question- and location-derived values unless `--include-question` is explicitly supplied. Impact also accepts semantic owner IDs such as `location_resolution`.

Machine-generated JSON owns structure and graph facts. Semantic YAML is serialized as YAML
from curated declarations in `impact.py`; ownership cannot be inferred from fan-in alone.
Major-symbol flags are heuristic, and `statically_unreferenced` is a lead rather than proof of
dead code because framework, CLI, and dynamic entry points may not have import edges.

Fix the first structured divergence and preserve separate release authority.
