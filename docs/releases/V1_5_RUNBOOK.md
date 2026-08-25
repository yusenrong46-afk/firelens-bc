# FireLens BC V1.5 release-candidate runbook

This runbook applies only to a clean `release/v1.5` worktree reconstructed from
baseline `209b4e5f8f16f13d7ac9af56a89e135f697ce052`. It does not authorize a production
deployment.

Do not create that worktree while either the frozen retrieval report or owner semantic decision
is unqualified. The relevant lab artifacts are
`output/benchmark/v1_5_frozen_holdout_retrieval.json` and
`output/benchmark/v1_1_conversation_live_review.md`.

## Preflight

1. Confirm the release branch and clean worktree with `git status --porcelain=v2 --branch`.
2. Run `make verify`, then `git diff --exit-code` and `git diff --cached --exit-code`.
3. Run `make retrieval-review-packet` and review all 47 cases against the included original corpus
   passages. Run `make retrieval-review-template`, record the owner decisions in the hash-bound
   YAML sidecar,
   then run `make qualify-retrieval-review`. Only after it reports `qualified: true`, run
   `make qualify-retrieval-v1-5` exactly once without tuning; require all three repetitions to
   reach at least 46/47 Recall@5. A miss requires a new versioned experiment and a newly frozen
   holdout, never case-specific tuning against this sealed set.
4. Run `.venv/bin/python scripts/run_limitation_probe.py --max-cost-usd 1.25`; require a
   complete report and all defined safety/quality gates.
5. Run `make benchmark-v1-1-paid`, then `make owner-review-template`. Review the generated
   Markdown packet and benchmark report, and record decisions in the generated hash-bound YAML
   sidecar without changing its report hash. Run `make qualify-owner-review` and require
   `qualified: true`, a live-provider report, all 50 expected cases approved, zero unsupported
   verified claims, and zero unclear claims. The template command refuses to overwrite an
   existing owner review.
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

Build the preview from the qualified release commit, verify that exact deployment, and promote
that deployment rather than rebuilding production. Run the executable anonymous HTTP gate with:

```bash
.venv/bin/python scripts/qualify_preview.py \
  --base-url https://PREVIEW_URL \
  --expected-version 1.5.0-rc.1 \
  --expected-commit FULL_RELEASE_COMMIT \
  --raw-evidence-output /absolute/private/v1_5_preview_raw.json
```

This writes a compact machine-readable report to
`output/qualification/v1_5_preview.json` and a non-overwriting 0600 private raw-response artifact
at the supplied path. The compact report hash-binds that private artifact so response-body digests
can be recomputed without retaining response bodies in the report. It does not claim browser
accessibility, forced source failure, or firewall enforcement; those remain separately recorded
gates.

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

The application ignores ordinary `X-Forwarded-For` input. On a deployment explicitly identified
as Vercel, it accepts only Vercel's platform-overwritten `x-vercel-forwarded-for` value and still
hashes that address with an ephemeral process secret. Confirm this behavior in preview before
using per-client observations as evidence. Vercel documents the platform-overwritten request
headers at <https://examples.vercel.com/docs/headers/request-headers>.

`make prepare-firewall` validates `config/vercel_firewall.v1.json` and renders pinned Vercel CLI
commands without executing them. The two method-scoped IP rules use an enforced deny action at
150 ask requests/minute and 300 map requests/minute. These are conservative initial thresholds,
not proven capacity limits. In an owner-approved preview, observe at least 24 hours, inspect false
positives and regional traffic, then adjust through a separate reviewed change if evidence requires
it. The owner publishes all firewall changes; repository tooling never publishes automatically.

Vercel's rate-limit action becomes a distributed control only after the rendered rule is published
and verified on the target deployment. A committed deny plan is preparation, not deployment
evidence. See <https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting>.

## Rollback

If a preview fails, stop promotion and keep production on V1.1. If an approved production release
later regresses:

1. Use the Vercel dashboard to promote the previously verified V1.1 deployment.
2. Confirm the restored deployment ID and readiness build identity.
3. Re-run anonymous homepage, readiness, and grounded-answer checks.
4. Record the failing V1.5 deployment ID and failure evidence without deleting it.
5. Repair in the lab branch; do not patch production directly.

Preview verification and rollback rehearsal must name deployment IDs. Never repair by creating a
new unverified production build; promote the previously verified deployment artifact.
