# Frontend release on the existing backend

## Scope

This release ports the question-led Home, reading layouts, evidence/Copy/Why,
responsive maps, refresh and selection improvements onto GitHub main
`ed2a7af26ceea0113619c8cdb72052a62e4d2903`. Backend implementation, models,
approved sources, corpus/index and public contracts remain unchanged. Experimental
backend repairs and source migration are deferred. This is not renewed source
currency approval or broad answer-quality qualification.

## Verification

Run `make verify`, `make verify-candidate-browser`, `make docs-check`,
`make productbench-deterministic`, `make source-aware-conversation`, and EvalLab
core. The current UI successor is `playwright.product.config.ts`; the original
`tests/e2e/app.spec.ts` remains historical evidence. The current built-stack lane
adds `fullstack-product-v2.spec.ts`, `atlas-readiness.spec.ts`, and
`basemap-transport.spec.ts`. Preserve failure assertions and privacy thresholds.

The frontend surface v2 protocol preserves the v1 obligations and remains
provisional. Complete measurements are not formal qualification.

The frozen ten-question release smoke is in
`tests/fixtures/frontend_release_smoke.v1.json`. Use actual browser conversation
history, review prerequisites, and reserve every target before submitting.
Ten preview plus ten production submissions and four corrective submissions are
the maximum. Provider charges absent from responses remain unknown; account
balance changes are not attempt receipts.

## Deployment and rollback

Existing project: `firelens-bc` (`prj_2aXvVXkFJZKAp5ReOAwDw5Kq5WTZ`),
team `team_AewB0gNEwKvTOeGFr3718mnG`, Node 24, existing production domain
`firelens-bc.vercel.app`. Current settings have no linked Git repository; merging
does not deploy. Recheck before release.

After local and CI gates, verify the preview and merge the frontend-only PR.
Bind the merged commit using the existing deploy wrapper with
`firelens_v1_6_2` benchmark identity and existing environment configuration.
Use pinned `vercel@58.1.0` to stage production with `--prod --skip-domain`,
verify the production-environment artifact, then promote that deployment.
Do not change models, secrets, firewall or deployment protection.

Rollback target: `dpl_EYCT2WNWw1WGTPQdgpTFUzzaeSQP`. On a new production
regression, restore this deployment with Vercel rollback, verify the public domain,
and prepare a Git revert of the frontend merge. Never force-reset main.

Release evidence must bind backend file hashes, final commit/tree, served assets,
CI, preview/production IDs, browser results, and any unresolved limitations.
