# FireLens V1.5-2 before/after benchmark

Status: **provisional — do not treat the existing legacy snapshot as the frozen ruler**

Governing decision: `docs/adr/0010-evaluation-dataset-roles-and-sealed-gates.md`

## Purpose

The V1.5-2 benchmark measures whether the upgrade improves FireLens without allowing a gain in one
area to hide a safety, evidence, usability, cost, or deployment regression. It composes existing
FireLens gates; it does not reduce them to one weighted score.

The specification is `data/evaluation/upgrade_benchmark_v1_5_2.yaml`. Its dataset-use policy is
`data/evaluation/upgrade_benchmark_v1_5_2_dataset_roles.yaml`. A ratified snapshot must bind the
candidate commit, corpus and vector identities, configuration and model identities, stable
execution environment, frozen evaluation-input hashes, and benchmark-harness hashes.

The tracks are:

1. zero-cost verification, offline hard-probe quality, complete frontend artifact accounting, and
   the 30-row browser surface/performance matrix;
2. official live-source availability and cached latency;
3. paid development retrieval plus a cost-capped qualified hard probe;
4. paired semantic owner review and five-task UX testing, plus the sealed-label prerequisite;
5. required-after-only sealed retrieval and semantic qualification; and
6. required-after-only preview, distributed-rate-limit, and rollback evidence.

## Current Gate 0 status

The ruler is not yet ratified. The 47-case V2 retrieval set was ranked by a deterministic fake
provider inside a test and written only to a temporary location. No persisted V2 ranking report and
no live or paid V2 ranking run were observed in the current checkout. Human inspection of the
temporary rankings is unknown. This is still an exposure event: V2 cannot be described as proven
untouched or unseen.

The owner must either retire V2 to permanent regression and create a fresh V3 sealed set
(recommended), or explicitly retain V2 with a weaker qualification claim. Until that decision is
recorded in the ADR, registry, and specification:

- do not rank V2 again;
- do not call the provisional snapshot a frozen before baseline;
- do not begin tuning from any V2 result; and
- do not claim that the sealed holdout remains unexposed.

The source-disjoint semantic holdout is also still planned. A ratified registry cannot retain a
planned dataset: before the ruler freezes, a checked-in schema-v3 manifest must commit the
owner-held payload hash, at least 25 cases, case-level source/family commitments, canonical source
and question-family rosters, the double-review requirement, and pre-candidate freeze time. It must
bind a separately frozen development-exposure registry and retain the exact machine-recomputed
zero-overlap audit. Both registry and manifest become frozen identity inputs; the case payload need
not be exposed in the repository.

The v2 worktree harness now implements these evidence-contract protections:

- snapshots retain and compare a stable environment fingerprint before paired latency is eligible;
- UX capture retains cohort/device counts, shares, and sliced outcomes, then enforces the frozen
  before/after comparability rule; and
- deployment summaries bind retained sanitized raw rate-limit and rollback artifacts by SHA-256 and
  exact parsed content rather than relying on reviewer-authored YAML alone; and
- semantic-holdout qualification binds the schema-v3 manifest and frozen development-exposure
  registry, recomputes exact source/family overlap, and binds the raw candidate report to a
  bundle-v2 blinded review with reproducible identity-bound actor orders, a 75-event append-only
  presentation hash chain, and event-linked reviewer/adjudicator decisions before recomputing every
  finding and agreement statistic; and
- capture launches the frozen frontend surface runner itself into a fresh owned directory, verifies
  its time/path/PNG/environment/build identities, recomputes every surface/journey/performance
  result, and inventories the full emitted `dist/` tree; and
- the required-after-only manual frontend validator binds a commit-derived candidate ID and retained
  readiness identity response, three distinct named roles, 30 frozen atomic checks, explicit WCAG
  2.2 AA thresholds/mappings, five OS/browser/input/assistive-technology profiles across all ten UI
  states, hash/size-bound retained files, an ordered timestamp chain, and final adjudication; and
- comparison resolves the unique commit that introduced the tracked before-snapshot seal and proves
  an exact clean ancestry from the before candidate, through that immutable seal, to the after
  candidate. Shallow history, dirty or rewritten seals, ambiguous history, unrelated commits, and
  side-branch candidates fail closed.

They have not yet been exercised in an eligible clean before/after capture or with real participant
or deployment evidence. Gate 0 also remains open because no eligible v2 before snapshot has been
captured and committed with the implemented tracked seal; the semantic holdout is still a planned
rather than fully identity-bound sealed role and has no real manifest/report/review bundle; and no
real manual accessibility/product-safety bundle has been completed by the required named people.
The automated and manual frontend metric contracts are implemented, but implementation is not human
review evidence. Therefore, even a
numerically complete capture made before those protections land is diagnostic rather than an
eligible frozen baseline.

The current zero-cost Gate 0 worktree passed one uninterrupted `make verify` on 2026-08-08: secret scan,
generated API contract, Ruff lint/format, mypy across 65 source files, 573 Python tests (3 skipped, 109 subtests), 15
frontend tests, production build, 4 Sites tests, and 18 Playwright flows. This verifies the harness
wiring; it does not substitute for the still-missing owner decisions, real human evidence, paid
before evidence, or committed seal.

The legacy schema-v1 capture recorded 73,547 initial-route and 46,422 lazy JavaScript gzip bytes,
119,969 bytes in total. Current build inspection also found about 869 KB of emitted fonts and an
808,528-byte logo that the JS-only score missed. These numbers are diagnostic only until the ruler
is ratified and the complete CSS/font/image/transfer inventory is recaptured under the surface
harness.

The current diagnostic frontend surface probe now exercises all ten product/safety states at three
viewports. It completed 30/30 rows, but 0/30 qualified: 27 rows had a serious contrast finding; all
30 failed text-size, target-size, or styled-control rules; the ten-record live fixture rendered ten
markers but only eight accessible-list records in all three viewports; and the browser made 200
direct OSM tile requests. Forty-five of those OSM requests aborted during Leaflet refits and remain
runtime failures rather than being allowlisted. There were no structural, overflow, clipping, page,
stylesheet, origin, or unexpected-console failures. All three scripted journeys and both lab
profiles passed; the worst observed p75 values were 828 ms LCP, 0.01692 CLS, 30.6 ms interaction
proxy, and 829.9 ms map ready.
The protocol is still provisional, so this is current-checkout diagnosis rather than an eligible
frozen before result. The qualitative findings are in
`docs/reports/V1_5_2_PRODUCT_AUDIT.md`.

A 2026-08-08 accessibility-foundation follow-up completed the same 30-row matrix and qualified
18/30. It eliminated the automated axe A/AA, text-size, target-size, styled-control, and 8/10
accessible-roster failures; map/list parity is now complete. The remaining 12 failures are the
map-bearing rows because the browser still made 200 direct OSM tile requests, including 40 aborted
requests across five rows. Functional journeys passed. Two performance samples were structurally
invalid, so no follow-up performance claim is made. This is diagnostic evidence only, not an
eligible paired after result.

A subsequent local-vector map follow-up removed all runtime tile-host requests and bundled a
simplified official Government of BC provincial boundary with visible source/licence disclosure.
The resulting diagnostic completed and passed all 30 automated surface rows, every functional
journey, and both lab-performance profiles. It observed zero direct third-party tile calls, zero
axe A/AA findings, zero undersized text or targets, and complete map/list parity. Because the
protocol is still provisional and no named specialist or participant review occurred, this is a
closed implementation defect and current-checkout diagnostic—not an eligible after result or human
accessibility/UX qualification.

Deployment artifact eligibility is also open, but the source packaging gaps are narrowed.
`vercel.json` now includes only the governed corpus, vector, conditional document context, repair,
runtime-candidate/contract, and built-client globs instead of broad `data/**`; its build hook writes
a full-commit candidate from the shipped corpus/vector manifests. `Dockerfile` now includes the
repair registry, app entrypoint, runtime contract, candidate generator, and a candidate bound to
Render's documented Git-commit build argument (or an explicit local build argument). Runtime config
also exposes Render's commit and instance identity. The current `metadata_context_v1` index does not
require document context; that sidecar becomes a required conditional input only if the frozen
vector/config strategy selects V2. The shared allowlist and inventory gate are implemented, but no
real extracted Vercel/Docker pair has been inspected and Docker is unavailable in this local
environment. Therefore platform-export provenance, actual evaluation exclusion, runtime-observed
candidate identity, distributed rate limiting, rollback, and deployment qualification remain open.

Candidate supply-chain evidence is now implemented but not release-qualified. A manual, pinned
workflow runs zero-cost verification, creates a CycloneDX SBOM, SLSA v1 provenance statement,
dependency/license reports, and a closed manifest, then independently verifies the bundle before
upload. The first live local advisory scan found three Python vulnerabilities and four high npm
vulnerabilities; upgrading the exact locks to fixed releases produced a clean Python audit and a
zero-vulnerability npm audit. The resulting ignored local bundle at
`output/candidate-evidence-local-20260808-after-examination/` verifies against commit `b00544c...`. It is diagnostic
local evidence from a dirty implementation worktree, not a GitHub-produced artifact, signed
attestation, frozen candidate, or promotion authorization.

## Dataset and comparison rules

Paired metrics use development, permanent-regression, or paired-human inputs. They require eligible
before and after values. After-only metrics must be null before, present after, and pass an explicit
gate. The capture command rejects sealed retrieval and semantic-holdout inputs for `--label before`;
preview, distributed-rate-limit, and rollback evidence must also be omitted from the before capture.

Missing evidence remains null. It is never converted to `0`, `false`, or a pass. Strict booleans,
integers, and finite numbers prevent type coercion from turning malformed evidence into a result.

For a paired numeric metric, the materiality boundary is:

`max(absolute tolerance, abs(before) * relative tolerance)`

The ratified tolerance and rationale live beside each metric in the specification. Deterministic
pass rates and safety counts have zero tolerance. Local and live latency have explicit noise
allowances plus hard gates. Near Me is marked `must_improve`: the final median must be at least 25%
faster than before and no more than 45 seconds.

Numeric latency tolerance applies only after identity eligibility. Both rounds must have the same
OS/release, CPU architecture and identity/count, machine or runner class, Python, Node, and npm;
browser-involved timing also requires the same browser and Playwright identity. Deployment/live
timing additionally retains deployment, region policy, cache state, and upstream mode. Missing or
mismatched environment fields make the latency row non-comparable; the tolerance cannot convert it
to a pass.

The client entry/lazy dependency graph is read from
`apps/web/dist/client/.vite/manifest.json`. Initial-route size is the gzip total of
the entry's static JavaScript/CSS closure. Lazy size is the gzip total of dynamic-import closures not
already counted as initial. The inventory then scans the complete `dist/` tree and classifies every
client file, font, image, server file, hosting/deployment metadata file, and other artifact exactly
once. Missing server/hosting outputs, invalid or ambiguous manifest evidence, an unclassified file,
or a total mismatch fails measurement. The hard client JavaScript budgets are 80,000 gzip bytes
initial and 55,000 gzip bytes lazy; the specification contains the remaining CSS/font/image/server/
metadata/total budgets.

## Eligible evidence only

Paid calls require explicit approval of a positive maximum OpenRouter budget. Human evidence must
come from a complete, current, hash/commit-bound summary with a named reviewer, review timestamp,
and explicit `qualified` decision. The required paired evidence is:

- the fixed 50-case development retrieval report;
- the 105-case qualified hard-probe report;
- claim-level review of all 50 known conversation cases;
- the same five UX tasks, moderator protocol, device policy, rubric, and comparable independent
  cohorts before and after.

Each eligible UX round requires 12 participants; a run with 8--11 participants may be retained only
as a pilot and is ineligible for the before/after claim. It must include at least four novice BC
residents, four wildfire-aware participants, three desktop participants, three mobile participants, one keyboard participant, and one
screen-reader participant. Capture must retain counts, shares, and task outcomes by cohort and
device. The comparison rejects any registered cohort or device whose share differs by more than
0.15 between rounds. Keyboard and screen-reader coverage must exist in both rounds, but their shares
need not be balanced.

The 47-case label review is a dataset-bound prerequisite, not a model-improvement metric. It may be
completed before implementation, must be retained with its actual sidecar, and must pass before any
active sealed ranking. Both semantic and retrieval summaries retain reviewer identity, timestamp,
and source-sidecar hashes; capture rejects a summary without the exact retained files.

Artifact hashes prove which files were named; they do not prove that copied aggregate fields were
derived correctly. The v2 worktree therefore recomputes the 50-case semantic and 47-case
retrieval-owner-review summaries from retained reports/sidecars, development and sealed retrieval
metrics from exact rank rosters against the governed dataset/corpus, and semantic-holdout findings
from the manifest-bound candidate report plus blinded double-review/adjudication bundle. Submitted
summaries must agree exactly with those recomputations.

Historical reports are useful for diagnosis but are ineligible as the V1.5-2 before baseline when
they use an older commit/corpus, lack current report identity, lack complete reviewer metadata, open
a historical holdout, or represent a dry run or fake-provider result. The historical semantic and
retrieval review artifacts currently in the repository do not establish an eligible current human
baseline. Playwright counts and screenshots do not substitute for participant evidence.

## Ratify and capture the before baseline

First resolve the ADR's V2/V3 decision, commit the active sealed and semantic-holdout manifests,
promote every active holdout to `sealed_release_qualification`, include each manifest in the frozen
identity inputs, update the registry/specification, finish the eligibility checks, and set
`frozen_before_upgrade: true`. Capture requires a clean tracked worktree and rejects relevant
untracked runtime/benchmark inputs both before and after its commands. The ignored output snapshot
must then be sealed by a tracked attestation that records its SHA-256, commit, specification hash,
creator, and freeze timestamp. The implemented `seal-before` command writes
`data/evaluation/upgrade_benchmark_v1_5_2_before_snapshot_seal.json` and also binds candidate,
dataset, harness, and paired-metric identities. Commit that new seal before application work begins.
Without a tracked, unmodified seal, an output file can be edited after capture and is not an
immutable baseline. Then generate all paired inputs on one unchanged before commit.
Examples of the paid commands are:

```bash
.venv/bin/python scripts/run_hard_probe.py \
  --mode qualified \
  --max-cost-usd 1.25 \
  --output output/qualification/hard_probe/qualified.json

make benchmark-retrieval-v1-5
make benchmark-v1-1-paid
```

Create, complete, and validate the semantic and active retrieval label reviews only after their
source reports/dataset are fixed:

```bash
make owner-review-template
make qualify-owner-review

.venv/bin/python scripts/retrieval_owner_review.py packet \
  --dataset path/to/active_sealed_retrieval.yaml \
  --output output/benchmark/v1_5_2_retrieval_owner_review.md
.venv/bin/python scripts/retrieval_owner_review.py template \
  --dataset path/to/active_sealed_retrieval.yaml \
  --output output/benchmark/v1_5_2_retrieval_owner_review.yaml
.venv/bin/python scripts/retrieval_owner_review.py validate \
  --dataset path/to/active_sealed_retrieval.yaml \
  --review output/benchmark/v1_5_2_retrieval_owner_review.yaml \
  --output output/benchmark/v1_5_2_retrieval_owner_review_summary.json
```

The label-review workflow may inspect questions and original passages, but it must not rank the
active sealed set. Fill the generated UX template from actual participant sessions.

The UX report is session-level: at least 12 participants, a named moderator,
pseudonymous cohort/device/multi-access records, and exactly one attempt per person per frozen task.
The v3 report records frozen criterion booleans, critical-error codes and notes, capped duration,
SEQ, confidence, and observed outcome; completion and the evidence/freshness/official-source metrics
are recomputed rather than accepted from a moderator. It requires novice, wildfire-aware, keyboard,
and screen-reader coverage. Unsuccessful Near Me attempts receive the 120-second cap. Runs with
8–11 participants may be retained as pilots but are ineligible for the frozen before/after
comparison. Each round reports Wilson intervals, worst core-cohort/device slices, and a deterministic
participant bootstrap. The paired report bootstraps independent cohorts; a Near Me interval that
crosses or reaches zero is an observed sample difference, not an established gain.

These access-method labels prove sampling coverage only. They do not prove WCAG 2.2 AA, correct
screen-reader behavior, or visual-state quality. Automated accessibility, frozen visual states,
CSS/layout, map privacy/parity, named-environment lab performance, and manual release review now have
separate gates. The manual gate uses
`data/evaluation/frontend_manual_review.v1.yaml`: three distinct named people must retain exact-
candidate evidence for 30 atomic checks and the full five-profile by ten-state matrix. The validator
recomputes the two qualification booleans and open-finding count; it cannot consume UX participant or
moderator fields as evidence.

Capture the before snapshot with paired inputs only:

```bash
.venv/bin/python scripts/upgrade_benchmark.py capture \
  --label before \
  --output-dir output/benchmark/v1_5_2/before \
  --qualified-hard-probe output/qualification/hard_probe/qualified.json \
  --development-retrieval-report output/benchmark/v1_5_retrieval_comparison.json \
  --semantic-report output/benchmark/v1_1_conversation_live_report.json \
  --semantic-review-sidecar output/benchmark/v1_5_owner_semantic_review.yaml \
  --semantic-review-summary output/benchmark/v1_5_owner_semantic_review_summary.json \
  --retrieval-review-sidecar output/benchmark/v1_5_2_retrieval_owner_review.yaml \
  --retrieval-review-summary output/benchmark/v1_5_2_retrieval_owner_review_summary.json \
  --ux-report output/benchmark/v1_5_2/before/ux_tasks.completed.yaml
```

This also runs `make verify`, the 105-case offline hard probe, the official live qualification, and
the frontend manifest measurement. `--skip-live` is permitted only when official network data is
unavailable; it deletes any stale live report in the output directory and leaves the live metrics
missing.

The live qualification uses evidence schema v2. In addition to the frozen cached map-concurrency
roster and chat/map identity check, it submits one canonical coarse-location request to
`POST /api/v1/live/nearby`. The parser independently recomputes its requested scope, ordered
viewport, explicit pagination, returned record count, unavailable layers, and HTTPS official
fallback roster. A successful HTTP response with inconsistent pagination or missing fallbacks
cannot qualify.

`scripts/live_slo_evidence.py` provides a separate no-model-cost diagnostic for repeated cold and
cached official-source observations by layer and three fixed coarse BC regions. Its verifier
recomputes the complete roster, availability, p50/p95 latency, stale-layer observations, freshness
coverage, and authoritative layer-update age from raw source-level observations. Protocol v1 keeps every threshold null
and reports `qualification_eligible=false`; no diagnostic run may be relabeled as a production SLO.
See `docs/protocols/V1_5_2_LIVE_SLO_EVIDENCE.md`.

If and only if the before capture is complete, seal it with a named owner and commit the generated
seal before any application work:

```bash
.venv/bin/python scripts/upgrade_benchmark.py seal-before \
  --before output/benchmark/v1_5_2/before/snapshot.json \
  --owner "Named benchmark owner"
```

The command refuses a dirty/untracked benchmark worktree, an incomplete snapshot, an identity/hash
mismatch, or an existing seal. The generated seal itself is intentionally new and must then be
reviewed and committed.

Never pass any of these options to a before capture:

```text
--retrieval-qualification
--semantic-holdout-report
--semantic-holdout-review-bundle
--semantic-holdout-summary
--frontend-manual-review-bundle
--preview-report
--deployment-report
--rate-limit-evidence
--rollback-evidence
--vercel-artifact-root
--vercel-artifact-id
--vercel-platform-root
--docker-artifact-root
--docker-artifact-id
--docker-platform-root
```

If budget, reviewers, or participants are unavailable, capture may retain those paired fields as
missing for development bookkeeping, but the comparison cannot pass and no improvement claim may
be made for the missing track. Do not call such a partial snapshot a complete baseline.

## Capture the final candidate

Run development experiments before candidate freeze. Never tune from the active sealed retrieval or
source-disjoint semantic holdout. On one unchanged final-candidate commit, repeat every paired input
with the same protocol and then create the after-only evidence.

The active sealed retrieval command is permitted only after its complete named owner label review
passes and only after the final candidate is frozen. Replace the placeholder paths with the dataset
accepted by the ADR:

```bash
.venv/bin/python scripts/run_retrieval_qualification.py \
  --dataset path/to/active_sealed_retrieval.yaml \
  --manifest path/to/active_sealed_retrieval.manifest.json \
  --owner-review output/benchmark/v1_5_2_retrieval_owner_review.yaml \
  --output output/benchmark/v1_5_2_sealed_retrieval.json \
  --repetitions 3 \
  --max-cost-usd 0.75
```

Capture all paired and after-only reports on that same commit:

```bash
.venv/bin/python scripts/upgrade_benchmark.py capture \
  --label after \
  --output-dir output/benchmark/v1_5_2/after \
  --before-snapshot output/benchmark/v1_5_2/before/snapshot.json \
  --qualified-hard-probe output/qualification/hard_probe/qualified.json \
  --development-retrieval-report output/benchmark/v1_5_retrieval_comparison.json \
  --retrieval-qualification output/benchmark/v1_5_2_sealed_retrieval.json \
  --semantic-report output/benchmark/v1_1_conversation_live_report.json \
  --semantic-review-sidecar output/benchmark/v1_5_owner_semantic_review.yaml \
  --semantic-review-summary output/benchmark/v1_5_owner_semantic_review_summary.json \
  --semantic-holdout-report output/benchmark/v1_5_2_semantic_holdout_report.json \
  --semantic-holdout-review-bundle output/benchmark/v1_5_2_semantic_holdout_review_bundle.json \
  --semantic-holdout-summary output/benchmark/v1_5_2_semantic_holdout_summary.json \
  --frontend-manual-review-bundle output/benchmark/v1_5_2/frontend_manual_review.json \
  --retrieval-review-sidecar output/benchmark/v1_5_2_retrieval_owner_review.yaml \
  --retrieval-review-summary output/benchmark/v1_5_2_retrieval_owner_review_summary.json \
  --ux-report output/benchmark/v1_5_2/after/ux_tasks.completed.yaml \
  --preview-report output/qualification/v1_5_preview.json \
  --deployment-report output/benchmark/v1_5_2/after/deployment.completed.yaml \
  --rate-limit-evidence output/benchmark/v1_5_2/after/rate_limit.raw.json \
  --rollback-evidence output/benchmark/v1_5_2/after/rollback.raw.json \
  --vercel-artifact-root /path/to/extracted-vercel-artifact \
  --vercel-artifact-id vercel-deployment-artifact-id \
  --vercel-platform-root /var/task \
  --docker-artifact-root /path/to/extracted-docker-artifact \
  --docker-artifact-id docker-image-digest-or-artifact-id \
  --docker-platform-root /app
```

The two artifact roots must be isolated, non-overlapping staged build directories outside the
benchmark output directory. The capture does **not** accept an owner-submitted inventory JSON as
proof. It runs `build_runtime_inventory` against every byte in each root before any benchmark
command, reruns it after all commands, and rejects a symlink, escape, missing/prohibited file,
candidate/commit mismatch, or any pre/post mutation. It writes capture-owned Vercel and Docker
inventories, the exact embedded candidate configurations, and a recomputed logical comparison under
`after/runtime_artifacts/`. Five required-after-only metrics gate overall qualification, missing
required files, prohibited files, cross-platform identity, and candidate-commit identity. The
comparator revalidates inventory schemas and content hashes and recomputes the comparison; it never
trusts a submitted `qualified` field.

The inventory assurance scope is deliberately `staged_logical_bundle`. `qualified` in the staged
comparison means that the supplied roots satisfy the frozen logical-bundle contract; it is not a
release claim. Every current inventory records `platform_export_provenance_verified=false` and
`runtime_candidate_identity_observed=false`, and the comparison records
`release_qualified=false` with both blockers. A later gate must bind immutable Vercel deployment and
Docker image/export provenance and observe the running readiness identity before staged parity can
be promoted to platform/runtime proof.

The semantic manifest contains only the owner-held payload commitment, canonical case IDs/input
hashes, case-level source/family commitments, canonical rosters, and protocol evidence; prompts and
source text stay owner-held. Its disjointness audit is accepted only when exact source and family
intersections recomputed against the hash-bound frozen development registry are empty. The retained
candidate report contains outputs and atomic claims but no prompt text. The retained review bundle
contains two distinct named independent reviews per case, a distinct adjudicator, identity-bound
randomized actor orders, locked pre-adjudication decisions, per-claim labels, dangerous-omission
flags, and a hash-chained presentation event for each reviewer/case and adjudicator/case exposure.
Every decision links the exact event it followed. The summary is optional and is accepted only when
all substantive fields exactly match recomputation from those raw artifacts.

The frontend manual bundle is mandatory for `after` and forbidden for `before`. Its candidate ID is
exactly `firelens-v1-5-2:<40-character-commit>`. The retained readiness-response evidence must target
the bundle's canonical base URL and return that candidate ID and commit. Every retained evidence file
must live below the bundle's `evidence/` directory without symlinks or traversal and match its declared
SHA-256, byte count, media type, profile, state, and capture time. A valid negative review may be
retained, but every non-passing atomic check or profile/state cell needs an open finding and the three
after-only metrics will fail qualification.

The event chain detects deletion, reordering, partial rewriting, or decision/event substitution once
its head and review-bundle digest are retained by the candidate snapshot. Because final holdout
qualification presents one candidate, the frozen algorithm randomizes case order independently for
each reviewer and the adjudicator while recording the candidate at position one under a blinded
label; it does not claim a multi-candidate ordering experiment. The log also cannot independently
prove wall-clock truth or prevent a privileged operator from replacing an entire not-yet-retained
bundle, so the review workspace still must append events durably and the final snapshot/seal must
retain the resulting digests.

The local operational workspace now provides a loopback-only, capability-isolated API and browser
client, same-actor recovery of an already-open deterministic presentation, immutable event/head
receipts, and a content-addressed final evidence export plus verifier. Those artifacts remain marked
`nonqualifying_backend_scaffold` and `qualification_eligible=false`; the browser/client smoke and
47-case retrieval preparation dry run are wiring evidence only. A fail-closed adapter now performs
the canonical conversion for conversation and retrieval reviews, but only after a fourth named
human attests the private storage/replay controls and external final-head retention. It refuses open
adjudicated findings, writes the sidecar, recomputed summary, and content-free qualification
manifest atomically, and preserves all actor/journal and source/export/analysis/attestation hashes.
Benchmark capture now rejects a legacy semantic or retrieval sidecar without that manifest. No real
named humans, independent storage review, external anchor, or qualifying package exists yet.

The deployment report must embed evidence exactly equal to two retained sanitized raw artifacts:
one distributed-rate-limit artifact and one rollback artifact. Record both SHA-256 values in the
reviewed report. The rollback artifact contains the candidate/restored identities and canonical
restored-readiness, anonymous-homepage, release-identity, grounded, and live smoke observations.
Redact secrets and precise user data before hashing and retention; do not recreate the raw artifact
from the reviewed summary.

Before preview qualification, supply the extracted Vercel and Docker/Render artifacts themselves to
the capture-owned inventory step. A ready endpoint does not compensate for shipping evaluation
material or omitting a required governance/context input.

Sealed retrieval must be explicitly qualified, contain exactly three complete repetitions, and
reach at least 46/47 Recall@5 in every repetition. The source/question-family-disjoint semantic
holdout must contain at least 25 fully adjudicated cases, zero unsupported or unclear material
claims, and zero dangerous omissions.

## Compare

```bash
.venv/bin/python scripts/upgrade_benchmark.py compare \
  --before output/benchmark/v1_5_2/before/snapshot.json \
  --after output/benchmark/v1_5_2/after/snapshot.json \
  --output-json output/benchmark/v1_5_2/comparison.json \
  --output-markdown output/benchmark/v1_5_2/comparison.md
```

Comparison fails closed if specification, dataset, or harness hashes differ; a paired before value
is missing; a required after value is missing; an after gate fails; a material regression occurs;
or a `must_improve` target is not met. It must also reject a missing/mismatched environment,
non-comparable UX cohort/device distributions, an unattested before snapshot, or a deployment
summary whose retained raw artifact hash/content does not match. An after-only value appearing in
the before snapshot is an invalid comparison, not a baseline result.

## Interpretation limits

- Offline hard-probe success proves deterministic wiring and policy behavior, not live-model
  semantic quality.
- A development retrieval gain may guide tuning; it is not final sealed qualification.
- Exact citation and schema checks do not prove semantic entailment; owner review remains final.
- Bundle reduction cannot compensate for worse task completion or evidence comprehension.
- Official-source latency varies; interpret it with availability, cache behavior, tolerance, and
  the four-second hard gate.
- An LLM judge may be evaluated offline or in shadow, but cannot supply or replace required human
  evidence.
- A benchmark pass is evidence for one candidate. Production still requires explicit owner
  approval and verification that the promoted artifact is the qualified artifact.
