# FireLens BC V1 Evidence Ledger

Status: candidate implemented; not release-qualified
Date: 2026-07-26
Environment: macOS 26.4.1, Python 3.14.5, Node 25.9.0, npm 11.12.1

## Gate ledger

| Gate | Result | Status |
|---|---|---|
| Git and secret boundary | baseline `fba00d9`; tracked scan clean | complete |
| Versioned backend/reliability | strict contracts, retries, atomic writes, retention | complete |
| Corpus audit | 8 reviewed sources, 180 chunks, one visual repair | complete for current corpus |
| Retrieval configuration | four locked candidates compared on development | complete; current retained |
| Benchmark execution | 100/100 cases completed, no provider error | complete |
| Safety/red-team | route and status 20/20 | pass |
| Citation and quote structure | 100% / 100% on accepted drafts | pass |
| Reranker Recall@5 | 81.82% versus 95% gate | fail |
| Variability | 30/30 one status, no reason variance | pass |
| Frontend | unit, accessibility, desktop/mobile, real local UI | pass |
| Semantic owner review | 20 high-risk plus 10 ordinary cases | pending |
| Final `make verify` | all Python/UI checks and builds passed | complete |

## Executed evidence

| Command or check | Result | What it proves | What it does not prove |
|---|---:|---|---|
| `.venv/bin/pytest -q` | 69 passed, 3 paid skipped | offline Python behavior | live provider availability |
| Ruff and mypy | clean | formatting/lint/type contracts | runtime semantics |
| Frontend component/accessibility | 5/5 | answer, abstention, retry, idle/evidence accessibility | real provider behavior |
| Playwright desktop/mobile | 6/6 | answer, citation, keyboard abstention, unavailable/retry | public deployment |
| `make benchmark` | 20/20 route/status, $0 | deterministic safety routing | answer quality |
| `make benchmark-retrieval` | current retained; $0.4500 | locked dev comparison at Recall@5 | label correctness |
| `make benchmark-live` | 100 cases; $0.2444 | end-to-end execution and metrics | semantic support |
| `make canary` | 30/30 stable; $0.1284 | repeated structural/status stability | truth/completeness |
| `make model-bakeoff` | 3 models, 9 shared packets; $0.0576 | identical-packet structural comparison | semantic model winner |
| Real local browser | answer, evidence, abstention, mobile, no console errors | integrated UI/API flow | public deployment |

The first canary exposed invalid passage IDs used as quote IDs. A packet-specific
quote-ID enum and clearer prompt fixed the invariant; the repeated 30-call run
then passed. This is reproduced evidence of a caught and corrected defect, not a
claim that generation is generally deterministic.

## Latest benchmark measures

| Measure | Result |
|---|---:|
| Route accuracy | 99% |
| Development / holdout / red-team status accuracy | 86.67% / 70% / 100% |
| Safety route/status accuracy | 100% / 100% |
| Abstention precision / recall | 70.83% / 100% |
| BM25 / dense / fused Recall@20 | 83.33% / 84.85% / 84.85% |
| Reranker Recall@5 / MRR@5 / nDCG@5 | 81.82% / 66.46% / 69.53% |
| Citation ID / exact quote validity | 100% / 100% |
| Validation rejection rate | 1% |
| Provider error rate | 0% |
| Answer latency p50 / p95 | 1.85 s / 3.14 s |
| Tokens | 212,997 prompt; 15,290 completion; 228,287 total |
| Full benchmark cost | $0.2444 |
| Canary plus full benchmark | $0.3728, below $2 |

`literal_forbidden_phrase_hit_count=9` is a literal-string diagnostic, not a
semantic forbidden-claim judgment; false-premise corrections can repeat a
forbidden phrase safely. Required-claim coverage, unsupported claims, and human
claim-to-evidence support remain unscored pending review.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| Benchmark dataset | `75414daede41d029ecb233b380053546c279eb4ed33a201c19a5ceb5d2e6afef` |
| Sealed holdout projection | `d16eb54a8a9d88d27db776db83171d555a90cd8bdc971ce436349cbc238420fe` |
| Corpus JSONL | `a6a26b22c45b1a17e286f38fb2af45b5d4baaf70f6c4c729243668b1355caa2f` |
| Corpus manifest | `ddeabeedc13778c1247d57be2c1e97d6e1cb311e672fa8e21d5f401e7f2821b3` |
| Vector matrix | `9762a252462e9a626b02a596a9714f34650c8e6ae3d6b9edc6ed28f2e1d9f09a` |
| Vector manifest | `d3bd912031b1715d1375c2418d485e19f15b0a62dad367eb6dbe77ccb89074fd` |
| Full benchmark report | `dfea22afeb5a2b34e1a8d6bbb1816ff31d0731e1708323d0a8f52646a101b7c0` |
| 30-call canary | `6ad5c798c786f26234846c4ebb6c8bded97b4a9e7b9357fd6d026bd6ad32c26f` |
| Retrieval comparison | `4384648e71808ebe7ecd29c1071041cdfba0a7f9ae584ed6c39cd8cf833bfa4d` |
| Model bake-off | `92b008f4a4db1e3b3add561e40d88ef9312eae1846c70903ca853ae92ca1bf21` |

Generated reports and provider traces stay local under ignored `output/` paths;
this ledger stores their measured summaries and hashes without question text.

## Release boundary

The architecture and frontend are implemented, but the hard Recall@5 gate and
owner semantic review are open. The only accurate label is `candidate
implemented; not release-qualified`. Do not call V1 released, semantically
accepted, or production-ready.
