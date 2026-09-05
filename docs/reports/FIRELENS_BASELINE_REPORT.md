# FireLens baseline report

Clean pre-fix adapter baseline: `CAPTURED` at exact commit
`ae975132c5d65800c1e960c7b6e0c46844959dfe`, tree
`c7952d897b09c2640cd0a2cc4313c925c32cd6ac`.

Canonical EvalLab envelope: `NOT_AVAILABLE` for that historical baseline,
because the capture occurred before EvalLab existed. This does not invalidate
or erase the bound raw artifacts.

## Clean pre-fix adapter baseline

| Adapter or gate | Bound result | Artifact SHA-256 |
|---|---|---|
| ProductBench offline | 31/31, fake provider, $0 | [`evals/eval_lab/baseline/raw/productbench_offline.json`](../../evals/eval_lab/baseline/raw/productbench_offline.json) — `c852643865fa32890c2b1fc556434789ca659daa7353d38b563ea66591a7648b` |
| Hard probe | rc2.1, 91/105, declared 86-case floor met, 14 mismatches, $0 | [`evals/eval_lab/baseline/raw/hard_probe_rc2_1.json`](../../evals/eval_lab/baseline/raw/hard_probe_rc2_1.json) — `10ffe98a15b9c00799d9db8487bc479e738e11d4d962f1e9e5cf53572bb3485f` |
| Source-aware conversation | 106/106; zero external network/model calls | [`evals/eval_lab/baseline/raw/source_aware_conversation.json`](../../evals/eval_lab/baseline/raw/source_aware_conversation.json) — `75dae4a889d3deed6528a3f8e414935ec3d9d4ff4fe0e6e09e2471ae6c699149` |
| Retrieval qualification dry run | `BLOCKED`; no spend; paid execution not authorized; estimated maximum $14.4072 | [`evals/eval_lab/baseline/raw/retrieval_dry_run.json`](../../evals/eval_lab/baseline/raw/retrieval_dry_run.json) — `db850a14914779ace6589b80e8edf7629f17a43f4f569ee97a144ac477de08c9` |
| Performance | Executed fake/local; 100 measurements per route; route p95 range 0.666–11.798 ms; zero generation calls | [`evals/eval_lab/baseline/raw/performance_local_fake.json`](../../evals/eval_lab/baseline/raw/performance_local_fake.json) — `e5a588106a96581877939e4b7e9284dc45ee001f45e16207b97a3d337a1f4c59` |

The untouched clean-checkout `make verify` record reports two backend passes of
2,071 and 2,072 tests, Vitest 178/178, and Playwright 41 passed with one expected
skip. These are local deterministic/fixture gates, not provider or production
qualification.

Baseline build and size measurements:

| Measure | Pre-fix baseline |
|---|---:|
| Main JavaScript | 546.86 kB; 159.64 kB gzip |
| Main CSS | 79.46 kB; 14.62 kB gzip |
| Python physical LOC | 76,953 |
| TypeScript/TSX physical LOC | 8,526 |
| CSS physical LOC | 3,276 |

## Separately retained production/UI observation

The production/UI observation and its report remain at
`docs/product/FIRELENS_UI_AUDIT.md` and
`docs/product/screenshots/production-baseline-*.png`. They bind a named deployed
baseline and observed UI behavior within that report's limits. They are not an
EvalLab core run, candidate-equivalence proof, or full production qualification.

## Dirty-local EvalLab diagnostic

The campaign checkout is dirty and shared with concurrent implementation work.
EvalLab ran a zero-cost diagnostic against a stable observed dirty-path/status
fingerprint. This historical compact pointer predates content-bound dirty
application identity and cannot be retrofitted; it is diagnostic only and
cannot be promoted to a baseline, candidate qualification, deployment result,
or release decision. The compact binding record is
`evals/eval_lab/core/CURRENT_DIAGNOSTIC.json`; the complete raw artifact remains
ephemeral and is identified by hashes there.

The diagnostic executed 574 cases: ProductBench offline passed 31/31,
ClaimBench v2 passed 332/332, source-aware conversation passed 106/106, and the
hard probe pinned to rc2.2 reported 12 evaluation-contract mismatches in 105
rows. Ten were labelled `CRITICAL`: `F06`, `F07`, `F09`, `F10`, `H01`, `H02`,
`H03`, `I04`, `K03`, and `K09`. The other mismatches were `I08` and `L05`.
EvalLab therefore reported `FAIL`; the legacy 86-case aggregate floor does not
waive the critical gate. Case records remain in `review` with suspected
expectation-contract ownership and do not by themselves assert production
defects.

The pre-fix capture remains incomplete for full qualification: focused
FireLens-200 execution, paid/current RAG evidence, standalone metamorphic and
trajectory oracles, a typed fault matrix, authorized full browser/UI runs,
fleet-grade performance, and provider-call/token/cost receipts remain absent or
blocked. Those gaps limit the baseline; they do not make the captured evidence
nonexistent.
