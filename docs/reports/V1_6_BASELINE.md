# FireLens V1.6 before baseline

Status: Stage 0 freeze. This report records the V1.5 starting point. It is not
an after-implementation scorecard.

## Identity

- Starting commit: `3de745a22ad0801e19563f90ac64f18609ecae03`
- Branch at freeze: `upgrade/v1-6` created from `main` / `codex/v1-5-v3`
- Package: `1.5.3rc1`
- Release label: `1.5.3-rc.1`
- Standard: `FL-V16-S1` at `data/evaluation/firelens_v1_6_upgrade_standard.yaml`
- Machine snapshot: `output/benchmark/v1_6/before/snapshot.json`
- Tracked seal: `data/evaluation/firelens_v1_6_before_snapshot_seal.json`

Exact hashes from the Stage 0 capture:

- Standard SHA-256: `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef`
- Before snapshot SHA-256: `670cbe65c36964e299e74eafd0d1b679c3f25e90cd51ba3d03d02e524f263c20`
- Environment: Darwin 25.4.0 arm64, CPython 3.14.5, Node v25.9.0
- `src/firelens/agent/loop.py`: 459 lines
- `tests/test_upgrade_benchmark.py`: 5468 lines
- Public-agent `except Exception` sites: present in `src/firelens/agent/loop.py`

Do not edit the standard, thresholds, or seal after implementation results are observed.

## Hypothesis status at freeze (INSPECTED)

1. Pure-static discarded outer write: REPRODUCED
2. Broad `except Exception` in the public agent path: REPRODUCED
3. Stale technical handbook: REPRODUCED
4. Unqualified “verified” wording: REPRODUCED
5. Packaging parity: PARTIALLY_REPRODUCED
6. Oversized modules and upgrade benchmark test: REPRODUCED
7. Qualification evidence distinct from local engineering: REPRODUCED

## Measurements

Stage 0 captures identity, environment, module sizes, and the public-agent
`except Exception` inventory. Full `make verify`, offline hard probe, frontend
surface, ClaimBench, sealed retrieval, and paid/human/preview/firewall gates
remain null, BLOCKED, or EXTERNAL until executed. Missing values are not
written as zero or pass.

## Commands

```bash
make v1-6-baseline
make v1-6-gate
make v1-6-report
make v1-6-package-verify
```
