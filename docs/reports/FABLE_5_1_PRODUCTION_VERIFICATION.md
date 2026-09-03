# FireLens v1.6 product rescue — Production Verification

Date: 2026-09-03

## What we verified locally
1. `make verify`: PASS
2. Product Reality Gate (browser + API):
   * `apps/web/tests/reality/product-reality.spec.ts`: 14/14 passed
3. Natural-language mutation set:
   * `data/evaluation/nl_mutation_set.v1.yaml`: 50/50 passed
4. Evaluation/contract gates (offline):
   * ClaimBench v2: 332/332 correct, `unsafe_false_accept_rate = 0.0`
   * Hard probe (offline, rc2.2): 93/105 passed; `minimum_passed_met = true`
   * Source-aware conversation: `passed = true`
   * FireLens-200 focused: PASS/REVIEW only; FAIL: 0

## Pending (requires deploy permissions)
* Preview deploy of the exact commit (`fable/firelens-product-rescue` → Vercel preview).
* Run Product Reality Gate against the preview deployment URL (via `FIRELENS_REALITY_URL`).
* Run the same smoke checks against production.
* If any “critical” checks fail, roll back to the recorded production deployment target.

Once Vercel credentials are available in this environment, we can run:
* `make vercel-preview`
* `make vercel-production`

