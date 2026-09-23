# Map-first release v2

## Scope and identity

Starting candidate `f103afd0a76fdc63c2a79dac3e5d8303a458f84e`, original main
`ed2a7af26ceea0113619c8cdb72052a62e4d2903`, PR #83. This successor replaces
question-led Home with the selected map-first interface and repairs two reproduced
context-routing defects. The [v1 report](frontend-release-v1.md) is historical.
Implementation commits: `ef98bfe` (UI), `6a1559c` (backend).

Permitted backend changes are limited to `intent_conversation.py`,
`static_guidance_subject.py` and `request_facets.py`. They restore bare pet-supplies
follow-ups to actual kit history, prevent an explicit located live request from
inheriting weather context, and prevent personal pronouns becoming a contents
container. Independent pet activities remain independent. No source, model,
Python dependency or API contract changes are part of this release.

## Design review

Product Design screenshot audit: retain the map as the primary geographic surface,
keep explanatory text off tiles, and open Ask only when needed. At 1440×900 the
closed-panel canvas occupied 84% of the viewport in the local fixture capture.
Desktop Ask is anchored below the header; below 1024px it becomes a bottom-entry
dialog. Guidance uses a reading column; spatial answers use a 440px column beside
the map. The initial map load is intentional and makes no AI-provider request.

Independent review identified and corrected pending hidden-map fits, accidental
conversation reset during map navigation, missing initial location-denial feedback,
and pet-topic context overreach. Screenshots are fixture evidence, not live feeds.
Map opening, evidence, Copy and Why must preserve the immutable answer snapshot.

## Reproducible gates

```bash
PYTHONPATH=src:tests make verify
PYTHONPATH=src:tests make verify-candidate-browser
make docs-check
make productbench-deterministic
make source-aware-conversation
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite core
npm --prefix apps/web run test:surface
node apps/web/scripts/qualify-frontend-surface.mjs --protocol data/evaluation/frontend_surface.v3.yaml --output output/map-first-surface
```

Use Python 3.12 / Node 22 for CI and Node 24 with pinned `vercel@58.1.0` for
packaging. Serialize builds. The v3 surface protocol only changes idle readiness
from v2 and remains provisional. Neither completed measurements nor accepted
historical evaluator dispositions turn raw failures into passes.

The frozen 24-case bank is `tests/fixtures/release_context_regressions.v1.json`.
Compare identical inputs on main, starting and final candidates; report routing
and full source support separately from live-provider correctness. Measure the
existing ten routes with five warmups, 30 samples and three rotating repetitions;
20 fresh processes per version measure cold readiness. Investigate each >10% p95
regression without claiming speed from code size.

## Real-provider campaign

Successor bank: `tests/fixtures/frontend_release_smoke.v2.json`. Ten preview and
ten production targets plus at most four corrective submissions. Preserve the
prior nine submissions separately. Reserve durably before UI submission, count
uncertain dispatches, prevent duplicate entries, and use actual browser history.
Failed prerequisites block their dependants. Exact deployment origins and commit
identities must be pinned. Missing charges remain unknown; UI requests are not
provider-attempt counts. No dollar cap applies to this authorized campaign.

## Deployment and rollback

Existing project: `firelens-bc` (`prj_2aXvVXkFJZKAp5ReOAwDw5Kq5WTZ`),
team `team_AewB0gNEwKvTOeGFr3718mnG`, Node 24, `firelens-bc.vercel.app`.
Recheck Git settings without changing them. Do not merge until exact-candidate CI,
preview identity, assets and ten smoke cases pass. Bind the merge commit and track
any automatic deployment. If none occurs, stage production with pinned CLI
`deploy --prod --skip-domain`, the exact build/runtime commit and existing
`firelens_v1_6_2` benchmark identity. Validate then promote; never publish a local
macOS native bundle as a Linux runtime artifact.

On failed public verification, restore `dpl_EYCT2WNWw1WGTPQdgpTFUzzaeSQP` with
Vercel rollback, verify the public domain and prepare a Git revert of the merge.
Preserve environment values, firewall, protection and project identity.

## Decisions and completion

KEEP: selected map-first UI and bounded repairs if final gates pass.
REVERT: any package that introduces an unresolved authority/privacy/core-journey defect.
DEFER: experimental backend, source migration, broader 400-question qualification.

Final evidence must bind commit/tree, protected-file hashes, assets, runtime,
CI, preview/production identities, all smoke receipts and rollback target. Report
frontend quality, targeted backend correctness, production verification and broader
qualification separately. Until those receipts exist, release remains BLOCKED.
