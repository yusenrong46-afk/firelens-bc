# Baseline

Status: clean pre-fix adapter baseline captured; canonical EvalLab envelope
`NOT_AVAILABLE` because EvalLab did not yet exist.

The pre-fix baseline was captured from exact commit
`ae975132c5d65800c1e960c7b6e0c46844959dfe`, tree
`c7952d897b09c2640cd0a2cc4313c925c32cd6ac`, before campaign behavior changes.
It is valid bound historical evidence, but it predates EvalLab and therefore is
not a normalized `firelens.eval_lab.run.v1` envelope.

| Evidence | Result | SHA-256 |
|---|---|---|
| [`raw/productbench_offline.json`](raw/productbench_offline.json) | ProductBench offline 31/31 | `c852643865fa32890c2b1fc556434789ca659daa7353d38b563ea66591a7648b` |
| [`raw/hard_probe_rc2_1.json`](raw/hard_probe_rc2_1.json) | Hard probe rc2.1 91/105; 86-case floor met; 14 mismatches | `10ffe98a15b9c00799d9db8487bc479e738e11d4d962f1e9e5cf53572bb3485f` |
| [`raw/source_aware_conversation.json`](raw/source_aware_conversation.json) | Source-aware 106/106 | `75dae4a889d3deed6528a3f8e414935ec3d9d4ff4fe0e6e09e2471ae6c699149` |
| [`raw/retrieval_dry_run.json`](raw/retrieval_dry_run.json) | Retrieval dry run `BLOCKED`; no spend; estimated paid maximum $14.4072 | `db850a14914779ace6589b80e8edf7629f17a43f4f569ee97a144ac477de08c9` |
| [`raw/performance_local_fake.json`](raw/performance_local_fake.json) | Fake/local, 100 measurements per route; p95 0.666–11.798 ms; zero generation calls | `e5a588106a96581877939e4b7e9284dc45ee001f45e16207b97a3d337a1f4c59` |

The untouched clean-checkout verification record also reports two backend
passes of 2,071 and 2,072 tests, Vitest 178/178, and Playwright 41 passed with
one expected skip. Baseline bundles were JS 546.86 kB (159.64 kB gzip) and CSS
79.46 kB (14.62 kB gzip); physical LOC were Python 76,953, TypeScript/TSX 8,526,
and CSS 3,276.

Separately, the clean pre-fix production/UI observation is retained in
`docs/product/FIRELENS_UI_AUDIT.md` and the
`docs/product/screenshots/production-baseline-*.png` artifacts. Those establish
the named deployment and observed UI state within their stated limits; this
directory does not erase or replace them.

These raw reports are retained in the repository so the baseline does not
depend on ephemeral host paths. The current dirty-local EvalLab diagnostic
must not be relabelled as the clean
pre-fix baseline. Conversely, the lack of a historical EvalLab envelope must
not be used to erase the manually captured baseline artifacts above.

Create a candidate only from a clean checkout:

```bash
PYTHONPATH=src:tests python -m firelens_eval run --suite core
```

Then retain the whole run directory, including raw artifacts, before using its
commit SHA with `compare`.
