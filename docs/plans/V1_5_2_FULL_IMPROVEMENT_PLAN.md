# FireLens BC V1.5-2 full improvement plan

Status: proposed execution plan; Gate 0 harness verified, but ratification remains provisional
pending owner decisions and eligible human/paid evidence

Prepared: 2026-08-06 (America/Vancouver)

Starting point: `main` at `b00544c1927ffa12d98689f6a4b0b44b6c7de7e1`

Provisional benchmark specification: `data/evaluation/upgrade_benchmark_v1_5_2.yaml`

Legacy diagnostic capture: `output/benchmark/v1_5_2/before/snapshot.json` (snapshot schema v1;
ineligible as the frozen v2 baseline)

## 1. Executive decision

V1.5-2 should be a comprehensive product and production hardening release, not a rewrite.
Keep the current high-level architecture:

1. deterministic routing and safety checks run before paid model calls;
2. reviewed static evidence is retrieved locally;
3. official current data stays in the typed live-data path, outside the static corpus;
4. models produce bounded, structured proposals;
5. deterministic validation either accepts supported output or fails closed; and
6. human review remains the final semantic authority for release qualification.

The largest gaps are not solved by replacing this foundation. They are solved by completing the
evaluation system, improving semantic evidence integrity and corpus lifecycle, adding production
controls, modernizing the frontend, and making the near-me map a first-class workflow.

An LLM judge is worth testing only as an offline or shadow triage tool. It must not become runtime
authority or replace owner review in V1.5-2. A conversation-model fine-tune should not begin until
measured errors remain after retrieval, prompt, corpus, and interaction improvements and there is
enough adjudicated training data to justify it.

## 2. Evidence legend and current truth

- **Observed**: read from the current checkout or produced by an executed command on the current
  checkout.
- **Inferred**: a design conclusion based on observed code and artifacts; it still needs an
  implementation experiment.
- **Unknown**: no current, identity-bound evidence exists yet.

### Observed baseline

| Area | Current evidence |
| --- | --- |
| Repository | The legacy v1 diagnostic capture identified `main` at `b00544c...`; the dirty Gate 0 worktree and v1 schema make it ineligible as the frozen before candidate |
| Verification | One uninterrupted `make verify` on the current Gate 0 worktree passed on 2026-08-08: tracked-secret scan, generated OpenAPI/client types, Ruff lint and format checks, mypy across 65 source files, 573 Python tests (3 skipped, 109 subtests), 15 frontend tests, the production frontend build, 4 Sites packaging tests, and all 18 Playwright flows |
| Offline hard probe | 105/105, zero critical failures, p95 20.3 ms, controlled doubles, zero model cost |
| Official live qualification | Qualified; chat/map records matched; cached p95 about 381.1 ms for the captured run |
| Retrieval configuration | BM25/vector/fused top-k 30/30/30; RRF 60; rerank top-5; `metadata_context_v1` |
| Models | OpenAI `text-embedding-3-small`, Cohere `rerank-4-pro`, Gemini `3.5-flash-lite`, all through OpenRouter |
| Corpus | 170 chunks, 8 sources, corpus SHA-256 `d5fcd794...` |
| Frontend bundle | Legacy diagnostic Vite-manifest split: 73,547 B initial-route + 46,422 B lazy = 119,969 B JavaScript gzip; the emitted build also contains about 869 KB of fonts and an 808,528 B logo, so JS-only accounting is incomplete and must be recaptured under the surface harness |
| Frontend surface probe | The initial diagnostic completed all 30 state/viewport rows but qualified 0/30. After the accessibility foundation pass, a fresh 30-row diagnostic qualified 18/30: zero axe A/AA findings, undersized text, undersized controls, or map/list parity failures remained. The 12 map-bearing rows still fail because all 200 OSM tile requests go directly from the browser; five rows also retained 40 aborted tile requests. Functional journeys passed. Two lab-performance samples were structurally invalid, so this follow-up makes no performance claim and does not replace the earlier valid diagnostic. The protocol remains provisional, so neither run is a frozen before/after score |
| V2 sealed retrieval exposure | A test ranked all 47 cases with a fake provider into a temporary report; no persisted/live/paid V2 result was observed, and human inspection is unknown |
| Human semantic review | Missing for the current candidate; no valid before score |
| Human retrieval review | Missing for the current candidate; no valid before score |
| UX benchmark | Missing real participants; the reviewer-ready v3 five-task protocol now derives completion from frozen criteria/error codes, permits multiple access methods, caps unsuccessful Near Me attempts at 120 seconds, reports Wilson/worst-slice/seeded-bootstrap evidence, and generates a blank 12-person/60-attempt matrix without fabricated outcomes |
| Paid qualification | Not run for the current candidate because no spend authorization was supplied |
| Deployment qualification | Production readiness was inspected separately, but anonymous preview, distributed rate-limit proof, rollback rehearsal, and real final built-artifact inventories are not captured in the provisional upgrade snapshot. Vercel inclusion is now narrowed to governed runtime inputs and the built client; Docker now ships repair governance, app/contract, and the same generated commit-bound runtime candidate; Render commit/instance identity is wired. Static tests pass, but Docker is unavailable locally and no real extracted platform pair has passed the inventory. Document context is conditional on the frozen retrieval strategy |
| Evidence-contract enforcement | The v2 worktree harness now enforces environment matching, UX cohort/device comparability, raw deployment hash/content binding, case-level recomputation for owner reviews, development/sealed retrieval, the semantic holdout, a required-after-only manual frontend bundle, and capture-owned runtime artifact inventories. Runtime artifact roots are scanned before and after all benchmark commands; candidate configurations, commit identity, required/prohibited paths, and cross-platform logical bytes are recomputed. It also requires a clean tracked before-snapshot seal on an exact `before -> seal -> after` Git ancestry. No eligible seal or real human/deployment/holdout/runtime-artifact evidence exists yet |

The offline 105/105 result proves deterministic wiring and policy behavior under controlled
doubles. It does not prove live-model semantic correctness, provider availability, production
latency, or user comprehension.

The present benchmark specification and legacy schema-v1 zero-cost snapshot are **provisional**, not
the final frozen ruler. The current specification lists the 47-case V2 retrieval set as a required-after-only
gate, but current tests previously ranked it with a deterministic fake provider. That result was
temporary rather than persisted, no live or paid run was observed, and human inspection is unknown;
none of those limits justify calling V2 untouched or unseen. Gate 0 must record an explicit owner
decision: preferably retire V2 to permanent regression and create a fresh V3 47-case sealed set, or
retain V2 with a documented weaker claim. It must also finalize dataset roles, paired development
retrieval/semantic inputs, after-only gates, metric tolerances, strict human-evidence rules, and
manifest-based initial/lazy bundle accounting, stable environment identity for latency,
machine-checkable UX cohort/device comparability, and raw deployment-artifact hash binding. Only
then may the before snapshot be recaptured and the ruler frozen.

## 3. Scope and non-goals

### In scope

- benchmark and experiment governance;
- human case review and usability testing;
- semantic evidence integrity and evidence presentation;
- corpus review, change detection, and source lifecycle;
- retrieval, reranking, model, prompt, and provider tuning;
- backend reliability, observability, security, and distributed controls;
- official live-data service and near-me map workflow;
- frontend architecture, visual design, accessibility, and responsive behavior;
- deployment, preview qualification, rollback, and release evidence; and
- a bounded LLM-judge experiment with a fine-tuning decision gate.

### Explicit non-goals for V1.5-2

- no wholesale RAG/framework rewrite;
- no GraphRAG or autonomous-agent path as the default architecture without a measured win;
- no runtime LLM judge deciding whether an answer is safe or publishable;
- no silent provider fallback that obscures model identity or weakens fail-closed behavior;
- no training on the sealed retrieval set or final human holdout;
- no unreviewed repair or source entering the production corpus;
- no production promotion from a different commit than the qualified candidate; and
- no paid experiment until the owner approves a positive maximum budget.

## 4. Target product and architecture

### User-facing product

The homepage should present two clear jobs:

1. **Ask FireLens** — evidence-grounded preparedness conversation with claim-level source
   inspection; and
2. **Wildfires near me** — a map-first current-information workflow using a named community or
   explicitly consented coarse location.

Desktop should use an open canvas rather than a collection of boxes. Conversation, evidence, and
map remain connected, but the active task owns the visual hierarchy. Mobile should use a full-map
view with a bottom sheet for records and evidence, not a compressed desktop two-column layout.

### Backend target

The API remains FastAPI with strict response contracts. It gains durable operational evidence,
stage-level telemetry, an explicit dependency-readiness model, distributed public controls, and a
deployment artifact that contains every runtime governance input. Static and live authority
boundaries remain unchanged.

### Evidence target

Move from quote-backed answer validation toward an evidence compiler:

`reviewed source -> atomic claims -> authority/condition metadata -> retrieval -> aspect matrix ->`
`bounded draft -> deterministic publication checks -> Proof Card -> human audit`

Exact quotes continue to prove provenance. They are not treated as automatic proof of arbitrary
semantic entailment.

## 5. Workstreams

Each workstream has a lead dependency and a measurable exit condition. Workstream IDs should be
used in issues, experiment records, commits, and the release ledger.

### W0 — Program control, release truth, and benchmark

**Objective:** make every before/after claim reproducible and prevent evidence from drifting away
from the candidate.

Tasks:

1. Ratify the benchmark specification before application work begins.
2. Create a dataset-role registry assigning each dataset split to exactly one of: development,
   permanent regression, paired human before/after, sealed release qualification, or planned sealed
   qualification. Record red-team and UX use in the declared split and allowed-use policy.
3. Record the V2 fake-provider test-ranking exposure and resolve its disposition. Prefer retiring V2
   to permanent regression and creating a fresh V3 47-case sealed set; if V2 is retained, explicitly
   weaken the claim and never describe it as untouched or unseen.
4. Remove the active 47-case sealed retrieval run from paired before/after measurement. Add a
   separate human-reviewed development retrieval set for the measured improvement gap and keep the
   active sealed set as a required-after-only final qualification gate.
5. Split semantic evidence into a development/permanent-regression track for paired before/after
   improvement and a source/question-family-disjoint human holdout for final qualification. Do not
   tune case-by-case from either final holdout. Freeze a complete development-exposure registry
   before authoring the holdout; the schema-v3 holdout manifest must bind that registry, retain
   canonical case-level source/family commitments, and recompute exact roster overlap rather than
   trusting author-supplied disjointness booleans.
6. Add noise policies for latency metrics and distinguish initial-route JavaScript/CSS/assets from
   lazy map code/assets. Use explicit absolute/relative tolerances, hard budgets, and a
   Vite-manifest dependency graph plus complete emitted-file inventory so timing noise, fonts,
   images, public assets, and deliberate lazy map loading are classified consistently. Retain a
   stable execution-environment fingerprint and reject paired latency when it differs.
7. If the benchmark specification changes during this final ratification, invalidate and recapture
   the entire `before` snapshot once. Freeze it after ratification.
8. Capture the missing eligible paired before evidence: paid public-regression qualification,
   development semantic/retrieval results, the 47-case label-only owner review, five-task UX test,
   and accessibility review. Define deployment templates and gates, but keep preview, distributed
   rate-limit, and rollback proof after-only. Do **not** run sealed retrieval ranks before the final
   candidate.
9. Bind every report to commit, corpus hash, vector hash, benchmark hashes, model identities,
   prompt/config identity, environment, timestamp, and reviewer identity where applicable. The
   environment fingerprint must include OS/release, architecture, CPU identity/count, Python,
   Node, and npm; browser-involved runs must also retain browser/Playwright identity.
10. Create an experiment registry with hypothesis, single intended variable, dev dataset, cost
   ceiling, output paths, result, decision, and rollback.
11. Create an isolated `codex/v1-5-2` branch only after the plan and frozen baseline are accepted.
12. Maintain one gate ledger with `not_run`, `pass`, `fail`, `waived`, owner, artifact, and expiry.
13. Freeze machine-checkable UX sampling rules: cohort/device counts and shares, task outcomes by
    slice, minimum allocations, keyboard/screen-reader coverage, and a maximum 0.15 before/after
    share delta for each registered cohort and device class.
14. Require the after-only deployment summary to bind retained sanitized raw rate-limit and rollback
    artifacts by SHA-256. The raw rollback artifact must contain the canonical restored-state smoke
    observations; reviewer-authored YAML alone is ineligible.
15. Seal the ignored before snapshot with the implemented tracked
    `data/evaluation/upgrade_benchmark_v1_5_2_before_snapshot_seal.json`, which binds its SHA-256,
    candidate/dataset/harness/specification identities, paired metrics, creator, and freeze
    timestamp; after capture and comparison reject an unattested or changed before artifact.
16. Recompute semantic-review, retrieval-review/qualification, and semantic-holdout aggregates from
    retained case-level reports/datasets and review sidecars. Require exact agreement with submitted
    summaries rather than trusting copied totals.
17. At freeze, promote the semantic holdout registry entry to `sealed_release_qualification` and
    `available`, apply every sealed prohibition, and add both its frozen development-exposure
    registry and schema-v3 manifest to `identity_inputs`; a status flip alone is invalid.
18. Add explicit automated/manual WCAG 2.2 AA, visual-state/CSS, named-environment Web Vitals,
    font/image size, total-transfer, third-party-request, and unclassified-asset metrics. UX
    keyboard/screen-reader participant labels remain sampling evidence, not an accessibility pass.
19. Use the frozen `frontend_manual_review.v1` after-only contract for manual frontend release
    evidence. It requires a named accessibility specialist, a distinct named wildfire product-safety
    reviewer, and a third named release adjudicator; exact 30-check criterion roster; five declared
    OS/browser/input/assistive-technology profiles across all ten safety-critical UI states; explicit
    WCAG 2.2 AA success-criterion mappings and contrast/zoom/reflow/target/text-spacing thresholds;
    retained file hashes and byte counts; a readiness-response identity artifact proving the target
    URL and full candidate commit; ordered review/adjudication timestamps; and zero open findings.
    The three scorecard outputs are after-only and must be absent from the before snapshot.
    Eligible capture must launch the frozen browser runner into a fresh capture-owned directory;
    externally supplied self-attested reports are diagnostic only. Retain and gate every applicable
    WCAG A/AA finding, bind the axe engine version, validate screenshot format/dimensions/path
    containment, and inventory every emitted file under the full frontend `dist/` tree.
19. Bind the sealed before candidate to the final candidate's Git ancestry. Reject a comparison
    when the before candidate commit is not an ancestor of the after candidate, when the tracked
    seal is not on that same history, or when the snapshot was sealed from an alternate side
    branch.
20. Add a controlled preview-retention canary: run known response/source strings through the
    preview recorder, retain the separately controlled raw fixture for the test only, and prove
    that the release artifact contains hashes/counts but none of the canary plaintext, private
    headers, source passages, or precise location data.

Exit gate:

- the before snapshot is immutable and complete enough to compare all claimed improvements;
- the V2 exposure has an explicit disposition and the active final holdout has not been ranked as a
  baseline or used for tuning;
- every unknown remains visibly unknown rather than being converted to zero or pass; and
- paired latency cannot compare different environments, paired UX cannot compare materially
  different cohort/device distributions, and deployment assertions cannot pass without their
  hash-bound raw evidence; and
- the ignored before snapshot has a tracked digest attestation, derived aggregates are reproduced
  from case-level evidence, and accessibility/visual-performance claims have their own gates; and
- the sealed before commit and seal are ancestors of the compared candidate, and retained preview
  evidence passes the controlled plaintext-omission canary; and
- the release ledger can reconstruct why each change was accepted.

### W1 — Evaluation, human review, and test-set governance

**Objective:** measure semantic quality, retrieval quality, usability, safety, latency, and cost
without leaking the holdout into tuning.

Tasks:

1. Complete a named owner review of all 50 conversation cases at claim level. Record supported,
   unsupported, unclear, wrong authority, missing condition, misleading freshness, and harmful
   omission. Treat this known set as a permanent regression/development baseline, not as an unseen
   final holdout.
2. Complete the 47-case retrieval owner review for the active dataset against original passages
   before its one-time sealed qualification run. Use V3 if Gate 0 retires V2.
3. Keep the active 47-case sealed retrieval set qualification-only. Any miss creates a versioned new
   experiment and eventually a new holdout; it never triggers case-specific tuning on the sealed
   set.
4. Expand development-only suites by failure family: paraphrase entailment, negation/polarity,
   quantities/dates, scope and authority, mixed static/live, conflicts, stale data, no-result
   language, conversation carryover, and Canadian place ambiguity.
5. Add challenge sets from real human-test failures after adjudication, keeping train/dev/holdout
   identities explicit.
6. Report per-slice results and worst-case failures, not only aggregate pass rate.
7. Run every promoted model/config candidate at least three times where provider variance can
   change the outcome.
8. Record cost per complete question and per stage, p50/p95 latency, retries, 429s, failures, and
   answer/abstention distribution.
9. Blind reviewers to model identity where practical, randomize candidate order, double-review all
   high-risk cases plus a stratified ordinary sample, and adjudicate disagreements before labels
   enter experiments or judge training.
10. Report inter-reviewer agreement and pause experimentation if the rubric is not stable enough to
    produce reliable labels.
11. Create and freeze a new source/question-family-disjoint semantic holdout of at least 25 cases,
    weighted toward high-risk and previously weak slices. Do not reveal its case-level results until
    the final candidate; double-review and adjudicate every case.
12. Build a local blind-review workspace that presents one case and its original source context at
    a time, hides automated verdicts and model identity until the first decision, supports keyboard
    review and disagreement adjudication, autosaves without overwriting prior decisions, and emits
    the canonical hash-bound sidecars. YAML remains the interchange format, not the human interface.
    Retain append-only reviewer/adjudication journals plus a hash-bound presentation-event log so
    blinding is recomputed from what the UI displayed rather than accepted from a `blinded: true`
    assertion. The implemented bundle-v2 validator requires one exact candidate presentation per
    reviewer/case and adjudicator/case, reproducible identity-bound actor ordering, monotonic
    timestamps, a contiguous event sequence and SHA-256 chain, displayed-payload commitments, and
    direct event-digest links from each decision. A nonqualifying local backend scaffold now imports
    blind display-only conversation/retrieval/semantic material, rechecks every source-file identity
    before exposure, enforces two isolated reviewers plus a distinct adjudicator, derives
    deterministic per-actor order, requires display acknowledgement before irreversible decisions,
    and writes receipt-bound private append-only journals. Replay is read-only and journal appends
    reject symlinks, hard links, root/path replacement, partial writes, truncation, and receipt-roster
    rollback. The implemented loopback-only API and same-origin browser client derive actor identity
    from private capability files, do not persist tokens in browser storage, recover only the same
    actor's already-open deterministic case, and expose no ranking/model selector. The preparation
    CLI, frozen runbook, immutable nonqualifying final-evidence export, and verifier are implemented.
    A deterministic content-free post-review analysis now recomputes disposition, rubric, and claim
    agreement, Cohen's kappa where defined, disagreement/finding rosters, adjudicator alignment, and
    unsupported/unclear claim counts from the finalized decision-event hashes. Its immutable receipt
    binds the source evidence and source export receipt, and verification recomputes every metric;
    questions, answers, source passages, and reviewer notes are excluded.
    Session preparation now refuses role labels, model identities, duplicate people, and other
    placeholder reviewer names, so a model cannot silently occupy a human review role.
    A coordinator-only status command revalidates the workspace and reports per-role progress
    without printing capabilities or human decision content.
    The fail-closed gate-sidecar adapter is now implemented for conversation and retrieval reviews.
    It requires a fourth named human, distinct from the session actors, to attest private storage,
    replay, and externally retained final-head controls. It refuses any adjudicated finding and
    emits an atomic content-free package binding all actors/journal heads, disagreements, source,
    export, analysis, attestation, sidecar, and summary hashes. The benchmark now rejects legacy
    semantic/retrieval sidecars without this qualification manifest. No real attestation, external
    anchor, qualifying package, or reviewer evidence exists yet.

Exit gate:

- 50/50 semantic cases reviewed and approved with zero unsupported or unclear material claims;
- the new semantic holdout is fully approved with zero unsupported/unclear material claims and zero
  dangerous omissions;
- 47/47 retrieval cases owner-reviewed;
- sealed Recall@5 at least 46/47 in each of three repetitions;
- 105/105 qualified hard probe with zero critical failures; and
- no critical slice is hidden by a passing aggregate.

### W2 — Semantic evidence compiler

**Objective:** reduce the gap between exact citation correctness and actual claim support.

Tasks:

1. Introduce reviewed atomic claims derived from approved source spans. Store claim text, source
   span/hash, authority, jurisdiction, conditions, temporal scope, risk class, reviewer, and status.
2. Add hash-bound admission so a changed source or changed span quarantines dependent claims.
3. Generate an aspect-support matrix for each candidate answer: action, actor, object, condition,
   quantity/date, jurisdiction, authority, and freshness.
4. Extend deterministic checks for condition removal, polarity inversion, changed quantities or
   dates, authority substitution, temporal overreach, and conflict suppression.
5. Add risk tiers. High-risk current/safety claims require stronger evidence and narrower
   generation freedom than low-risk background explanations.
6. Generate a Proof Card for every grounded response containing accepted claims, exact evidence,
   source authority, source/retrieval timestamps, validation disposition, and limitations.
7. Add ClaimBench cases for every reproduced semantic failure before fixing it.
8. Keep a human adjudication route for cases that deterministic checks cannot decide.

Exit gate:

- every grounded material claim has complete aspect coverage or the answer is partial/abstains;
- every Proof Card can be reconstructed from stored identities;
- source changes quarantine affected claims; and
- ClaimBench has zero critical regressions.

### W3 — Corpus lifecycle and Source Change Radar

**Objective:** turn the reviewed corpus from a static build artifact into a governed, refreshable
system.

Tasks:

1. Resolve the ten quarantined page-repair chunks through owner review; approve, replace, or keep
   excluded with a reason.
2. Define source owners, review cadence, expected update behavior, jurisdiction, and authority tier
   for all eight current sources.
3. Build scheduled source fingerprinting and structural/text diffs without automatically admitting
   changed content.
4. Classify changes as cosmetic, content, authority/URL, removed, or fetch failure.
5. Quarantine changed dependent chunks/atomic claims until review; preserve last-known evidence
   with explicit status rather than silently overwriting it.
6. Add new sources only through a measured corpus admission packet: authority rationale, scope,
   licensing/retention, extraction QA, retrieval impact, semantic review, and rollback.
7. Add novel-document and generalization tests so the pipeline is not validated only against the
   current eight sources.
8. Record ingestion, repair, chunking, embedding, and index lineage in one manifest chain.

Exit gate:

- every production chunk has an approved, current lineage;
- detected source changes cannot silently enter or remain authoritative;
- novel-document extraction and retrieval gates pass; and
- corpus/index reconstruction reproduces the qualified hashes from source inputs.

### W4 — Retrieval, model, prompt, and provider experiments

**Objective:** improve evidence recall and answer quality with bounded experiments, not intuition.

Experiment order:

1. query planning and conversation-context formulation;
2. BM25/vector/fused top-k and RRF `k`;
3. rerank depth and candidate allocation;
4. chunk/context strategy and neighbor window;
5. evidence span limit and context budget;
6. reranker candidates;
7. generation prompt/schema variants;
8. generation model bake-off; and
9. embeddings only if earlier experiments expose a persistent recall problem.

Rules:

- change one intended variable per experiment or use a declared factorial design;
- tune only on development data;
- require identity-bound artifacts and a positive cost budget;
- retain the current candidate unless another candidate improves the targeted metric without
  regressing safety, semantic review, cost ceiling, or latency ceiling;
- do not reward verbosity or generic conversational style over evidence correctness; and
- retain OpenRouter as the provider boundary unless an explicit architecture decision changes it.
- store candidate settings in versioned experiment manifests rather than editing invisible runtime
  defaults between runs.

Provider hardening tasks:

1. honor `Retry-After` within the public deadline;
2. add circuit-breaking and adaptive backpressure by provider stage;
3. expose provider readiness/canary status without leaking secrets;
4. separate embedding, rerank, planning, and generation latency/cost/error metrics;
5. replace local-only attribution headers with environment-specific values; and
6. explicitly test strict fail-closed behavior and any proposed degraded BM25-only mode before
   deciding whether the latter is safe to expose.

Current implementation status (2026-08-08): tasks 1 and 2 are implemented. Numeric and HTTP-date
`Retry-After` delays occur outside both the global and stage-local provider capacity controls,
retain same-model/no-fallback behavior, and are refused when they cannot fit within the public
request deadline. Error status and retry guidance remain typed even when a 429 response body is not
JSON. Embedding, reranking, planning, context-generation, grounded-generation, and background-
generation circuits are isolated; final retryable or invalid-response operation failures open a
bounded cooldown, one half-open probe is admitted, and a fully validated success resets only that
stage. Each stage also has isolated additive-increase/multiplicative-decrease backpressure: a 429
halves that stage's capacity, timeout/unavailability reduces it by one, a configured floor prevents
starvation, and a configured run of fully validated successes restores one permit at a time.
Malformed-but-successful responses do not misclassify semantic/schema failure as upstream load;
cancellation releases capacity. The bounds are environment-configurable and included in benchmark
runtime identity. Readiness reports a content-free provider state without model or secret details.
A real provider canary and production backpressure telemetry remain open.

Exit gate:

- an experiment report names the selected configuration and rejected alternatives;
- selected settings pass W1 gates on an unchanged commit;
- no hidden provider/model substitution occurs; and
- cost and p95 latency remain within owner-approved ceilings.

### W5 — Backend foundation, observability, security, and durability

**Objective:** preserve the strong safety boundary while completing the production foundation.

Current alignment:

| Foundation requirement | Current state | V1.5-2 action |
| --- | --- | --- |
| Deterministic validation owns publication | Aligned | Preserve and extend through W2 |
| Strict typed API contracts | Aligned | Preserve; version only intentional public changes |
| Static/live authority separation | Aligned | Preserve shared typed live service |
| Model/provider identity and bounded retries | Operational-event v2 separates provider model IDs from stage names and records bounded status/count/identity fields. Retry-After is deadline-bounded and same-model; stage-isolated circuits, adaptive stage-local backpressure, and a content-free readiness state are implemented. A real canary and production pressure telemetry remain | Retain v2 schema; add canary and measure backpressure in production |
| Human semantic authority | Policy aligned, operationally incomplete | Complete W1 and review tooling |
| Durable traces/analytics | Content-free v2 events are ready for a platform log drain, but local traces remain files/ephemeral `/tmp` and no sink, retention, access, or sampling proof exists | Configure and verify a privacy-safe durable event/trace sink |
| Global public quota | Not aligned; application reports `instance_local` | Verify external distributed enforcement |
| Shared cache/state | Partial; in-process caches | Add only where load/SLO evidence justifies it |
| Reproducible deployment artifact | Packaging source aligned to the shared contract: Vercel uses narrow runtime globs and a generated commit-bound candidate; Docker ships repair governance, app entrypoint, runtime contract, built frontend, and the same candidate schema. Real extracted artifacts, platform provenance, and runtime identity observation remain unproven; Docker is unavailable locally. Document context is conditional rather than currently missing | Pass both isolated extracted roots through the same capture-owned allowlist/inventory gate, then bind platform export provenance and observed readiness identity |

Supply-chain status (2026-08-08): task 12's repository and candidate-evidence portion is now
implemented. The manual candidate workflow is action-SHA pinned, runs the full zero-cost verifier,
creates a CycloneDX 1.6 SBOM, an in-toto/SLSA v1 provenance statement, dependency/license reports,
and a closed hash manifest, and refuses unbound or mutated inputs. The normal verifier also runs on
`main` pushes. A real local audit initially found three Python advisories and four high npm
advisories; the locked `cryptography`, `pypdf`, `brace-expansion`, `js-yaml`, and `nanoid` versions
were advanced to their fixed releases. Re-audit found no known Python vulnerabilities and zero npm
vulnerabilities, and the resulting local candidate bundle passed its independent verifier. This is
local implementation evidence, not a CI artifact, signed attestation, container/infrastructure scan,
or frozen release candidate.

Tasks:

1. Define structured operational events for route, mode, stage latency, cache status, provider
   model, retry/error class, evidence count, validation disposition, corpus/version identity, and
   coarse success outcome. Do not log answer/query content by default.
2. Send privacy-safe events and traces to a durable sink with retention, access, sampling, and
   deletion policy. Keep content tracing separately opt-in.
3. Add request and stage SLO dashboards for availability, p50/p95, provider errors/429s,
   abstentions, live-source partial failures, cache hit rate, and cost.
4. Add startup/readiness checks for every required runtime input, including repair governance files
   and any evidence-compiler manifests.
5. Fix the Docker/Render artifact: `Dockerfile` currently omits
   `data/repairs/text_overrides.yaml` and `data/index/document_context_v2.jsonl`, which the runtime
   governance/configuration paths require. Add a built-image readiness smoke so this cannot recur.
6. Keep application rate limiting as a local safety guard, but enforce and verify a distributed
   limit at the platform edge for public routes.
7. Evaluate a shared cache only after measuring duplicate provider/live calls across instances.
   Use bounded TTLs and include model/config/corpus/location identities in cache keys.
8. Add dependency timeouts, budgets, bulkheads, and cancellation propagation for each paid/live
   stage.
9. Add misuse, oversized-body, proxy-spoofing, prompt-injection, data-exfiltration, and dependency
   outage tests to the permanent suite.
10. Normalize geocoder HTTP, JSON, conversion, empty-result, and cancellation failures into typed
    live-data outcomes so a place-resolution dependency cannot escape as an unexplained 500.
11. Profile cold start and warm static/live traffic at concurrency 1, 5, 20, and 50. Record route- and
    mode-specific p50/p95/p99, error rate, queue time, memory, and provider cost before choosing
    final edge limits.
12. Add container and infrastructure scanning, an SBOM/provenance artifact, and a candidate gate for
    unwaived high/critical findings while preserving pinned Actions, lockfiles, and secret scans.
13. Verify OpenRouter project-key scope, hard spend cap, and alerts outside the repository without
    recording the key itself. Record the zero-data-retention decision explicitly.
14. Do not add a general application database simply because this is a broad upgrade. Add durable
    storage only for an accepted need such as feedback/review records or telemetry, and define
    retention, deletion, backup, and restore before collecting user data.
15. Maintain the implemented shared runtime-artifact allowlist for Vercel and Docker/Render. Include only the
    production corpus/index/manifests, human-verified runtime repair provenance, frontend bundle,
    and required runtime code/config; include document context only when the frozen strategy
    selects `document_context_v2`. Explicitly exclude `data/evaluation/**`, owner-review material,
    benchmark outputs, and sealed case payloads. The benchmark now inventories explicit staged
    Vercel and Docker roots before and after all capture commands, retains capture-owned reports,
    and fails on missing/prohibited inputs, symlinks, mutation, or identity mismatch. Fix the actual
    packaging until both artifacts pass. The production container
    must avoid eager lab/benchmark imports, prove the frontend is present, and keep evidence inputs
    read-only under its non-root user.

Exit gate:

- preview demonstrates durable, privacy-safe telemetry and correct candidate identity;
- distributed rate limiting is proven across instances;
- built Vercel and Docker artifacts both become ready with the same required inputs;
- built-artifact inventories match the shared allowlist and contain no evaluation or sealed payload;
- dependency failures remain explicit and fail closed; and
- SLO and cost alerts are tested, not only configured.

### W6 — Official live-data and near-me service

**Objective:** make current wildfire discovery fast and understandable without weakening official
source/freshness rules.

Tasks:

1. Add a dedicated typed near-me endpoint or query contract returning map viewport, requested
   radius, resolved coarse location, official records by layer, freshness, retrieval timestamps,
   unavailable layers, and official fallback URLs.
2. Keep chat and map backed by the same live service and verify matching IDs/statuses.
3. Make radius explicit and adjustable within safe bounds; never imply that no records means no
   danger.
4. Preserve coarse-location privacy: request permission at the user action, round coordinates,
   explain session use, avoid background collection, and define whether any location-derived
   event is retained.
5. Test ambiguous community names, boundary locations, empty results, stale cache, partial layer
   outage, total outage, pagination, malformed geometry, and upstream schema drift.
6. Measure cold and cached p50/p95 by layer and region; add upstream availability/freshness SLOs.
7. Decide whether a distributed live cache is needed from measured cross-instance load and official
   service constraints, not as a default complexity increase.
8. Replace the unbounded exact-bounding-box in-process live cache with a size-bounded policy and
   normalized BC viewport keys; cap returned records/geometry and test adversarial viewport churn.
9. Fetch independent official layers concurrently under one bounded upstream budget when testing
   proves it preserves partial-layer behavior and official-service constraints.
10. Replace direct browser-to-third-party tile requests with a same-origin cached tile path or a
    tile-free local BC basemap, preserve required attribution/terms, and prove that every returned
    record remains available in the keyboard/screen-reader list rather than silently truncating it.

Current implementation status (2026-08-08): the in-process cache now expands viewports onto stable
0.1-degree keys, filters results back to the exact requested bounds, enforces both LRU entry and
total-feature budgets, and has adversarial churn coverage. Independent official layers now fetch
concurrently through one bounded upstream semaphore, with existing partial-layer failure tests
retained. Geocoder HTTP, timeout, connection, JSON, conversion, empty-result, and out-of-BC failures
are sanitized and typed; cancellation propagates. A dedicated `POST /api/v1/live/nearby` contract
now returns the coarse resolved location, requested radius/layers, computed viewport, aggregate
freshness, unavailable layers, official fallbacks, and a bounded 1–200-record page with explicit
total/next/previous metadata. The service retains and paginates the complete matching roster rather
than silently truncating the accessible list; out-of-range pages are explicit. Response geometry
payloads now fail closed against both per-feature and per-response byte ceilings before entering
the cache. The official live qualification evidence is now schema v2: it exercises the typed Near
Me route on a fixed coarse BC location and lets the benchmark recompute its request, viewport,
pagination, returned-page roster, unavailable-layer state, and official fallback contract.
A frontend follow-up removed the separate eight-record rendering slice, so every returned API
record now remains in the keyboard/screen-reader list and the 10/10 fixture parity gate passes.
Direct browser tile traffic remains unresolved: OSM discourages casual proxies and requires
contactable identification plus cache compliance, so a provider/cache decision is required before
implementing a same-origin path.
A hash-bound diagnostic SLO harness now measures cold/cached p50/p95, availability, stale-layer
observations, freshness coverage, and authoritative layer-update age by official layer and three fixed coarse BC regions; its
verifier reconstructs the complete observation roster and summaries. The protocol deliberately
keeps thresholds null and qualification false until owner ratification. Real scheduled production
measurements, distributed cache evidence, and the same-origin/tile-free map decision remain open.

Exit gate:

- near-me records, list, chat, and map agree;
- the browser leaks neither user IP nor viewed tile coordinates to an undeclared map provider, and
  the accessible list exposes the complete record roster or explicit pagination;
- all failure/freshness states are explicit;
- the same five-task UX protocol shows faster, safer comprehension; and
- official-source verification remains one action away.

### W7 — Frontend architecture and visual system

**Objective:** create a modern, calm, map-capable product without turning every object into a card.

Tasks:

1. Split the 593-line `App.tsx` into task shell, conversation, composer, evidence inspector, map
   workspace, live record sheet, status/failure, and shared state/API modules.
2. Introduce an explicit state model for task (`ask`/`near-me`), request, conversation, selected
   claim, evidence inspector, map viewport, location consent, and errors. Preserve abort behavior.
3. Establish design tokens for type, spacing, color, motion, focus, elevation, and responsive
   breakpoints. Raise body and metadata text to readable sizes; the current CSS uses many 8–11 px
   labels.
4. Replace box-heavy cards with hierarchy created by whitespace, typography, dividers, anchored
   rails, map overlays, and progressive disclosure.
5. Build desktop as an adaptive canvas: focused conversation/evidence for Ask and expanded map with
   contextual side rail for Near Me.
6. Build mobile as task tabs plus full-screen map/list with an accessible bottom sheet; avoid a
   long compressed evidence/map column.
7. Keep the map lazy-loaded and measure initial-route and interaction bundle budgets separately.
8. Fix the current desktop map-heading clipping and the misleading `{history.length} of 6 turns`
   label, which counts messages rather than user/assistant exchanges.
9. Add visual regression coverage for idle, grounded, partial, abstention, provider failure, live,
   mixed, stale, no-result, and partial-layer states at mobile/tablet/desktop sizes.
10. Add CSS/layout integrity checks and measure Core Web Vitals under a frozen browser, device,
    network, and runner profile. Keep these gates separate from participant UX scores and raw bundle
    size.
11. Remove unused font subsets/formats, resize or replace the oversized logo, classify every emitted
    asset, and enforce initial/lazy CSS, font, image, total-transfer, and browser-request budgets.

Exit gate:

- no critical clipping, overflow, unreadable metadata, or hidden failure state at supported sizes;
- initial Ask remains fast while Near Me map code loads on demand;
- every main state has deterministic browser coverage; and
- frozen visual-state/CSS gates and named-environment Web Vitals pass; and
- design review confirms the interface no longer depends on repeated boxed cards for hierarchy.

### W8 — End-to-end user experience, accessibility, feedback, and analytics

**Objective:** prove that people can complete the important tasks and understand the product's
evidence and limitations.

Tasks:

1. Put Ask and Near Me at the top-level entry point. Do not bury location below the general chat
   composer.
2. Add a near-me onboarding sequence: choose community or coarse location, understand radius and
   freshness, view records, inspect an official record, and move to the official source.
3. Redesign evidence inspection around claim -> support -> original source, with plain-language
   authority, date, freshness, and limitation cues.
4. Add copy-tested failure recovery for provider failure, stale data, partial layer outage, no
   results, out-of-scope questions, and unsupported answers.
5. Add accessible map alternatives: keyboard-operable record list, visible focus, non-color status
   encoding, screen-reader summaries, escape/focus behavior for sheets, and reduced-motion mode.
6. Run WCAG 2.2 AA automated checks plus manual keyboard, VoiceOver, zoom/reflow, contrast, target
   size, and live-region tests. Retain all applicable automated findings rather than filtering by
   impact level, and pin the engine/rule-set identity. Final manual evidence requires three distinct
   named roles: accessibility specialist, wildfire product-safety reviewer, and release
   adjudicator. Every frozen atomic criterion needs a retained hash-bound artifact; a failed check
   or open finding cannot be adjudicated into a pass.
7. Add explicit answer/evidence feedback that records the response/trace identity and category, not
   only thumbs up/down. Route safety/evidence concerns into the human-review queue.
8. Add privacy-safe product events for task start/completion, time to map, evidence opened, official
   link opened, failure/recovery, and feedback. Do not capture precise location or raw conversation
   content by default. Test the location boundary against the full request roster, URL/history,
   cookies, local/session storage, IndexedDB, Cache Storage, and service-worker state.
9. Decide on session persistence/share only after a privacy and evidence-staleness design. Shared
   links must preserve or disclose the original evidence identity and freshness.
10. Preserve the frozen sampling frame in both rounds: at least four novice BC residents, four
    wildfire-aware participants, three desktop and three mobile participants, plus keyboard and
    screen-reader coverage. Retain cohort/device counts, shares, and task outcomes; reject a pair
    when any cohort or device share differs by more than 0.15.
11. Define frozen criterion IDs and critical-error codes for every task, derive completion from the
    criteria rather than a moderator-entered boolean, allow multiple assistive access methods, and
    score an unsuccessful Near Me attempt at the 120-second task cap instead of rewarding fast
    failure.
12. Report task-by-core-cohort and task-by-device worst slices plus Wilson intervals and a seeded
    participant bootstrap for completion and Near Me timing. If the timing interval crosses no
    effect, describe the result as an observed sample difference rather than an established gain.

Implementation status: the private packet generator now creates the complete blank 30-check/50-cell
accessibility and product-safety roster for three distinct named humans, and the UX v3 validator
implements tasks 10–12, including multiple access methods, derived completion, the Near Me failure
cap, Wilson intervals, worst core-cohort/device slices, and deterministic round/effect bootstraps.
These are reviewer-operational controls, not evidence that any human review has occurred.

Map/accessibility diagnostic status (2026-08-08): the complete result roster is present in both the
map and accessible list, and a locally bundled simplified Government of BC boundary has replaced
all third-party runtime basemap tiles. The final 30-row diagnostic passed every automated surface
row, all functional journeys, and both lab-performance profiles with zero direct tile-host calls,
axe A/AA findings, undersized text/targets, or parity failures. The boundary is orientation context
only. The provisional protocol and missing named-human sessions still prevent qualification.

Exit gate:

- at least 90% aggregate completion across the frozen five tasks;
- zero critical task errors;
- the before/after cohort and device distributions satisfy the frozen comparability rule and no
  critical slice is hidden by the aggregate;
- every eligible round has 12 real participants; smaller runs remain pilots rather than release
  evidence;
- near-me median completion time improves from the measured before baseline;
- all participants notice stale/partial/unavailable states in UX04; and
- automated WCAG plus the named manual keyboard/VoiceOver/zoom/reflow/contrast/target-size/live-
  region review pass with retained evidence, and no critical screen-reader defect remains.

### W9 — CI/CD, preview, deployment, and recovery

**Objective:** promote exactly the artifact that passed qualification and prove that it can be
recovered.

Tasks:

1. Keep PR verification and weekly dependency security jobs, then add a candidate workflow that
   packages identity-bound artifacts, benchmark summaries, SBOM/license evidence, and deployment
   manifests.
2. Run required zero-cost verification on protected main-branch pushes as well as pull requests and
   manual dispatches; keep paid qualification behind an explicit protected approval.
3. Add built-artifact smokes for Vercel and Docker/Render paths; choose one canonical production
   platform and treat the other as a tested portability target or retire it explicitly. For both,
   supply isolated extracted roots, exact artifact IDs, and exact platform roots to the implemented
   capture-owned runtime inventory gate. It asserts the shared allowlist, required
   governance/context files, the absence of `data/evaluation/**` and sealed case payloads,
   cross-platform logical identity, candidate-commit identity, and pre/post-capture immutability.
4. Deploy an owner-approved anonymous preview from the frozen candidate commit.
5. Run readiness, homepage, grounded, partial/abstention, live, mixed, stale/no-result, error, 413,
   429, keyboard map, mobile, accessibility, and official-link checks.
6. Publish and verify platform-level rate limiting; record rule/deployment IDs and cross-instance
   behavior in a retained sanitized raw artifact whose SHA-256 is recorded in the deployment
   summary.
7. Rehearse rollback by promoting a previously verified deployment, validating restored identity,
   and recording the exercise without deleting the failed candidate. Retain the raw rollback
   artifact, including candidate/restored identities and canonical restored-state smoke checks, and
   bind its SHA-256 in the deployment summary.
8. Promote the already-qualified preview artifact rather than rebuilding production.
9. Run post-promotion readiness and real static/live smokes, then monitor the release against SLOs
   and rollback thresholds.

Implementation status (2026-08-08): tasks 1 and 2 are implemented for the repository workflow.
`.github/workflows/candidate.yml` is manual-only, uses pinned Actions, builds and verifies the
commit-bound candidate evidence bundle, uploads it even when the security gate fails, and performs
no deployment or paid qualification. `.github/workflows/verify.yml` now covers protected
`main`-branch pushes. A local evidence bundle passed after live advisory remediation, but the
candidate workflow has not run in GitHub and tasks 3–9 remain open.

Exit gate:

- preview qualification passes anonymously on the frozen commit;
- distributed rate limiting and rollback are reproduced with deployment IDs and hash-bound raw
  artifacts;
- production identity equals the qualified candidate identity; and
- no critical post-deploy regression appears during the declared observation window.

### W10 — LLM judge and fine-tuning decision

**Objective:** learn whether a judge can reduce review effort without becoming an unsafe authority.

Position:

- first use a strong general model as a structured offline judge;
- never expose judge output to users or let it override deterministic validation;
- compare it with adjudicated human labels, including disagreements and high-risk negative cases;
- use it initially for queue ordering, duplicate clustering, and second-review suggestions only;
- do not fine-tune merely because a fine-tuning path exists.

Experiment:

1. Define a strict judge schema: claim/evidence IDs, support disposition, missing aspect, authority,
   freshness, severity, rationale span, and confidence.
2. Build a separate adjudicated dataset from owner reviews and newly collected development cases.
   Do not train on the sealed release holdout.
3. Blind the judge to the existing automated verdict and measure agreement against two-human
   adjudication where practical.
4. Report per-class precision/recall, unsafe false-pass count, calibration, Cohen's kappa, latency,
   and cost. Overall accuracy alone is insufficient.
5. Require at least 95% recall on unsupported/unclear high-risk claims, kappa at least 0.80, and zero
   critical false passes on the untouched judge test set before using it even for automated triage.
6. Fine-tune a judge only if a general judge misses a stable, learnable error family and there are at
   least 500 adjudicated claim units with at least 100 meaningful negative/high-risk examples and a
   document/source-disjoint test split.
7. Fine-tune the conversation model only if W1/W4 evidence shows a persistent error that prompt,
   retrieval, schema, or corpus changes cannot solve, and a separate dataset with enough approved
   conversations exists. Re-run every release gate afterward.
8. Before any fine-tune, complete training-data licence/privacy review, near-duplicate and
   group/source leakage checks, immutable rubric/base-model/checkpoint lineage, calibration with
   confidence intervals, and explicit requalification triggers for corpus, rubric, or base-model
   changes.
9. Confirm that the chosen checkpoint can be served through the approved OpenRouter provider
   boundary with stable model identity, retention terms, cost accounting, and rollback. If it
   cannot, treat a new hosting/provider path as a separate architecture and security decision, not
   as a tuning detail.

Exit gate:

- a written `adopt for shadow triage`, `continue research`, or `reject` decision is supported by an
  identity-bound report;
- human review remains final release authority; and
- no fine-tuned model enters runtime without a separate architecture decision and full benchmark.

## 6. Target frozen before/after scorecard

The benchmark is multi-track. No weighted composite score should allow a UX gain to hide a safety
loss or a retrieval gain to hide an unsupported claim.

| Metric | Before | Required V1.5-2 disposition |
| --- | ---: | --- |
| Full verification | Every stage observed passing across current runs; no single final uninterrupted run after all Gate 0 edits yet | Pass on the frozen before and unchanged final candidate, no critical regression |
| Before-snapshot seal | Mechanism implemented; no eligible v2 snapshot has been sealed | Tracked seal verifies snapshot SHA-256 plus candidate/dataset/harness/spec/paired-metric/owner/freeze identities |
| Offline hard probe | 105/105 | 105/105, zero critical failures |
| Offline p95 | Legacy diagnostic 20.3 ms | Compare only under an exact stable environment match, then apply the ratified noise tolerance |
| Execution environment | Not retained completely by the legacy snapshot | Same OS/release, architecture, CPU identity/count, Python, Node, and npm for paired latency; browser identity where applicable |
| Initial-route JS gzip | Diagnostic 73,547 B | <= 80,000 B and no material growth beyond the ratified 2,048 B / 3% tolerance |
| Lazy JS gzip | Diagnostic 46,422 B | <= 55,000 B and no material growth beyond the ratified 4,096 B / 10% tolerance |
| Initial/lazy CSS gzip | Diagnostic 5,090 B / 6,453 B | Each <= 8,000 B and within ratified paired tolerance |
| Emitted font assets | Diagnostic about 869 KB | <= 200,000 B; only required languages/formats/weights emitted |
| Emitted image assets | Diagnostic 808,528 B logo | <= 100,000 B total and every image classified |
| Frontend state/accessibility matrix | Follow-up diagnostic 30/30 executed, 18/30 qualified; zero axe A/AA, text-size, target-size, styled-control, overflow, clipping, or map/list parity failures; 12 map-bearing rows remain unqualified on tile transport | 30/30 state-viewport rows; zero applicable WCAG A/AA, layout, clipping, or unexpected-console failures under the pinned engine/rule set |
| Lab browser performance | Diagnostic worst viewport: LCP p75 828 ms, CLS p75 0.01692, INP proxy p75 30.6 ms, map-ready p75 829.9 ms on the recorded Apple M5/Chromium lab profile | Worst-viewport LCP p75 <= 2.5 s, CLS p75 <= 0.10, INP proxy p75 <= 200 ms, map-ready p75 <= 2 s under the exact frozen profile |
| Browser map privacy and parity | Accessible roster parity is now 10/10, but the follow-up still records 200 direct OSM tile requests and 40 aborted tile requests | Zero third-party tile/map requests; attribution and complete or explicitly paginated accessible record parity preserved |
| Official live qualification | Legacy diagnostic: pass | Pass; chat/map identity match |
| Cached live p95 | Legacy diagnostic ~381.1 ms | <= 4 s gate and no material ratified regression under matching environment identity |
| Qualified hard probe | Not run | 100%, zero critical failures, cost within approved cap |
| Development retrieval gap | Current historical reports are identity-ineligible | Paired before/after Recall@5, MRR@5, nDCG@5, source coverage, and cost on the reviewed 50-case development set |
| Sealed retrieval | V2 had a temporary fake-provider test ranking; no persisted/live/paid result observed; disposition unresolved | Active set is a required-after-only final gate; Recall@5 >= 46/47 in every one of 3 repetitions |
| Semantic owner review | Missing | 50/50 approved; zero unsupported/unclear material claims |
| Source-disjoint semantic holdout | Not yet created | At least 25/25 adjudicated approvals; zero unsupported/unclear material claims or dangerous omissions |
| Retrieval owner review | Missing | 47/47 reviewed and approved |
| Derived-evidence recomputation | Missing | Case-level recomputation exactly matches every semantic/retrieval/holdout summary |
| UX task completion | Missing | >= 90% aggregate and report each task/cohort |
| UX critical errors | Missing | 0 |
| Near-me completion | Missing | Improve median from frozen before run |
| UX cohort/device comparability | Missing | Frozen minimum allocation, slice outcomes retained, and <= 0.15 share delta for every cohort/device class |
| Accessibility / visual / Web Vitals | Missing | Automated and manual WCAG pass, frozen visual/CSS states pass, and named-environment Web Vitals meet ratified budgets |
| Manual accessibility and product-safety review | No real review bundle exists; the frozen protocol and fail-closed validator are implemented | After-only `frontend_manual_accessibility_qualified=true`, `frontend_manual_product_safety_qualified=true`, and `frontend_manual_open_findings=0` on the exact commit-derived candidate; all 30 atomic checks and 50 profile/state cells retain hash-bound evidence under three distinct named roles |
| Anonymous preview | Missing | Qualified on exact candidate |
| Distributed rate limit | Missing | Verified across instances |
| Rollback rehearsal | Missing | Reproduced with deployment IDs |
| Raw deployment proof | Missing | Sanitized rate-limit and rollback artifacts retained and SHA-256-bound to the reviewed summary |
| Runtime artifact boundary | Staged logical-bundle contract and after-only benchmark gate implemented; no real staged pair has passed. The verifier rejects fake entrypoints, invalid NPY payloads, loose corpus/vector schemas, hard links, in-flight mutation, unreachable Vite entries, and missed side-effect/worker imports. Source packaging now includes repair governance and a shared commit-bound runtime candidate while narrowing Vercel inputs. Real Vercel extraction, Docker build/extraction, platform-export provenance, and runtime-sidecar observation remain explicit blockers | Capture-owned Vercel and Docker inventories match one allowlist, include every required runtime input (document context conditional on the frozen strategy), exclude evaluation/sealed payloads, remain byte-identical across the capture, bind immutable platform exports to the exact candidate commit, and observe the same candidate identity from the running readiness endpoint |

## 7. Human testing protocol

### Semantic review

- Review all 50 conversation cases at claim level.
- Show source context and exact quote, but hide automated verdicts during initial labeling.
- Use explicit reason codes and reviewer identity.
- Adjudicate every disagreement or unclear claim.
- Treat material unsupported content as a release blocker, even if the response is otherwise useful.
- Use the known 50-case set for permanent regression and paired improvement. Qualify the final
  candidate separately on the new source/question-family-disjoint semantic holdout.

### Retrieval review

- Review all 47 cases in the active sealed dataset against original source passages. If V2 is
  retired, this means the fresh V3 set.
- Complete named, timestamped owner review before the one-time three-repetition model run.
- Do not rank the active sealed set for the before snapshot or expose its results to development
  tuning.
- Do not describe V2 as untouched or unseen: its fake-provider test ranking is part of the
  qualification record even though no persisted/live/paid result was observed.
- Use a different reviewed development retrieval set for paired before/after improvement claims.

### Usability benchmark

- Run the same five tasks defined in `upgrade_benchmark_v1_5_2.yaml` before and after.
- Use the same moderator script, task order policy, devices, success rubric, and comparable
  independent cohorts.
- Require at least four novice BC residents and four wildfire-aware participants, at least three
  desktop and three mobile participants, and at least one keyboard and one screen-reader
  participant in each round.
- Record completion, critical error, time, confidence, evidence comprehension, freshness
  comprehension, and official-source escalation.
- Add a wildfire/domain expert review for dangerous ambiguity and one accessibility specialist pass.
- Require 12 participants per eligible round with matched independent cohorts. Runs with 8–11 may
  be retained as pilots but cannot establish the release before/after claim.
- Retain counts, shares, and task outcomes by cohort and device. Reject the comparison when any
  registered cohort or device share differs by more than 0.15 between rounds; access-method
  coverage must be present in both rounds but is not share-balanced.
- Require each task to reach at least 80%, median Single Ease Question score at least 5/7, and at
  least 90% correct comprehension of evidence support plus stale/no-result meaning.
- Target Near Me median completion at or below 45 seconds and at least 25% faster than its frozen
  before baseline.

Five frozen tasks:

1. ask a preparedness question and inspect exact support;
2. find wildfires near a named BC community;
3. distinguish an evacuation alert from an order;
4. interpret stale or partially unavailable live data; and
5. recover from provider or live-source failure.

## 8. Execution waves and gates

### Wave 0 — Freeze release truth

Deliver the V2 disposition, semantic-holdout manifest, W0 dataset-role correction, environment and
UX-comparability enforcement, raw deployment-evidence binding, tracked baseline attestation,
case-level aggregate recomputation, explicit accessibility/visual/Web Vitals gates, benchmark
ratification, eligible missing before measurements, owner decisions, and branch setup.

**Gate 0:** no product tuning begins until the ruler and candidate identity are frozen and the
V2 exposure has been dispositioned, while the active final holdout has not been ranked as a baseline
or used for tuning. The v2 harness must reject mismatched latency environments, materially different
UX cohort/device distributions, and deployment summaries without their hash-bound raw artifacts. If
a paid budget or reviewers are not yet available, zero-cost implementation may proceed only if
those baseline fields remain explicitly missing and no improvement claim is made for them.

### Wave 1 — Close foundation blockers

Deliver the Docker governance-input fix, artifact readiness smokes, telemetry schema, distributed
rate-limit design, pass the implemented shared runtime-artifact gate on real staged builds, experiment registry, and
human-review operations.

**Gate 1:** both deployment artifacts become ready; review packets are usable; no safety boundary
has weakened.

### Wave 2 — Evidence and corpus integrity

Deliver atomic claims, aspect checks, Proof Cards, ClaimBench, Source Change Radar, repair decisions,
and novel-document tests.

**Gate 2:** all production evidence has approved lineage, semantic critical tests pass, and changed
sources quarantine dependent evidence.

### Wave 3 — Retrieval/model/provider tuning

Run the ordered W4 experiments on development sets. Select one candidate configuration and freeze
it.

**Gate 3:** the selected candidate improves its target metric without a safety, semantic, cost, or
latency regression. Paid runs require the approved ceiling.

### Wave 4 — Frontend and near-me experience

Deliver the component/state refactor, modern visual system, map-first workflow, accessibility,
feedback, and product events.

**Gate 4:** responsive, accessibility, browser-state, and repeated five-task UX gates pass; the
interface is not promoted from screenshots alone.

### Wave 5 — Frozen candidate qualification

On one unchanged commit, run full verification, qualified hard probe, sealed retrieval, semantic
review, retrieval review, and live qualification. Deploy that same commit to an anonymous preview,
prove the distributed controls against that preview, and rehearse rollback. Only then complete the
after snapshot and comparison so every required after-only deployment metric and its retained raw
evidence are present.

**Gate 5:** required after metrics are present, thresholds pass, no critical or material regression
is accepted, and reviewers sign the reports.

### Wave 6 — Promotion and observation

Obtain explicit owner promotion approval, promote the already-qualified preview artifact without a
rebuild, verify production identity, run post-promotion smokes, and observe declared SLO and rollback
thresholds.

**Gate 6:** production is the already-qualified artifact, post-deploy checks pass, and rollback
remains immediately available.

## 9. Stop conditions

Stop the affected workstream and record a failed gate when any of these occurs:

- frozen evaluation inputs or benchmark rules change after implementation begins;
- the before snapshot lacks a valid tracked attestation or its digest changes;
- the V2 exposure has no explicit owner disposition when Gate 0 is presented as accepted;
- a candidate is tuned against the active sealed holdout;
- the active sealed retrieval ranks are run as a before measurement;
- a material unsupported claim passes as grounded;
- a submitted aggregate disagrees with recomputation from its retained case-level evidence;
- a source/corpus change lacks owner approval or reproducible lineage;
- a built runtime artifact omits a required governance/context input or contains
  `data/evaluation/**`, owner-review material, or a sealed case payload;
- provider/model identity differs from the recorded configuration;
- paired latency environments differ, or required environment fields are missing;
- before/after UX cohort or device shares violate the frozen comparability rule;
- cost reaches the approved ceiling;
- a dependency failure produces invented or silently substituted output;
- chat and map disagree on current official records;
- a critical UX participant mistakes stale/no-result output for safety;
- UX access-method coverage is represented as an accessibility pass without the separate automated
  and manual WCAG evidence;
- preview identity differs from the qualified commit; or
- a deployment control is supported only by a reviewer-authored summary rather than its hash-bound
  raw rate-limit or rollback artifact; or
- rollback cannot restore and verify the previous deployment.

## 10. Owner decisions and dependencies

The following are not safe to infer and must be decided before their dependent gates:

| Decision | Needed for |
| --- | --- |
| Retire exposed V2 to regression and create V3 (recommended), or retain V2 with a weaker explicit claim | W0, W1, Gate 5 |
| Maximum OpenRouter budget for before, experiments, and after qualification | W0, W1, W4, W10 |
| Named semantic and retrieval reviewers/adjudicator | W1, W10 |
| UX participant recruitment and accessibility specialist | W8 |
| Canonical production platform: Vercel; Render as portability target or retired path | W5, W9 |
| Durable telemetry/product analytics service, retention, and privacy policy | W5, W8 |
| Distributed edge-rate-limit thresholds and observation window | W5, W9 |
| Whether session persistence/share is wanted | W8 |
| Promotion approval after Gate 5 qualification | Gate 6 / production release |

Proposed caps for owner approval, not authorization already granted: up to **$4.00** for the frozen
before baseline (qualified hard probe $1.25 + development retrieval $1.25 + conversation benchmark
$1.50), an initial **$5.00** experiment tranche before any additional tranche is considered, up to
**$4.75** for final repeated qualification (the same $4.00 plus $0.75 sealed retrieval), and a
separate **$2.00** offline judge pilot only after human labels exist. Commands must still stop at
their smaller per-run ceilings, and unused budget does not transfer automatically.

## 11. Definition of done

V1.5-2 is complete only when all of the following are true on the same unchanged candidate commit:

1. the full zero-cost repository verification passes;
2. the after snapshot compares against the tracked-digest-attested immutable before snapshot with
   all required fields and an eligible matching execution environment for paired latency;
3. the 105-case qualified hard probe passes with zero critical failures;
4. the V2 exposure has a recorded disposition, and the accepted active sealed retrieval set reaches
   at least 46/47 Recall@5 in all three repetitions without baseline ranking or tuning exposure;
5. named owners approve all 50 semantic and 47 retrieval cases, with zero unsupported/unclear
   material claims, and the new source-disjoint semantic holdout also passes with zero material or
   dangerous-omission failures; all submitted aggregates exactly match case-level recomputation;
6. the five UX tasks reach at least 90% completion, zero critical errors, and improved near-me time
   under cohorts/devices that satisfy the frozen minimum allocations and 0.15 share-delta rule;
7. automated and manual WCAG, frozen visual-state/CSS, named-environment Web Vitals, and dangerous-
   ambiguity reviews pass with retained evidence, distinct named manual-review roles, and zero open
   findings;
8. the corpus, index, prompt/config, models, commit, environment, and reports have reconstructable
   identities;
9. anonymous preview, distributed rate limiting, and rollback rehearsal pass, with sanitized raw
   rate-limit and rollback artifacts retained and SHA-256-bound to the reviewed summary;
10. Vercel and Docker/Render artifact inventories match the shared runtime allowlist, contain all
    required governance/context inputs, and exclude evaluation/owner-review/sealed payloads;
11. production is promoted from the verified preview artifact and reports the expected identity;
12. post-deploy static/live smokes and observation checks pass; and
13. the owner explicitly approves promotion.

## 12. Persistent goal objective

Execute this V1.5-2 plan gate by gate while preserving FireLens's evidence-first architecture.
Freeze and complete the before benchmark, close backend/deployment foundation gaps, establish human
semantic/retrieval/UX baselines, implement evidence/corpus and provider hardening, modernize the Ask
and Near Me experiences, qualify one unchanged candidate against every required before/after gate,
and promote only the already-qualified artifact after anonymous preview, distributed-control, and
rollback proof. Keep any LLM judge offline/shadow and do not fine-tune or deploy it without the
explicit W10 evidence and decision gate.
