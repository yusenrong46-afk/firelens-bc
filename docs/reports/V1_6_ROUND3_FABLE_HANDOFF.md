# FireLens V1.6 Round-3 Fable handoff

Examine this candidate without inspecting sealed labels, running paid
retrieval, pushing, or deploying.

Round 2 improved engineering but failed fresh semantic adversarial testing.
Round 3 introduces risk-tiered typed claims and deterministic rendering.
Visible development benchmarks are not independent proof.

## Identity

```text
git switch upgrade/v1-6-semantic-round3
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --short
```

Rollback:

```text
git switch examined/v1-6-round2
git rev-parse HEAD
# expected: 40cabcb9a3a42888474d4de1a622ca84a3fd49b3
```

## Frozen hashes to confirm

```text
shasum -a 256 \
  data/evaluation/firelens_v1_6_upgrade_standard.yaml \
  data/evaluation/claimbench_v1_6.yaml \
  data/evaluation/claimbench_v1_6_2.yaml \
  data/evaluation/hard_probe.v1.yaml
```

Expected:

- FL-V16-S1 `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef`
- ClaimBench v1 `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1`
- ClaimBench v2 `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557`
- Hard probe `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035`

## Development suites (not independent proof)

```text
PYTHONPATH=src:tests .venv/bin/python scripts/v1_6_round3_eval.py --output-dir /tmp/v16r3-fable
.venv/bin/python -m pytest -q \
  tests/test_round3_semantic_adversary.py \
  tests/test_round3_full_path_invariants.py \
  tests/test_typed_claim_inventory.py \
  tests/test_claimbench_v1_6.py \
  tests/test_claimbench_v2.py \
  tests/test_critical_fields.py
PYTHONPATH=src .venv/bin/python scripts/run_hard_probe.py --mode offline \
  --output /tmp/v16r3-fable/hard_probe.json
```

Row-level development outputs: `docs/reports/V1_6_ROUND3_DEVELOPMENT_EVAL.json`.

## Zero-cost verification

```text
make verify
make v1-6-package-verify
```

## Performance (representative, not fleet)

Do not overwrite Round-2 tracked reports. Measure into `/tmp`:

```text
PYTHONPATH=src .venv/bin/python scripts/v1_6_round2_performance.py \
  --measure-only --root "$(pwd)" \
  --routes-json /tmp/v16r3-fable/routes.json \
  --warmup 10 --measured 30 \
  --output /tmp/v16r3-fable/performance_current.json --label current
```

## Do not run

- paid retrieval / H4
- sealed-label inspection
- push or deploy
- frontend redesign
