# Appendix — Evaluation Catalog

Catalog sizes are not pass results. The tables/hashes below retain the Sol
baseline. Current Astra runs and the unchanged-application evaluator bridge are
in the [continuation packet](../../reports/ASTRA_CONTINUATION.md); exact
envelopes and native artifacts are retained outside Git.

| Evaluation | Dataset / expectation binding | Evaluator binding | Cases and role | Current evidence |
| --- | --- | --- | --- | --- |
| ProductBench v2 offline | catalog SHA-256 `e285fa6bdf5e3731d797f96fc5145929fc66e3d1c50b2cc947fa25d1a8676e9f` | `productbench_v2.py` SHA-256 `585abc43986f06310fae464d6957d5b948afab3a18acf5fdf7dd62f7775a4716` | 50 total; 31 offline-fake, 19 provider/manual; development-unsealed | **PASS 31/31** locally; not release proof |
| ClaimBench v2 | dataset SHA-256 `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557` | `claimbench_v2.py` SHA-256 `c14d77bc33376a13a14c333b51e348f87f72120e03c5b558bd5e3d30fb9bd7ad` | 332 rows: 86 faithful, 246 mutations | **PASS 332/332** locally; semantic completeness unproven |
| Hard probe RC2.2 offline | dataset SHA-256 `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035`; expectations SHA-256 `17d73575e894395df2b6193c62ebfdcffb2cd3b892b79e233fb99a0f22fd8904` | evaluator SHA-256 `3bec958bc350457b70cba1638320a6c8af8086495bab3bf0186a85529f040e48`; wrapper `342b7e3cd87ba4cf1bb5f222c8a6d3d4051fb85d54a40ffbca93c07cce865f35` | 105 cases; floor 86; not sealed | **FAIL 93/105**; 12 expectation mismatches, including 10 `CRITICAL` under review |
| Source-aware conversation v1 | dataset SHA-256 `029081a491018804e07b87d7826656f6d2bc4468a11b0b139a8f5aa060e6e32a` | evaluator SHA-256 `5de2a0c0ccb1c7c1d2239f045b78b786123a4208a07d9b2ff2eb60f4dc45fc8c` | 106 development-unsealed cases over fake/local dependencies | **PASS 106/106** locally; no provider/live qualification |
| Live fail-closed regressions | `tests/test_live.py` SHA-256 `a3d4b614090b21c1765037db26f7b5f90cf000f781884ced7a11c00eb4787aa5` | `src/firelens/live.py` SHA-256 `9fe0d03cfa05d610144faeef75b7191f521bbe04283bdd77b19719948612b5cd` | row, geometry, size, time, count, pagination, status, roster, and mixed-count contracts | Included in 122 live/safety/architecture passes plus 48 subtests |

## Historical Sol EvalLab binding

The clean local core result is **FAIL 562/574**: three adapters pass and hard
probe fails. Ten hard-probe mismatches are `CRITICAL`: `F06`, `F07`, `F09`,
`F10`, `H01`, `H02`, `H03`, `I04`, `K03`, and `K09`; the other mismatches are
`I08` and `L05`. Meeting 93/105 against the older floor does not waive them.
They remain evaluation-contract owner-review cases, not automatically confirmed
product defects.

The run uses no network/provider calls. The final envelope binds the clean
candidate SHA/tree, `changed_during_run=false`, aggregate EvalLab runner SHA-256
`9592fd2bc1e12a7f783e60725ff2f9b27aa70860ef03216148b6eeb959962b79`,
failure schema `21f13efbfb829a87e18117b7f9c9b2afa7f24690480b3f2d9360b8f4232f4afb`,
registry `f4c2f413d4dbed2380b21ac1af891b76a4c561a5050e0a6f87ef304eafd95b8c`,
and policy `b7589b38bc2811e7150c5ce5e42bdf5d27f395f70e58a591bf12f7490253a1b3`.
The checked-in [diagnostic pointer](../../../evals/eval_lab/core/CURRENT_DIAGNOSTIC.json)
is explicitly a superseded historical dirty-run record.

## Integrity and comparison

EvalLab blocks dirty and source-changing evidence. For eligible comparisons it
opens each envelope's own commit in a detached snapshot, validates it there,
replays all four core adapters, and refuses incompatible
policy/schema/dataset/evaluator bindings. Volatile vector-manifest self-hashes
are rejected. ProductBench's unauthenticatable random-trace-derived
`trace.response_sha256` is omitted, and a raw artifact that reintroduces it is
rejected.

## Astra local adapters and external gaps

- RAG/source: 30 executable local diagnostics; provider/sealed V3 qualification
  stays **BLOCKED**, separately from those assertions.
- Metamorphic: 14 executable cases; trajectory: three actual three-turn flows.
- Fault: 12 named existing fail-closed tests with native subtests; performance:
  six checks including 900 retained fake-provider loopback HTTP samples.
- UI: seven lifecycle tests, seven versioned current-interface journeys and
  19 unchanged legacy browser tests. Their results are separate; deployed
  candidate Product Reality stays **NOT_RUN**.
- FireLens-200: **UNPROVEN** as a release measure; the inspected judge is
  heuristic, fault cases are not run, and costs are absent.

Historical Pacific Clarity, Fable, Round 2/3, and V1.6.4 reports remain bound to
their recorded identities. They cannot qualify this candidate.
