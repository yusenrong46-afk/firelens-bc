# Learning path and mastery checkpoints

Teach one lesson at a time. Use the prerequisite and mastery checks; do not advance because the user can repeat terminology.

## Level 0 — Product mental model

Lessons: purpose and non-goals; stable evidence versus current live records; response modes; one complete question flow.

Mastery: the user can explain what FireLens answers, what it refuses, and why a current incident is not a static citation.

## Level 1 — Repository navigation

Lessons: root folders; `app.py`; `firelens` CLI; `api.py`; `runtime.py`; frontend `App.tsx`; tests and docs.

Exercise: locate the entrypoint, API route, service class, corpus file, vector manifest, and one test for a chosen behavior.

Mastery: the user can find the code path for a feature without asking Codex to search the whole repository.

## Level 2 — Project programming foundations

Teach only concepts present in the chosen path: Python packages, classes, dataclasses, Pydantic models, enums, type hints, async/await, exceptions, protocols, serialization, HTTP, environment configuration, and dependency injection.

Mastery: the user predicts a small typed object, identifies a boundary, and explains why an async call or exception path exists.

## Level 3 — Components and data flow

Lessons: contracts; runtime assembly; `StaticRAGService`; provider protocol; retrieval/evidence/generation interfaces; traces and operation logs.

Exercise: trace one `QueryRequest` through `execute_search` and name each transformation.

Mastery: the user distinguishes data, control flow, state, and authority at module boundaries.

## Level 4 — RAG and model pipeline

Sequence: ingestion → chunking → metadata → BM25 → embeddings/vector search → RRF → reranking → evidence packet → structured prompt → validation → public citations.

For every algorithm: intuition, tiny numeric example, formula if useful, repository symbol, rationale, limitation, and alternative. Use `technical-glossary.md` and `architecture-and-data-flow.md`.

Mastery: the user can calculate a two-document RRF example, explain why reranker scores are not citations, and identify where evidence becomes authoritative.

## Level 5 — APIs, backend, frontend, runtime

Lessons: request/response schemas; middleware; deadlines and body limits; health/readiness; frontend state; generated API types; map/chat parity; failure rendering.

Mastery: the user can describe a request from browser event to rendered claim/evidence panel and name at least two failure responses.

## Level 6 — Testing and evaluation

Lessons: unit/property tests; fake providers; contract/OpenAPI tests; browser tests; retrieval metrics; conversation benchmarks; hard probes; owner semantic review; cost/latency; what automated checks cannot prove.

Mastery: the user can state what a test protects, what it does not prove, and why exact quote identity is not semantic entailment.

## Level 7 — Deployment, security, operations

Lessons: locked setup; Docker/Vercel/Render; secrets; CSP; request guard; provider retries; freshness/cache; logs/traces; readiness; rollback and release evidence.

Mastery: the user can identify which controls are local defense-in-depth versus externally enforced production controls.

## Level 8 — Architecture judgment

Lessons: authority boundaries; cohesion/coupling; hard-coded policy; experiment isolation; failure modes; scaling and cost; refactoring seams; redesign alternatives.

Mastery: the user can defend one design choice with repository evidence, name a tradeoff, propose an experiment, and define a regression gate.

## Recommended sequence

Start with Levels 0–1. Then use one complete grounded question as the spine for Levels 2–6. Add the live path at Level 5, operations at Level 7, and architecture judgment only after the user can independently trace and test the current system.
