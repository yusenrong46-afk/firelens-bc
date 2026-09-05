# 02 — System Overview

The public product is a React/Vite client served beside a FastAPI application. FastAPI composes a versioned static corpus/index, a single OpenRouter provider boundary, three official live layers, deterministic request planning, and strict response publication.

| Component | Purpose | Input → output | Principal invariant |
| --- | --- | --- | --- |
| API composition | Build runtime, middleware, routes, live service, and frontend | configuration → FastAPI app | Production startup fails closed on required provider privacy preflight |
| Request understanding | Project a question/context into typed intent features | `QueryRequest` → typed intent | Interpretation does not itself authorize a tool |
| Agent plan | Bind exact route, mode, layers, geography, and tool arguments | request features → `AgentQueryPlan` | Only exact planned calls may execute |
| Official live | Fetch, validate, normalize, filter, and derive live records | authorized layer/scope → typed live result set | Layer failure cannot become authoritative zero |
| Static RAG | Plan static subrequest, retrieve, select evidence, generate/compile, validate | authorized static request → `AskResponse` | Support must be packet-bound; high-risk publication is deterministic or quote-only |
| Composition | Join authority-labelled live/static/boundary sections | authorized results → canonical response | Top-level answer and public claims must bind to structured inputs |
| Client | Submit bounded state and project the response into answer/map/evidence views | API contracts → UI state | UI must not strengthen backend authority |
| Evaluation | Exercise deterministic, provider, live, trajectory, and UI properties | candidate + bound datasets → artifacts | Dataset role and evaluated identity travel with every conclusion |

Detailed owners, failure modes, observability, tests, and evaluation families are centralized in the [module map appendix](appendices/module-map.md).

## Storage and external boundaries

- Static corpus and vector artifacts are local versioned files loaded by [`runtime.py`](../../src/firelens/runtime.py).
- OpenRouter is the configured model/embedding/reranking network boundary through [`providers/openrouter.py`](../../src/firelens/providers/openrouter.py).
- Official live records and BC geocoding are HTTP boundaries defined in [`live_support.py`](../../src/firelens/live_support.py).
- The browser keeps bounded session state; the public API does not implement accounts or long-term user memory.

