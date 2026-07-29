# FireLens BC V1.5 execution state

Updated: 2026-07-28 (America/Vancouver)

## Repository truth

- Canonical checkout: `/Users/thomas/Downloads/firelens-bc 2`
- Canonical branch/commit: `improvement/rag-webapp-v2` at `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- Canonical state: tracked-clean with 25 user-owned untracked files; read-only for this task
- Lab checkout: `/Users/thomas/Downloads/firelens-bc-v1-5-lab`
- Lab branch/commit: `codex/v1-5-lab` at
  `6903c86cb1325b63638a3b373063f8231e987aa5`
- Release branch: `codex/v1-5-release` at the V1.1 baseline; no release worktree yet
- Main and production: unchanged

## Current milestone

Qualify the repaired lab candidate, beginning with independently valid retrieval and
semantic-review evidence.

Live/mixed hardening is in `fba79cc`, operational safeguards are in `ade480e`, and the
conflict/corpus-admission trust boundary is in `6903c86`.

## Executed evidence in this goal

- `make verify` at `7e77691`: 115 Python tests passed, 10 skipped, 36 subtests;
  12 frontend unit tests; production build; 4 Sites tests; 12 Playwright flows.
- Generated OpenAPI and TypeScript types left the tracked worktree clean.
- Public ArcGIS metadata inspected for all three layers. Each exposes a layer
  `editingInfo.dataLastEditDate`; only evacuation records expose a direct `DATE_MODIFIED` field.
- `fba79cc`: 33 targeted backend tests and 14 subtests, 12 frontend unit tests, production
  build/typecheck, 12 desktop/mobile Playwright flows, mypy, Ruff, and formatting passed.
- `make verify` at `6903c86` content: secret scan, generated OpenAPI/types, Ruff, formatting,
  mypy over 48 source files, 129 Python tests, 10 skipped, 36 subtests, 12 frontend tests,
  production build, 4 Sites tests, and 12 desktop/mobile Playwright flows passed.
- A bounded live OpenRouter calibration passed all 10 poison-source cases and all 3 conflict
  cases. The malicious source was quarantined before retrieval; all conflict answers used the
  explicit `conflict` response state with two exact sources. Cost: `$0.02845812`.

## Candidate and experiment state

- Current production retrieval candidate: `metadata_context_v1`, BM25/vector/fused 30/30/30,
  RRF 60, rerank 5.
- `document_context_v2`: excluded unless a controlled rerun clears its promotion gate.
- GraphRAG: excluded; no qualified real graph run exists.
- Paid cost in this goal: `$0.02845812`.

## Known blockers and remaining gates

- Existing relevance addendum is development evidence, not a sealed owner-adjudicated holdout.
- Exact citation completeness and a deterministic claim-to-quote lexical support floor are now
  enforced. Full semantic entailment remains pending owner review of the release packet.
- Cached-live p95 and concurrency are unmeasured.
- Distributed production throttling still requires Vercel Firewall verification; the application
  correctly reports its own guard as instance-local.
- Release branch reconstruction has not started.

## Next action

Freeze a non-circular qualification manifest, execute the independently frozen holdout and
paid-cost-instrumented limitation probe, and generate the final semantic review packet.

Next verification command:

`make benchmark-v1-1-paid`
