# FireLens BC V1.5 execution state

Updated: 2026-07-28 (America/Vancouver)

## Repository truth

- Canonical checkout: `/Users/thomas/Downloads/firelens-bc 2`
- Canonical branch/commit: `improvement/rag-webapp-v2` at `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- Canonical state: tracked-clean with 25 user-owned untracked files; read-only for this task
- Lab checkout: `/Users/thomas/Downloads/firelens-bc-v1-5-lab`
- Lab branch/commit: `codex/v1-5-lab` at `7e776918f65573e82928f4e2a412c175cfaf864e`
- Release branch: `codex/v1-5-release` at the V1.1 baseline; no release worktree yet
- Main and production: unchanged

## Current milestone

Repair the existing lab candidate before qualification. Active hypotheses:

1. Mixed answers must keep the user's actual question and preserve live partial-failure metadata.
2. Live source timestamps must come from a genuine record modification or ArcGIS layer edit time,
   never ignition or event-start time.
3. Unsupported live domains such as roads and air quality must fail honestly instead of querying
   unrelated wildfire layers.

## Executed evidence in this goal

- `make verify` at `7e77691`: 115 Python tests passed, 10 skipped, 36 subtests;
  12 frontend unit tests; production build; 4 Sites tests; 12 Playwright flows.
- Generated OpenAPI and TypeScript types left the tracked worktree clean.
- Public ArcGIS metadata inspected for all three layers. Each exposes a layer
  `editingInfo.dataLastEditDate`; only evacuation records expose a direct `DATE_MODIFIED` field.

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
- Operational rate limits, V1.5 identity, preview verification, and rollback documentation are incomplete.
- Release branch reconstruction has not started.

## Next action

Repair live intent, timestamp, mixed-response, and partial-failure contracts with targeted tests.

Next verification command:

`./.venv/bin/python -m pytest -q tests/test_live.py tests/test_v1_5_rag.py`
