# FireLens BC V1.5 execution state

Updated: 2026-07-28 (America/Vancouver)

## Repository truth

- Canonical checkout: `/Users/thomas/Downloads/firelens-bc 2`
- Canonical branch/commit: `improvement/rag-webapp-v2` at `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- Canonical state: tracked-clean with 25 user-owned untracked files; read-only for this task
- Lab checkout: `/Users/thomas/Downloads/firelens-bc-v1-5-lab`
- Lab branch/commit before the current operational patch: `codex/v1-5-lab` at
  `fba79cc806b4968f26c685d379dcb0f782289115`
- Release branch: `codex/v1-5-release` at the V1.1 baseline; no release worktree yet
- Main and production: unchanged

## Current milestone

Complete operational safeguards and then qualify the repaired lab candidate.

The live/mixed hypotheses were confirmed and repaired in `fba79cc`.

## Executed evidence in this goal

- `make verify` at `7e77691`: 115 Python tests passed, 10 skipped, 36 subtests;
  12 frontend unit tests; production build; 4 Sites tests; 12 Playwright flows.
- Generated OpenAPI and TypeScript types left the tracked worktree clean.
- Public ArcGIS metadata inspected for all three layers. Each exposes a layer
  `editingInfo.dataLastEditDate`; only evacuation records expose a direct `DATE_MODIFIED` field.
- `fba79cc`: 33 targeted backend tests and 14 subtests, 12 frontend unit tests, production
  build/typecheck, 12 desktop/mobile Playwright flows, mypy, Ruff, and formatting passed.
- Operational safeguard patch: 25 request-guard/provider/live tests and 37 reliability/invariant
  tests with 22 subtests passed; frontend tests and production build passed.

## Candidate and experiment state

- Current production retrieval candidate: `metadata_context_v1`, BM25/vector/fused 30/30/30,
  RRF 60, rerank 5.
- `document_context_v2`: excluded unless a controlled rerun clears its promotion gate.
- GraphRAG: excluded; no qualified real graph run exists.
- Paid cost in this goal: `$0.00`.

## Known blockers and remaining gates

- Existing relevance addendum is development evidence, not a sealed owner-adjudicated holdout.
- Semantic claim support/completeness remains pending a valid release review surface.
- Cached-live p95 and concurrency are unmeasured.
- Distributed production throttling still requires Vercel Firewall verification; the application
  correctly reports its own guard as instance-local.
- Release branch reconstruction has not started.

## Next action

Run the complete lab verification, inspect the generated diff, and commit the operational milestone.

Next verification command:

`make verify && git diff --check`
