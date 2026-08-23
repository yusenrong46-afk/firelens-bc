# FireLens V1.6 state

Kept under 300 lines. Update after every patch group.

## Starting identity

- Repository: `/Users/thomas/Downloads/firelens-bc 2`
- Starting commit: `3de745a22ad0801e19563f90ac64f18609ecae03`
- Working branch: `upgrade/v1-6` (local only; do not push)
- Package: `1.5.3rc1` / release `1.5.3-rc.1` (not bumped)

## Current patch group

W7 — Qualification. Final local report:
`docs/reports/V1_6_FINAL_ENGINEERING_REPORT.md`. Verdict `NOT_PROVEN`.

## Completed

- W0 freeze + seal (`c247a3bd`)
- W1 route budgets / pure-static fast path (`98e32ae`)
- W2 adaptive retrieval behind `adaptive_v1` (`5ff2d5d`)
- W3 additive claim-trust and frozen ClaimBench (`0f2819f`)
- W4 typed failures, ops ledger, Source Change Radar, packaging (`2a5d523`)
- W5 proof-carrying UX (`b269c52`)
- W6 loop/test split, ARCHITECTURE_V1_6, ADR 0013, golden traces (`1f5c2f5`)
- W7 local qualification (this commit):
  - `make verify` passed (855 pytest, 47 vitest, 26 e2e)
  - ClaimBench 200/200
  - offline hard probe 82/105 (not coerced)
  - package logical parity passed; staged inventories BLOCKED
  - H10 left EXTERNAL

## Blockers

- H4 sealed 46/47: EXTERNAL
- H4 paired adaptive ranking: BLOCKED
- H8 paid p95/cost: EXTERNAL
- H10: EXTERNAL
- `service.py` and `contracts.py` remain written size exceptions

## Residual risks

- Adaptive retrieval stays opt-in until H4+H8
- Hard probe still fails D10/K04 mode contracts and several FakeProvider
  related-route background cases
- Do not retune ClaimBench or FL-V16-S1 thresholds
- Do not mutate frozen V1.5.2 catalogs

## Next exact action

Stop. Do not push. Do not declare release GO. Further work needs explicit
authorization (paid, human, preview, firewall, sealed 46/47, or a version bump
to `1.6.0-rc.1` before a new qualification).
