# FireLens v1.6 product rescue — Remaining Issues

Date: 2026-09-03

## A. “REVIEW” items from FireLens-200
Local campaign verdicts were deterministic (“FAIL: 0”), but the harness marked several cases for manual review:
* `FL200-146` (REVIEW)
* `FL200-171` (REVIEW)
* `FL200-172` (REVIEW)

These did not produce “hard failures” (the grader rubric over metadata + visible output did not accept a full match), so we should treat them as quality polish rather than broken contracts.

## B. Performance before/after not yet measured (remaining task)
We updated presentation logic and parsing rules; we should re-run:
* `make v1-6-performance`
* (and/or) `scripts/v1_6_round2_performance.py`

to quantify any latency or throughput regressions introduced by:
* clause/routing adjustments,
* stable selection + ordinal binding,
* and evidence/proof presentation changes.

## C. Deployment preview + production verification (pending)
Local gates are passing. Next is to:
* deploy the exact commit as a preview,
* run the Product Reality Gate against that preview URL,
* then run the same smoke checks against production.

This step may require Vercel authentication/permissions in the environment.

