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
6. Set the stage privacy policy for preview and production:
   `FIRELENS_EMBEDDING_ZDR=required`, `FIRELENS_GENERATION_ZDR=required`,
   `FIRELENS_RERANKING_ZDR=optional`, `FIRELENS_DATA_COLLECTION=deny`,
   `FIRELENS_ALLOW_FALLBACKS=false`. Keep content tracing off. Bind the same
   embedding, rerank, and generation model IDs in the environment that the v3
   runtime candidate document records. `FIRELENS_REQUIRE_ZDR=true` remains a
   migration shim for the approved mix (rerank optional). Local `make run` may
   use optional ZDR stages and is not a production-qualified artifact.
7. Run the authenticated ZDR preflight for embedding and generation. Do not
   deploy if either required model is absent. Cohere reranking may be absent
   from the ZDR roster under the approved exception. Confirm OpenRouter account
   prompt logging is disabled.
8. Confirm the configured reranker is still the retained retrieval-qualified
   `cohere/rerank-4-pro`. A ZDR listing alone is not a quality qualification.
   Qwen remains unqualified and must not replace Cohere. FireLens does not
   claim universal ZDR or a privacy certification.

## Local, preview, and production evidence

| Surface | What it proves | What it does not prove |
| --- | --- | --- |
| Local `make check` / `make verify` | Engineering regressions on this worktree | Deployed identity, ZDR roster, or human review |
| Preview deployment | One HTTPS origin built from the bound candidate | Production traffic, firewall proof, or UX qualification |
| Production | Fail-closed embedding/generation ZDR, deny-collection, no fallback, and the exact candidate artifact | Semantic, accessibility, safety, UX, or privacy certification |

Zero-cost identity/ZDR/partial-layer gates (do not deploy; point at an
authorized origin). Qualification requires HTTP 200 and `status: ready` from
`GET /api/v1/health/ready`, plus a full match of candidate ID, candidate SHA-256,
commit, release, corpus, embedding, rerank, generation, and retrieval-text
strategy as observed on that endpoint. A 503/`not_ready` origin is not qualified.

`--include-ask-probes` posts one safety Ask and expects
`reason_code=personalized_safety_decision`. That probe is paid on a live
provider. Do not add it without an explicit cost authorization.

```bash
.venv/bin/python scripts/qualify_deployment_gates.py \
  --base-url https://PREVIEW_URL \
  --candidate config/runtime_candidate.v1.json \
  --expect-production
```

Localhost rehearsal only (identity/map; not production-mode unless the
process was started as production):

```bash
.venv/bin/python scripts/qualify_deployment_gates.py \
  --base-url http://127.0.0.1:8000 \
  --candidate config/runtime_candidate.v1.json \
  --allow-http
```

Local production-mode rehearsal (zero-cost; no Ask probe):

```bash
.venv/bin/python scripts/qualify_deployment_gates.py \
  --base-url http://127.0.0.1:8000 \
  --candidate config/runtime_candidate.v1.json \
  --expect-production \
  --allow-http
```

`--include-ask-probes` posts one safety Ask (`personalized_safety_decision`)
and is paid on a live provider. Do not add it without an explicit cost
authorization.

Paid comparison of a *different* reranker remains blocked until authorized.
Cohere Rerank 4 Pro remains the retained retrieval-qualified reranker; Qwen
must not replace it. A later V3 sealed holdout is a separate owner-authorized
gate, not a current Cohere-unqualified finding. Smallest existing retrieval-only
ceilings:

- Development comparison, max `$1.25`:
  `FIRELENS_RERANK_MODEL=<zdr-candidate> make benchmark-retrieval-v1-5`
- Frozen holdout after owner review, max `$0.75`, three repetitions:
  `FIRELENS_RERANK_MODEL=<zdr-candidate> make qualify-retrieval-v1-5`

Promotion requires the frozen Recall@5 threshold on the sealed holdout. Do not
edit labels or thresholds. Do not promote from a ZDR roster listing.

Rollback proof must retain candidate and restored artifact SHA-256 values plus
environment snapshots that include models and the stage privacy policy
(`data_collection`, `allow_fallbacks`, `require_parameters`, `embedding_zdr`,
`reranking_zdr`, `generation_zdr`).

Human review launch commands are in
`docs/audit/V1_5_V3_HUMAN_REVIEW_HANDOFF.md`. Grok cannot act as a reviewer.

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
