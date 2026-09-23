# FireLens engineering map

Deterministic, offline navigation index for the current source content. It is not runtime, qualification, deployment, or release evidence. Source digest: `b34233de1afb1e422105315fb54580f95628d4c8e73af84e270fb51522bbdfb2`.

Inventory: 215 production Python modules, 69 production TS/TSX modules,
230 test modules, and 2273 resolved internal import edges.

Generate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py`; validate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py`.
Inspect impact with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>`; inspect a planning trace with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "<question>"`.
Traces redact question- and location-derived values unless `--include-question` is explicitly supplied. Impact also accepts semantic owner IDs such as `location_resolution`.

Machine-generated JSON owns structure and graph facts. Semantic YAML is serialized as YAML
from curated declarations in `impact.py`; ownership cannot be inferred from fan-in alone.
Major-symbol flags are heuristic, and `statically_unreferenced` is a lead rather than proof of
dead code because framework, CLI, and dynamic entry points may not have import edges.

Fix the first structured divergence and preserve separate release authority.
