# FireLens V1.6 Round-2 state

Kept under 300 lines.

## Starting identity

- Round-1 examined candidate: `6f038b4cacc2204be2da0147240143ecfbde3c96`
- Immutable local ref: `examined/v1-6-round1`
- Frozen V1.5 baseline: `3de745a22ad0801e19563f90ac64f18609ecae03`
- Working branch: `upgrade/v1-6-qualification-round2` (local only; do not push)
- Package now: `1.6.0rc1` / `1.6.0-rc.1`
- Standard FL-V16-S1 sha256: `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef`
- ClaimBench v1 sha256: `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1`
- ClaimBench v2 sha256: `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557`
- Hard probe dataset sha256: `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035`
- Fable 5 Round-1 verdict: `NOT_PROVEN` / `CONDITIONAL_NO_GO`

## Current patch group

Patch Group 7 complete. Final identity commit pending when this file is committed.

## Files changed this group

- Version bump to `1.6.0rc1` / `1.6.0-rc.1` (pyproject, web, OpenAPI, Dockerfile, render, config)
- `src/firelens/answering/intent_patterns.py` (intent.py ≤650)
- Gate hard-probe floor 86/105
- `docs/reports/V1_6_ROUND2_ENGINEERING_REPORT.md`

## Tests red/green

- `make verify` green (872 pytest, 47 vitest, 26 e2e)
- `make v1-6-round2-gate` green
- ClaimBench v1 200/200, v2 332/332
- Hard probe 86/105
- Retrieval provider metrics BLOCKED
- Adaptive default remains baseline

## Benchmark status

- ClaimBench v2 frozen and passing
- Hard probe no paired regression (78 → 82 → 86)
- Adaptive retrieval: dry-run only; keep experimental and disabled
- Representative generate-call reduction 41.7%

## Paid/external authorization state

- Paid retrieval: BLOCKED
- Sealed 46/47: EXTERNAL
- Preview/firewall/rollback/human AT: EXTERNAL
- Docker image inspect: BLOCKED

## Residual risks

- Independent examiner mutations remain necessary
- Do not retune FL-V16-S1 or the frozen 105-case probe
- Do not enable `adaptive_v1` without paid + sealed evidence
- Staged Docker/Vercel inventories unexecuted

## Rollback reference

```text
git switch examined/v1-6-round1
```

## Next exact action

No further code after the identity commit. Independent Fable 5 re-examination only.
