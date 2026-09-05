# FireLens EvalLab v1

## Purpose

EvalLab is the canonical adapter layer for FireLens evaluation evidence. It
does not replace suite-owned datasets or oracles. It gives existing evaluators
one command surface, verifies their important identities and counts, retains
their raw reports, and writes a normalized fail-closed envelope.

EvalLab v1 is zero-cost and denies external network/provider access. Explicit
local browser adapters use loopback servers. Results are engineering evidence,
not provider, live-feed, sealed-label, human, deployment, or release qualification.

## Commands

```bash
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval inventory
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite core
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite rag
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval diagnose PB-04
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval compare BASE_SHA CANDIDATE_SHA
```

`run` accepts `core`, `rag`, `metamorphic`, `trajectory`, `fault`, `ui`, and
`performance`. An unimplemented, unsafe, provider-backed, browser-dependent,
or incomplete suite emits `BLOCKED` or `NOT_RUN`; it never receives a synthetic
pass. Versioned local diagnostics now execute all six non-core families where
fixtures suffice; missing external qualifications remain separate adapters.

`data/evaluation/astra_local_diagnostics.v1.json` binds exact case rosters and
test/fixture material paths. Local adapters retain native pytest events or
browser JSON, reconcile failures and counts, and preserve logs and browser
artifacts. The accessible diagnostic labels are provisional. Native-result
reconciliation is not an independent semantic judge or secure attestation.
Changes to an evaluator require a same-evaluator bridge comparison, not relaxed
identity equality. Original frozen expectations and red reports stay intact.

The default artifact root is `output/eval_lab/`. A caller may give an exact
run directory with `--output-dir`. `diagnose` and `compare` search normalized
envelopes below that root by default; `--artifacts` can select another artifact
directory or one `envelope.json`. Comparison selects `core` unless `--suite`
names another suite.

## Core suite

The core suite executes these existing runners:

| Adapter | Existing authority | Required invariant |
|---|---|---|
| `productbench_offline` | ProductBench v2 offline | Exactly 31 manifest-bound cases, zero failures, fake provider, zero cost |
| `claimbench_v2` | ClaimBench v2 | Exactly 332 raw rows, recomputed correctness, zero unsafe accepts/rejects, no mass abstention |
| `hard_probe_rc2_2` | Permanent hard probe | Exact rc2.2 profile and hashes, all 105 rows, declared 86-case floor, zero-cost offline boundary, no failed `CRITICAL` case |
| `source_aware_conversation` | Source-aware conversation | All 106 cases, registered thresholds, zero external/model and Tier A/B generation calls |

The hard probe retains its frozen rc2.2 aggregate threshold, but EvalLab adds a
fail-closed disposition: any failed row labelled `CRITICAL` fails the adapter.
Every failing row is emitted as a failure record so `diagnose` and `compare`
cannot hide it. The aggregate score is not authority to waive a critical safety
finding.

ClaimBench is validated from its raw rows. Submitted summary fields cannot make
an incorrect row pass. ClaimBench v1 is not rerun because v2 contains the v1
catalog; historical v1 views should be derived from the v2 evidence.

## Artifact contract

Every run writes:

- `envelope.json`: normalized run identity, adapter outcomes, counts, metrics,
  material bindings, limitations, and failures;
- `failure_records.jsonl`: one record for each case failure, report-contract
  failure, blocker, or intentionally unexecuted adapter;
- `report.md`: human-readable summary;
- `raw/*.json`: unchanged or lossless reports from executed suite owners;
- `raw/*.stdout.log`: captured child-runner console output where the owner emits it.

The failure-record schema is
`evals/eval_lab/schema/failure_record.schema.json`. The envelope binds the exact
Git commit/tree, a content digest of tracked diffs and untracked bytes, imported
FireLens module path, registry, policy, EvalLab source files, failure schema, and
suite-owned material identities. On a clean tree, `application_sha` is the exact
commit; on a dirty diagnostic it is a 64-character digest bound to both the base
revision and working-tree content.

Each FailureRecord separates execution disposition (`run_status`: `FAIL`,
`BLOCKED`, or `NOT_RUN`) from investigation lifecycle (`status`:
`confirmed_fail`, `review`, `fixed`, or `cannot_reproduce`). A complete
evaluator/gate failure may start as `confirmed_fail`; unavailable or unexecuted
evidence starts in `review`. A hard-probe row whose observed mode differs from
the pinned profile still fails `run_status`, including the critical-case gate,
but starts in `review` with suspected ownership in the evaluation contract.
That mismatch alone does not prove a production defect or product-layer first
divergence. Every record includes `fixed_in_sha`; it remains `null` until the
lifecycle is `fixed`. A `fixed` record requires either an exact 40-character
candidate SHA or a 64-character working-tree digest. Dirty, unbound work stays
in `review` rather than claiming a fix. Records include
`first_divergence.layer`, `owner`, and `confidence`,
the full pipeline slots, application/dataset/evaluator hashes, and explicit
provider, embedding, rerank, and judge model/prompt identities. Unused model
fields are `null`; EvalLab never invents a model identity.

An artifact from a dirty tree remains diagnostically useful but is ineligible
for `PASS`, comparison, or qualification and adds an identity blocker. A
complete executed oracle failure may still make the aggregate diagnostic
`FAIL` under known-failure precedence. Commit or tree changes require a new
run. Historical artifacts do not qualify a changed candidate. EvalLab captures
the working-tree content again after execution and blocks evidence if bytes
changed during the run, even when the same paths remain modified.

The campaign's confirmed starting and production regressions are retained in
`evals/eval_lab/core/campaign_failure_records.jsonl`. A local repair does not
change their lifecycle to `fixed`; that requires an exact committed or
content-bound candidate identity and a passing rerun.

## Status and exits

| Status | Meaning | Exit |
|---|---|---:|
| `PASS` | Every required adapter executed and its registered oracle passed on a clean identity | 0 |
| `FAIL` | Complete executed evidence proves an oracle failure | 1 |
| `BLOCKED` | Required identity, material, runner, or evidence is missing or unsafe | 2 |
| `NOT_RUN` | Adapter is inventoried but intentionally not executed | 2 |

Known failure beats incomplete evidence in the aggregate disposition; otherwise
`BLOCKED` and `NOT_RUN` cannot be promoted to pass.

## Registry and policy

- `data/evaluation/eval_lab_registry.v1.yaml` owns suite/adapter inventory,
  exact commands, classifications, source materials, and explicit blockers.
- `data/evaluation/eval_lab_policy.v1.yaml` owns zero-cost policy, core adapter
  requirements, counts, thresholds, and fail-closed rules.

Neither file is a substitute for frozen expected-answer catalogs. EvalLab must
not expose ProductBench manifest refresh, ClaimBench catalog writing, limitation
catalog generation, worktree creation, provider execution, or deployed browsing
through its zero-cost run command.

## Baseline and comparison

A clean core `envelope.json` is a baseline candidate. Keep the complete run
directory so raw evidence remains available. `compare BASE_SHA CANDIDATE_SHA`
selects the newest normalized envelope for each recorded commit, requires the
same suite, reports adapter-status changes and failed-count increases, and
fails on newly failed case IDs. It never checks out or mutates either revision.

Comparison refuses dirty, unstable, or identity-incomplete artifacts. It also
requires compatible evaluator, policy, failure-schema, and adapter dataset
bindings; incompatible evidence is `BLOCKED`, not an approximate comparison.

`diagnose CASE_ID` returns every matching raw row and normalized failure record.
If no retained artifact contains the ID, the diagnosis is `BLOCKED` rather than
an invented explanation.

## Executable local adapters and remaining external gaps

The Astra v1 manifest binds executable RAG/source diagnostics, metamorphic
relations, three-turn trajectories, typed fault cases, session lifecycle,
current and legacy browser journeys, and validated performance samples. Native
reports are retained and reconciled; local assertion failures remain failures.
The source-identical evaluator bridge allows baseline/candidate comparison.

Provider RAG remains BLOCKED: sealed retrieval V3 and provider qualification are
not authored or executed. Deployed UI remains NOT_RUN. Local accessible cases
are unsealed and provisional, not comprehensive state-transition, retrieval,
human-calibrated or release qualification. Performance is fake-provider ASGI;
missing matched evidence is NOT_COMPARABLE, never a measured regression pass.

Provider-backed adapters require a separately authorized positive ceiling,
pre-call reservation, OpenRouter boundary, verified receipts, and explicit
deployment identity. They are outside EvalLab v1.
