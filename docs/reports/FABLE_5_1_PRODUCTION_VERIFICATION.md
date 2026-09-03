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

## Deploy + Reality Gate verification (Vercel)
* Preview:
  * URL: https://firelens-gxw0zii31-yusenrong46-9212s-projects.vercel.app
  * Product Reality Gate: PASS (14/14)
* Production:
  * URL: https://firelens-apmj87f1p-yusenrong46-9212s-projects.vercel.app
  * (Aliased as `https://firelens-bc.vercel.app`)
  * Product Reality Gate: PASS (14/14)

