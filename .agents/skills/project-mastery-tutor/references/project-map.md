# FireLens BC project map

Snapshot basis: `main` at `b00544c1927ffa12d98689f6a4b0b44b6c7de7e1`, inspected while creating this skill. Refresh Git identity and lesson-relevant files before relying on these details.

## Product purpose

**OBSERVED** — `README.md:1-13` describes FireLens BC as an evidence-first conversational assistant for reviewed British Columbia wildfire-preparedness guidance. V1.5 adds bounded official incident, perimeter, and evacuation records plus a restrained map. Stable claims require exact local evidence; current records are separate and do not authorize personal safety decisions.

## Folder map

| Area | Responsibility | Start here |
|---|---|---|
| `src/firelens/` | Python package, contracts, runtime, API, evaluation | `runtime.py`, `api.py`, `contracts.py` |
| `src/firelens/ingestion/` | Acquire, parse, normalize, repair, and chunk source documents | `acquire.py`, `pdf.py`, `html.py`, `chunking.py`, `repairs.py` |
| `src/firelens/retrieval/` | BM25, vectors, fusion, reranking, text rendering | `bm25.py`, `vector.py`, `hybrid.py`, `pipeline.py` |
| `src/firelens/answering/` | Routing, planning, evidence packets, generation, validation | `intent.py`, `service.py`, `context.py`, `grounded.py`, `validate.py` |
| `src/firelens/providers/` | OpenRouter and fake provider boundary | `base.py`, `openrouter.py`, `fake.py` |
| `data/` | Source registry, processed corpus, vector index, evaluation datasets, repairs | `sources/source_registry.yaml`, `processed/`, `index/`, `evaluation/` |
| `prototype/firelens-rag-ui/` | React/Vite UI, generated API types, Leaflet map, tests | `src/App.tsx`, `src/api.ts`, `src/LiveMap.tsx` |
| `tests/` | Python unit, contract, safety, evaluation, live, reliability, and release tests | `test_static_rag.py`, `test_v1_5_rag.py`, `test_live.py` |
| `docs/` | Handbook, ADRs, learning notes, release and audit evidence | `TECHNICAL_HANDBOOK.md`, `adr/`, `learning/` |
| `scripts/` | Verification, qualification, review, security, packaging, and experiments | `run_hard_probe.py`, `qualify_preview.py`, review scripts |
| root deployment files | FastAPI entrypoint, Docker, Vercel, Render | `app.py`, `Dockerfile`, `vercel.json`, `render.yaml` |

## Entrypoints

- **Vercel/FastAPI:** `app.py:1-10` imports `create_app` and builds configuration from the repository root.
- **Application factory:** `src/firelens/api.py:55-95` creates FastAPI, live service, request guard, and lifespan state.
- **Runtime assembly:** `src/firelens/runtime.py:60-180` loads and validates corpus/index resources, creates the provider and retrieval pipeline, then creates `StaticRAGService`.
- **CLI:** `src/firelens/cli.py` exposes `firelens` commands declared in `pyproject.toml`.
- **Local server:** `Makefile:42-45` builds the frontend and runs `firelens serve`; the UI and `/api/v1` share one origin.

## Main integrations and boundaries

- OpenRouter supplies planning, embeddings, reranking, and structured generation; configuration and provider behavior are in `src/firelens/config.py` and `src/firelens/providers/openrouter.py`.
- Official live data uses injected ArcGIS layer definitions and a BC geocoder in `src/firelens/live.py:58-198`; chat and map share `LiveDataService`.
- The frontend calls `/api/v1/ask` through `prototype/firelens-rag-ui/src/api.ts:1-44` and renders claims, evidence, modes, limitations, and the lazy `LiveMap` in `App.tsx`.
- `vercel.json` deploys `app:app`; `Dockerfile` builds the frontend then installs the locked Python runtime; `render.yaml` describes a Docker web service.

## Recommended reading order

1. `README.md:1-44` and `73-152` — product boundary and response modes.
2. `src/firelens/contracts.py` — typed request, plan, retrieval, evidence, response, and health shapes.
3. `src/firelens/api.py` and `src/firelens/runtime.py` — startup and HTTP lifecycle.
4. `src/firelens/answering/intent.py` and `answering/service.py` — routing and orchestration.
5. `src/firelens/retrieval/pipeline.py`, `answering/context.py`, `answering/grounded.py`, `answering/validate.py` — RAG path.
6. `src/firelens/live.py` and `live_answering.py` — current-data path.
7. `prototype/firelens-rag-ui/src/App.tsx` and `LiveMap.tsx` — presentation and state.
8. `tests/` and `src/firelens/benchmark.py` — what is actually measured.
9. `docs/TECHNICAL_HANDBOOK.md`, ADRs, release reports, and deployment files — rationale and operational limits.
