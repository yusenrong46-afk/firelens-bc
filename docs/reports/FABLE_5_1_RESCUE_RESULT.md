# FireLens v1.6 product rescue (FABLE 5.1) — Result

Date: 2026-09-03
Branch: `fable/firelens-product-rescue`
Code commit: `681ff72`

## What we changed (high signal)
* Evidence-first UX: answer first, then inline “where it comes from” and “official sources”; map/records appear only when useful.
* Authority rails: high-risk questions that cannot be published as exact reviewed wording are handed off without pretending to know (no invented structured claims).
* Stable live binding:
  * Stable record selection uses deterministic IDs (prevents “second one” mis-binding).
  * Ordinal follow-ups now bind the same record the composer counts.
* Honest product scope:
  * Unrelated first-turn requests (e.g. non-wildfire topics) get a scoped note; wildfire questions stay in scope.
  * Definition questions (“what does X mean?”) are not treated as record-focused anaphora.
* Live presentation correctness:
  * Distance wording names the bound place (not the generic “place you asked about”).
  * Status-filtered counts bind to record-derived status.

## Gate results (local)
* `make verify`: PASS
  * Backend tests (non-browser): PASS
  * Frontend tests (vitest/fixtures): PASS
  * E2E fixture suite (`tests/e2e/app.spec.ts`): PASS (41 passed; 1 skipped in fixture mode)
* Product Reality Gate (browser + API, local run):
  * `apps/web/tests/reality/product-reality.spec.ts`: 14/14 passed
* Natural-language mutation set (NL mutation, local):
  * `data/evaluation/nl_mutation_set.v1.yaml`: 50/50 passed
* ClaimBench v2 (offline):
  * 332/332 correct
  * `unsafe_false_accept_rate = 0.0`
* Hard probe (offline, rc2.2 profile):
  * executed: 105
  * passed: 93
  * failed: 12
  * `minimum_passed_met = true`
* Source-aware conversation (offline):
  * `passed = true`

## FireLens-200 focused campaign (local)
* `run_firelens200_focused.py` (69 cases total)
  * PASS: 62
  * REVIEW: 7
  * FAIL: 0

## Complexity deltas
Key backend complexity metrics (baseline → after):
* `backend.python_loc`: 75,352 → 76,887
* `backend.functions`: 2,060 → 2,146
* `backend.modules`: 270 → 284

## Summary judgment
The rescue is “good enough for purpose” on product behaviour gates: ordinary wildfire questions resolve to live official records, evidence is visible and correctly attributed, and the authority/safety boundary behaviour is consistent.

