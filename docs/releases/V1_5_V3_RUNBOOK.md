# FireLens BC V1.5 V3 candidate runbook

This runbook prepares release `1.5.3-rc.1`. It does not replace independent
semantic, accessibility, safety, retrieval, or UX review.

## Candidate preflight

1. Confirm branch `codex/v1-5-v3`, the intended commit, and a clean worktree.
2. Run `make check`. Run the browser and qualification suites only with the
   required browser authorization and record their exact outputs.
3. Confirm the generated OpenAPI schema matches the frontend types.
4. Confirm `OPENROUTER_API_KEY` is present without printing it.
5. Set `FIRELENS_RELEASE_VERSION=1.5.3-rc.1` and the exact build commit.
6. Set `FIRELENS_REQUIRE_ZDR=true` for production and keep content tracing off.
7. Run the authenticated ZDR preflight for the configured embedding, rerank,
   and generation models. Do not deploy if any model is absent.
8. Verify the configured reranker passed the frozen retrieval regressions; a
   ZDR listing alone is not a quality qualification.

## Product checks

- The province map loads without asking for location.
- Selecting an incident or perimeter exposes status and distance tasks.
- An evacuation area never substitutes an unrelated fire for distance.
- Location is requested only to resume a task that actually needs an origin.
- Ordinary low-risk questions return reviewed guidance or labelled general
  background, while current and personalized safety requests remain bounded.
- Stale, partial, unavailable, and no-result states never imply safety.

## Promotion boundary

Create a preview from one committed candidate. Verify its readiness identity,
anonymous homepage, live map, grounded answer, labelled background answer,
selected-fire status, resumable distance, privacy probes, and rollback artifact.
Promote that exact artifact without rebuilding only after the required human
review and sealed benchmark gates pass.
