# 12 — Evaluation System

No single score can establish routing, retrieval, publication, live-data
honesty, conversation coherence, UI quality, and release identity. EvalLab is a
thin canonical layer over existing evaluators; it does not replace their
datasets or weaken their oracles.

## Current zero-cost surfaces

| Surface | Current catalog | What it can establish | What it cannot establish |
| --- | --- | --- | --- |
| ProductBench v2 offline | 31 executable fake-provider cases from a 50-case development catalog | Deterministic product predicates | Provider quality, 19 manual/provider cases, release quality |
| ClaimBench v2 | 332 rows: 86 faithful, 246 mutations | Deterministic validator behavior | Independent semantic completeness |
| Hard probe RC2.2 offline | 105 cases; declared floor 86 | Fake-provider regression behavior against its expectation profile | Paid provider, sealed holdout, deployed behavior |
| Source-aware conversation | 106 cases | Real agent control flow over fake/local dependencies | Real upstream/provider behavior or comprehensive trajectories |

The Sol/unchanged-application bridge result is **FAIL 562/574**: ProductBench 31/31,
ClaimBench 332/332, hard probe 93/105, and source-aware conversation 106/106.
Ten of the hard probe's 12 expectation mismatches are `CRITICAL`; the aggregate
floor cannot waive them. They remain evaluation-contract owner-review cases and
are not relabelled product defects.

The [Astra continuation](../reports/ASTRA_CONTINUATION.md) adjudicates the visible
behavior separately: some cases expose real provenance, source-selection and
safety-clause defects. The original profile and red artifacts remain unchanged.
`astra_local_diagnostics.v1.json` declares accessible, model-assisted diagnostics:
30 RAG/source/oracle cases, 14 metamorphic cases, three actual three-turn flows,
12 fault nodes (including their native subtests), seven lifecycle tests, seven
current-interface browser journeys, and six performance checks. The 19 legacy
browser tests remain a separate adapter with their original assertions.

Local adapters retain pytest events or browser-native JSON, exact rosters,
test/fixture/corpus hashes, logs, screenshots/traces and performance samples.
Validation reconciles native results, wrapper counts, failure records, exits,
and material identity. Python diagnostic sockets and browser routes deny
external destinations; loopback servers are allowed. This is fixture evidence,
not a calibrated semantic oracle or tamper-proof execution attestation.

The final envelope/raw reports are retained outside Git and bind the exact
clean candidate SHA/tree, stable source, runner, schema, policy, registry, and
adapter dataset/evaluator identities. This is deterministic local evidence,
not provider, real-feed, sealed, human, preview, or production qualification.

## Integrity and comparison

For a dirty checkout, `application_sha` binds the base commit/tree, binary
tracked diff, and every untracked path and byte. Source identity is captured
again after evaluation. Dirty evidence cannot pass; changed-during-run evidence
is still persisted as `BLOCKED` and cannot be compared.

Historical compare is evidence verification, not a score-file diff. Each clean
envelope is opened against a detached snapshot of its own recorded commit,
validated there, and replayed through all four core adapters. Comparison blocks
identity-incomplete evidence and incompatible policy, registry, failure schema,
evaluator, or dataset bindings. Volatile vector-manifest self-hashes are not a
substitute for source identity.

The evaluator-only bridge `2295b24` has the same production runtime and frontend
bytes as Sol `c578de5`. Product changes are evaluated against that bridge with
identical evaluator/test/material bytes. This avoids pretending an upgraded
harness executed inside the old commit, or loosening comparator identities.

ProductBench's `trace.response_sha256` was derived from a response containing a
random trace ID, but the normalized record does not retain that preimage.
EvalLab therefore omits the field from retained and replayed rows and rejects
raw reports that reintroduce it. It does not pretend an unauthenticatable hash
is integrity evidence.

The checked-in
[`CURRENT_DIAGNOSTIC.json`](../../evals/eval_lab/core/CURRENT_DIAGNOSTIC.json)
is a superseded historical pointer to the earlier dirty smoke. It remains
labelled rather than being retroactively upgraded.

## Method

1. Freeze application, dataset, evaluator, provider/judge prompt, and
   environment identity.
2. Reproduce a failure and record the first incorrect layer.
3. Add a minimal regression plus neighboring/metamorphic cases.
4. Fix the earliest authoritative owner.
5. Re-run affected deterministic suites, then broader falsification.
6. Run paid, live, sealed, human, preview, and production gates only with
   explicit authority.

Development catalogs guide repair; sealed holdouts and independent review judge
generalization. Model judges require calibration against human decisions and
must expose prompt/model/version. A deterministic score cannot be relabelled as
human or production evidence.

## Current status

**FAIL / BLOCKED:** The exact local candidate and deterministic gate exist, but
EvalLab core fails. No current live-upstream qualification, paid-provider run,
sealed retrieval review, independent semantic examiner, human
accessibility/product review, preview qualification, or candidate production
qualification exists. Historical results remain useful only as bound
historical evidence.
