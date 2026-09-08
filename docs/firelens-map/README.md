# FireLens engineering map

Deterministic, offline navigation index for the current source content. It is not runtime, qualification, deployment, or release evidence. Source digest: `27b7939a30bb3111c5107211b14c3b6345fa6506c4341df1139b3e41c45938c9`.

Inventory: 215 production Python modules, 56 production TS/TSX modules,
204 test modules, and 2161 resolved internal import edges.

Generate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py`; validate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py`.
Inspect impact with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>`; inspect a planning trace with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "<question>"`.
Traces redact question- and location-derived values unless `--include-question` is explicitly supplied. Impact also accepts semantic owner IDs such as `location_resolution`.

Machine-generated JSON owns structure and graph facts. Semantic YAML is serialized as YAML
from curated declarations in `impact.py`; ownership cannot be inferred from fan-in alone.
Major-symbol flags are heuristic, and `statically_unreferenced` is a lead rather than proof of
dead code because framework, CLI, and dynamic entry points may not have import edges.

Fix the first structured divergence and preserve separate release authority.
