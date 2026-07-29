# FireLens BC V1.5 release-candidate runbook

This runbook applies only to a clean `codex/v1-5-release` worktree reconstructed from
baseline `209b4e5f8f16f13d7ac9af56a89e135f697ce052`. It does not authorize a production
deployment.

Do not create that worktree while either the frozen retrieval report or owner semantic decision
is unqualified. The relevant lab artifacts are
`output/benchmark/v1_5_frozen_holdout_retrieval.json` and
`output/benchmark/v1_1_conversation_live_review.md`.

## Preflight

1. Confirm the release branch and clean worktree with `git status --porcelain=v2 --branch`.
2. Run `make verify`, then `git diff --exit-code` and `git diff --cached --exit-code`.
3. Run `make qualify-retrieval-v1-5`; require owner-approved labels and `qualified: true`.
4. Run `.venv/bin/python scripts/run_limitation_probe.py --max-cost-usd 1.25`; require a
   complete report and all defined safety/quality gates.
5. Run `make benchmark-v1-1-paid`; complete and approve the semantic review packet.
6. Run `make qualify-live-v1-5`; require all official layers, matching chat/map records, and
   cached p95 at or below four seconds.
7. Confirm `GET /api/v1/health/ready` reports the expected `release_version`, `build_commit`,
   corpus version, chunk count, provider readiness, and `rate_limit_scope=instance_local`.
8. Confirm the OpenRouter key is configured without printing it.

## Preview only

The CLI version verified for this runbook on 2026-07-28 is `58.1.0`:

```bash
npx vercel@58.1.0 deploy
```

Creating a preview is an external action and requires owner approval. Do not add `--prod`.
Record the preview URL, deployment ID, Git commit, environment target, and command output in the
release evidence ledger.

## Anonymous verification

From a logged-out browser and a separate HTTP client, verify:

- homepage delivery;
- liveness and readiness;
- one grounded static answer with exact evidence;
- one partial or unsupported answer;
- one supported live answer with source and retrieval timestamps;
- one mixed answer;
- map keyboard interaction on desktop and mobile;
- missing-location, no-result, partial-layer-failure, total-outage, 413, and 429 behavior.

An unchanged source timestamp is not an outage. A missing or invalid source timestamp is.
No-result language must not imply safety.

## Rate-limit boundary

The application guard is per warm instance and is deliberately reported that way. Before public
production approval, verify an outer Vercel Firewall or equivalent distributed rate limit for the
ask and live-map routes. Do not describe the in-process guard as a global quota.

## Rollback

If a preview fails, stop promotion and keep production on V1.1. If an approved production release
later regresses:

1. Use the Vercel dashboard to promote the previously verified V1.1 deployment.
2. Confirm the restored deployment ID and readiness build identity.
3. Re-run anonymous homepage, readiness, and grounded-answer checks.
4. Record the failing V1.5 deployment ID and failure evidence without deleting it.
5. Repair in the lab branch; do not patch production directly.
