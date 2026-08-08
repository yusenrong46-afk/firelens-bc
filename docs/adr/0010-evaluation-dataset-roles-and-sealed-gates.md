# ADR 0010: Evaluation dataset roles and sealed qualification gates

- Status: Accepted — V2 retired to permanent regression; V3 required
- Date: 2026-08-06

## Context

FireLens V1.5-2 needs a measured before/after result without turning a final holdout into a tuning
set. The earlier upgrade scorecard mixed paired improvement metrics with one-time qualification
gates and treated missing human evidence too much like a numerical result.

The current 47-case V2 retrieval set also has a material qualification-history issue. A repository
test invoked its rankings with a deterministic fake provider and wrote the result only to a
temporary location. No persisted V2 ranking report and no live or paid V2 ranking run were observed
in the current checkout. Whether a person inspected the temporary rankings is unknown. Therefore,
V2 cannot honestly be described as proven never ranked or certainly unseen.

## Decision

### Dataset roles

Every evaluation dataset split is registered with one role and an explicit baseline policy:

- **development**: may be used for experiments, tuning, and paired before/after measurement;
- **permanent regression**: already exposed, useful for repeatable checks, but not an unseen
  qualification claim;
- **paired human**: the same task and rubric are measured before and after with comparable cohorts;
- **sealed release qualification**: may be used only for the final candidate and is never a
  `before` value; and
- **planned sealed qualification**: must be created and frozen before the final candidate exists.

Allowed and prohibited uses are declared in
`data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml`, and sealed-role constraints are
machine-validated when the specification loads. Development or exposed regression sets establish
the improvement gap. Sealed sets establish only whether the final candidate clears a release gate.

### V2 sealed retrieval disposition

The owner accepted the recommended disposition on 2026-08-08. V2 is permanently retired from
sealed use and remains unchanged as regression/failure-reproduction data. It cannot support an
untouched, unseen, or final-generalization claim.

A fresh 47-case V3 is the only retrieval set eligible for final sealed qualification. V3 receives
two independent label reviews and adjudication before any ranking, is never ranked for the before
baseline, and is run exactly once as a three-repetition final-candidate qualification.

### Paired, prerequisite, and after-only snapshots

The `before` snapshot may contain paired metrics and dataset-bound prerequisites such as the
label-only retrieval review. The capture command must reject a sealed retrieval report or
semantic-holdout report when `--label before` is used. Preview, distributed-rate-limit, and rollback
proof also remain after-only and therefore stay null in the before snapshot.

An after-only metric has no before value, must be present after the upgrade, and must clear its
explicit gate. A paired metric requires both values. A prerequisite may be completed before
implementation but is not scored as an improvement; it must be present and pass for the final
candidate. Missing measurements remain null and fail a required comparison; they are never coerced
to zero, false, or pass.

### Comparison and bundle policy

Metric value types are strict. Boolean values are not interchangeable with `0` or `1`, and numeric
values must be finite. Paired numeric metrics use the ratified tolerance recorded in the benchmark
specification: the materiality boundary is the greater of the absolute tolerance and the relative
tolerance applied to the before value. Safety counts and deterministic pass rates have zero
tolerance. A metric marked `must_improve` must clear its improvement threshold, not merely remain
within tolerance.

Frontend JavaScript is measured from the Vite build manifest. The initial-route total is the gzip
size of the entry's static dependency closure; lazy total is the gzip size of dynamic-import
closures not already counted as initial. Every emitted JavaScript file must be classified exactly
once. A missing, invalid, ambiguous, or incomplete manifest fails measurement rather than producing
a zero. Initial and lazy chunks have separate hard budgets so a map can remain lazy without hiding
route-cost growth in one aggregate number.

Latency is comparable only when both snapshots retain the same stable execution-environment
identity: operating-system family/version, machine or runner class, CPU architecture, Python,
Node/npm, and browser/Playwright versions where a browser participates. Live/deployment timing must
also identify the deployment, region policy, cache state, and upstream mode. A mismatch makes the
latency row ineligible; it is not absorbed by the numeric tolerance. The v2 worktree harness now
captures and compares OS/release, architecture, CPU identity/count, Python, Node, and npm for the
existing paired timing rows. Browser/Playwright identity remains part of the separate pending Web
Vitals contract. Gate 0 still requires full verification and an eligible clean before capture
before the implemented protection is accepted.

### Human evidence

Human-review summaries are eligible only when they are complete, hash/commit bound, explicitly
qualified, retain the actual review sidecar, and include reviewer identity and review timestamp.
Semantic review requires all 50 known conversation cases; retrieval-label review requires all 47
cases. UX evidence uses the same five
tasks, protocol, rubric, and comparable independent cohorts before and after. Missing or partial
review is `not_run` or fails validation, not a 0% score.

"Comparable cohorts" is a machine-checkable evidence rule, not a narrative assertion. Each round
must retain participant counts by registered cohort and device class plus keyboard and screen-reader
coverage. The frozen protocol targets 12 participants, permits eight only with a documented
recruitment constraint, requires at least four novice BC residents and four wildfire-aware
participants, at least three desktop and three mobile participants, and at least one keyboard and
one screen-reader participant. The maximum absolute before/after share difference for every
registered cohort and device class is 0.15. Results must retain task outcomes by cohort and device
so an aggregate cannot conceal a critical slice. The v2 worktree harness now retains these slices
and enforces the allocation and 0.15 share-delta rules; Gate 0 still requires full verification and
real eligible before/after participant reports.

Existing historical semantic, retrieval, latency, or UX reports are not accepted as the V1.5-2
before baseline unless they satisfy the current schemas and identities. In particular, prior review
artifacts with incomplete reviewer metadata, results from another commit/corpus, exposed historical
holdout results, and dry-run or fake-provider outputs are ineligible for a current human or live
qualification claim.

The source-disjoint semantic holdout cannot remain merely planned when the benchmark is ratified.
A checked-in schema-v3 manifest must commit its owner-held payload hash, exact canonical case roster
of IDs/input hashes, case-level source/family commitments, canonical aggregate rosters,
double-review rule, and pre-candidate freeze. It must bind a separately frozen development-exposure
registry. The harness recomputes both exact intersections and rejects overlap or a copied
disjointness assertion that disagrees with the rosters. Both registry and manifest become frozen
benchmark identities and the final summary must match recomputation exactly. At freeze time the
registry entry must move to `sealed_release_qualification` and `available`, inherit all sealed-role
prohibitions, and place both artifacts in `identity_inputs`; merely changing `status: planned` to
`status: available` while retaining a planned role is not sufficient.

The machine audit proves exact canonical-identifier non-overlap, not semantic independence between
differently named but equivalent sources or question families. The development registry therefore
requires owner-reviewed canonicalization before freeze, and human review remains authoritative for
conceptual leakage that identifier intersection cannot decide.

Case-level evidence is authoritative over copied aggregates. The capture harness must recompute
semantic-review, development/sealed retrieval, and semantic-holdout totals and decisions from the
retained report, dataset, ranks, and review sidecars, then require exact agreement with any submitted
summary. A matching file hash does not make a manually altered aggregate truthful. The v2 worktree
now recomputes the 50-case semantic and 47-case retrieval-owner-review summaries, development and
sealed retrieval aggregates, and semantic-holdout findings from a registry/manifest-bound candidate
report plus a bundle-v2 blinded review. That bundle requires reproducible identity-bound actor
orders, a monotonic append-only SHA-256 event chain containing every reviewer/case and
adjudicator/case presentation, and exact event-digest links from subsequent decisions. The real
development registry, manifest, owner-held payload, candidate report, presentation journal, and
review bundle still must be created and retained.

UX keyboard and screen-reader participant labels establish sampling coverage, not accessibility
conformance. Release evidence also requires separate automated and manual WCAG 2.2 AA gates,
including keyboard, VoiceOver, zoom/reflow, contrast, target size, live regions, and accessible map
alternatives; frozen visual-state/CSS checks at supported viewports; and named-environment Web
Vitals. These product gates are currently planned but are not represented by the provisional
scorecard, so no UX capture may be described as accessibility proof.

### Baseline immutability

The frozen before snapshot is written under an ignored output directory. Clean-worktree checks make
the capture reproducible but do not make that ignored file immutable after the command exits. The v2
worktree harness now creates a tracked
`data/evaluation/upgrade_benchmark_v1_5_2_before_snapshot_seal.json` containing the snapshot SHA-256,
candidate, dataset, harness, specification, paired-metric, creator, and freeze identities. The
after-capture path and comparator verify it. No eligible v2 before snapshot has been captured or
sealed yet, so the current diagnostic snapshot remains ineligible as a frozen ruler.

### Deployment evidence eligibility

Preview, distributed-rate-limit, and rollback gates are required-after-only. Their structured
summary is eligible only when it points to retained, sanitized raw platform evidence and records
each artifact's SHA-256. Distributed-rate-limit proof must retain the platform rule/config export
and timestamped request observations from distinct clients and regions. Rollback proof must retain
the platform deployment activity plus the raw restored-readiness, anonymous-homepage, release-
identity, grounded, and live smoke outputs. Candidate, restored deployment, and commit identities
must agree across the summary and raw artifacts.

A reviewer-authored YAML assertion by itself is not deployment proof. Secrets and precise user data
must be removed before retention, and the hash must cover the exact sanitized artifact used in
review. The v2 worktree harness now requires retained raw rate-limit and rollback artifacts, verifies
their declared hashes, and requires their parsed content to equal the embedded structured evidence.
No real preview, rate-limit, or rollback evidence has been run yet.

### Runtime artifact boundary

Deployment packaging must use one explicit runtime-artifact allowlist across Vercel and
Docker/Render. The allowlist contains the reviewed production corpus/index and manifests, repair
governance, frontend bundle, and required runtime code/configuration. Document context is included
only when the frozen vector/config strategy selects `document_context_v2`. It excludes
`data/evaluation/**`, owner-review material, benchmark outputs, and all sealed case payloads.

The current packaging paths are inconsistent: `vercel.json` requests broad `data/**` inclusion
while `.vercelignore` excludes evaluation, so precedence and final built contents are unproven;
`Dockerfile` definitely omits `data/repairs/text_overrides.yaml`. The current
`metadata_context_v1` index does not require `data/index/document_context_v2.jsonl`. Each built
artifact must publish a path inventory and fail qualification when a required allowlisted file is
missing or a prohibited evaluation/sealed file is present. The allowlist and standalone staged-
artifact verifier are now implemented. The provisional benchmark freezes the allowlist as an
identity input and the verifier/tests as harness inputs. After capture requires isolated extracted
Vercel and Docker roots plus exact artifact IDs and platform roots; externally submitted inventory
JSON is ineligible. The harness runs the verifier against both roots before and after every other
capture command, retains capture-owned inventories and exact embedded candidate configuration
bytes, and recomputes required/prohibited counts, cross-platform logical identity, and candidate-
commit identity. Any symlink, root escape, mutation, missing/prohibited input, or identity mismatch
fails closed. The verifier also rejects hard-linked inputs, invalid NPY payloads, loose corpus/vector
schemas, fake entrypoints, unreachable Vite entries, and missed side-effect or worker imports. This
proves only the supplied staged roots, not current packaging or platform provenance: inventories
explicitly retain `platform_export_provenance_verified=false` and
`runtime_candidate_identity_observed=false`, so `release_qualified` remains false. No real
Vercel/Docker pair has passed, and the known Docker omission remains.

## Consequences

- Gate 0 cannot be accepted and the before ruler cannot be frozen until the V2 disposition is
  recorded, the semantic holdout is promoted to a fully identity-bound sealed role, and baseline
  sealing plus the implemented environment, UX-comparability, and raw deployment-evidence checks
  pass an eligible capture; remaining derived-evidence and accessibility/visual-performance
  contracts must also be enforced.
- Paid, human, UX, and deployment gaps remain visible until eligible evidence is supplied.
- Neither Vercel nor Docker/Render is release-eligible until capture-owned inventories generated
  from the actual staged roots satisfy the shared runtime allowlist and logical identity gate, the
  roots are bound to immutable platform exports, and the running readiness identity is observed.
- Development measurements can guide tuning without revealing the active final holdout.
- A benchmark pass is evidence about one identity-bound candidate, not permission to deploy it.
- Retiring V2 costs the work needed to create and adjudicate V3, but produces the clearest release
  claim and is the preferred option.
