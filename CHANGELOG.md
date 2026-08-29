# Changelog

## Unreleased — V1.6.2

### Changed

- Improved scope recall without broadening factual authority: ordinary
  conversation remains labelled general background, wildfire guidance reaches
  its reviewed lane, and safety-sensitive questions receive a bounded official
  check or handoff instead of an unrelated-record response.
- Normalized qualified B.C. locality wording before live resolution, bound
  closest/ordinal results to a selected official record ID, and kept unrelated
  typed claims out of a requested aspect.
- Added deterministic multi-record summaries, concurrent mixed-lane prefetch,
  and answer-first presentation that opens analysis or map views only when they
  serve the request.
- Rejected quote-only spans that interleave headed evacuation alert, order, and
  rescind stages. They now fall back to the existing official handoff rather
  than being rewritten or published as a single proposition.
- Added ProductBench v2's executable development contract and the V1.6.2
  Product Constitution/evaluation framework for contract-based repair and
  falsification.

### Known limits

- PB15-style source-extraction defects remain source-repair work. An unreadable
  exact span is omitted or handed off; it is not converted into FireLens advice.
- This section describes an uncommitted local engineering candidate. Exact Git
  qualification, paid evaluation, human review, live/production verification,
  and release authorization are not established here.

## Unreleased — V1.6 RC2

### Changed

- Made immutable `AgentQueryPlan` the sole authorization for public Ask tools,
  live layers, geography, selected records, and reviewed-guidance subrequests.
  Provider requests outside that plan, including repeats, are rejected.
- Made default local traces content-minimized: no question, answer, history,
  coordinates, evidence text, or deterministic query hash is persisted.
  Raw-question tracing is an explicit local debugging opt-in and is rejected in
  preview and production.
- Hardened evidence identity, relevance selection, distance rails, and the
  atomic quote floor for structured publication.
- Made public support presentation a per-item projection of publication kind:
  reviewed structured claims and extraction-only source wording are labelled
  independently.
- Bound candidate evidence and current documentation to the exact candidate
  commit, tree, and matching CI artifact. RC1 reports remain historical
  snapshots.
- Versioned the ten safer RC2 hard-probe response-mode migrations as a named,
  hash-bound expectation profile without changing the historical dataset or
  lowering its `86/105` floor.
- Added the independently hash-bound RC2.1 profile: it retains the ten frozen
  RC2 migrations and appends A01's exact reviewed-plus-quote-only contract as
  the eleventh migration without changing the dataset, schema, or floor.
- Added the independently hash-bound RC2.2 profile: it copies frozen RC2.1
  unchanged and migrates only A09 and A10 to two-sided `structured_reviewed`
  coverage of `TC-EVAC-ALERT-001` and `TC-EVAC-ORDER-001` without rewriting the
  historical dataset, RC2, RC2.1, or the `86/105` floor. Candidate evidence
  uses RC2.2 as the active overlay while retaining RC2 and RC2.1 as frozen
  materials.
- Bound V1.6 promotion ancestry with isolated `rev-list` reachability so Git
  2.55 commit-graph false negatives and inherited `GIT_DIR` cannot reject a
  merge commit when F and unique P are ancestors. Candidate-evidence now
  unshallows after qualification, which can write a shallow boundary that hides
  F while leaving HEAD unchanged. Overlays, the 86 floor, and
  `ALLOWED_PROMOTION_PATHS` are unchanged.
- Added a typed intent automaton as the single owner of request shape before
  `AgentQueryPlan` authorizes tools, layers, and geography.
- Rendered live current-record answers from fetched typed official records so
  provider prose cannot publish unbound status, fire-count, or kilometre
  assertions while retaining those records.
- Restored OpenAPI `ProofCard` / `PublicClaim` publication requiredness to the
  origin/main public contract: `ProofCard.publication` is not a public field;
  `PublicClaim.publication` stays optional/nullable. Internal proof-card
  publication authority remains required.
- Required both atomic evacuation-alert and evacuation-order definitions for a
  grounded comparison, or `PARTIAL` with
  `Not supported by selected evidence: evacuation alert meaning`. Comparison
  retrieval now queries both atomic meanings, and packet selection
  keeps a fused hit for each still-uncovered atomic aspect after rerank so a
  packet that contains both reviewed spans can ground; a one-sided packet
  stays partial.
- A09 and A10 now pass under the added RC2.2 overlay as two-sided
  `structured_reviewed` coverage of `TC-EVAC-ALERT-001` and `TC-EVAC-ORDER-001`.
  They remain exclusive `official_quote_only` failures under frozen RC2 and
  RC2.1. The 86/105 floor is unchanged.
- Bound trailing `from <place>` as location scope for nearest-wildfire
  requests.
- Bound quote-only official wording to an admitted corpus chunk identity and
  exact quote occurrence; a gov.bc.ca URL plus a 64-hex hash is not enough.
  Unofficial hosts stay rejected. Kept current-advice on the guidance lane;
  treated FireLens map-data questions as non-live; routed universal standoff
  prompts as prescriptive rather than live geometry. A preparedness noun does
  not let static documents answer whether an evacuation order is active.
- Promoted the public package, runtime, Docker, Render, OpenAPI, and
  candidate-evidence identity from `1.6.0-rc.1` to `1.6.0`.
- Rebuilt the README as a reader-first explanation of the product, authority
  boundary, V1.6 work, verification limits, and contributor entry points.
- Made rejected validation downgrade public presentation even for no-claim
  responses carrying stale strengthening banner copy.
- Made unsupported current AQHI, smoke-forecast, road-condition, and aircraft
  requests return deterministic official handoffs before any provider or
  unrelated wildfire-record tool can run; mixed supported requests keep their
  supported records or reviewed guidance.
- Removed repeated combined-answer, support-checklist, and limitation blocks
  from the answer surface. Authority-labelled sections now render once as the
  primary content while proof and source controls remain available.

## Historical — V1.1 conversational RC

### Added

- Added bounded conversation history: the API and frontend carry at most six
  completed user/assistant turns, with an explicit clear-history control.
- Added deterministic capability answers so a new user can discover the
  reviewed collection and receive useful suggested questions without a paid
  provider call.
- Added a schema-constrained planner that classifies related requests as
  `grounded_candidate`, `adjacent`, or `tangent` and may emit at most three
  standalone retrieval queries.
- Added four explicit public answer modes beyond abstention: grounded evidence,
  labelled general background, capability overview, and scope redirect.
- Added generalized multi-query BM25/dense retrieval with one deduplicated RRF
  fusion across every planned query.
- Added versioned retrieval text strategies and a development-only contextual
  retrieval A/B/C experiment. `metadata_context_v1` was selected and the
  governed 180 × 1,536 index was rebuilt.
- Added a strict 50-case V1.1 conversation benchmark covering capability,
  contextual follow-ups, adjacent background, tangents, and mixed adversarial
  boundaries across development, sealed holdout, and red-team splits.
- Added ADRs for conversational evidence modes, bounded planning, contextual
  retrieval, and retaining the inspectable custom pipeline rather than adopting
  a framework abstraction.
- Added learning notes for routing/planning, generalized RRF, evidence modes,
  and contextual retrieval.

### Changed

- Replaced the old serialized `static` route with `related`; Python callers can
  still read historic `static` values for compatibility.
- Kept deterministic live, personalized-safety, personalized-medical, and
  policy-manipulation checks before any paid call. Ambiguous high-risk follow-ups
  remain fail-closed.
- Separated background drafts from grounded drafts so background claims cannot
  acquire corpus citations and grounded claims cannot omit them.
- Made each dedicated OpenRouter generation method own its draft family. The
  strict wire schema omits the redundant `answer_type`; a model-supplied
  discriminator is rejected, and the local typed draft is constructed only
  after all model-supplied fields pass validation.
- Promoted capability/background/scope labels, bounded context, and clear
  evidence states into the Source Lens UI and generated TypeScript contract.

### Measured validation

- Final verification: 99 Python tests passed, 3 paid smoke tests skipped, and 22
  Python subtests passed. Frontend verification passed 11 unit/accessibility
  tests, 4 Sites packaging tests, and 12 Playwright flows (six flows in each of
  two viewport projects).
- V1.1 offline: 50/50 complete with all control metrics at 100%; fake-provider
  retrieval scores are structural tests, not live quality evidence.
- Contextual A/B/C: `metadata_context_v1` reached 100% Recall@5 and 81.25% MRR@5
  on eight grounded development cases, compared with 87.5%/58.75% for the raw
  V1 question baseline.
- Locked V1 retrieval sweep: the current 20/20, RRF 60, top-5 configuration
  retained 96% Recall@5 and 86.17% MRR@5 across 50 answerable development cases.
- Thirty-call canary: all structurally accepted, with no status or reason-code
  variance and 2.565-second p95 latency.
- The final retained live V1.1 run completed 50/50 cases with every automated
  control metric and retrieval-stage recall at 100%, zero provider failures,
  2.572-second p95 latency, and $0.075479 reported cost. An earlier
  repeat hit a transient 429 after all three bounded attempts on one case; both
  observations are retained as provider-variability evidence.

### Release status

- Label remains `engineering-complete, semantic acceptance pending`.
- V1.1 is not release-qualified: owner review is pending, the legacy V1
  compatibility benchmark is still below its 95% Recall@5 gate at 92.42%, and
  manual in-app visual inspection was blocked by stale browser handles.

## Historical — Static RAG V1 completion

- Established a secret-safe Git baseline.
- Added an authoritative living technical handbook, ADRs, learning notes, and
  an evidence ledger.
- Added the versioned single-question API and local evidence-support contract.
- Added shared provider lifecycle, same-model bounded retries, atomic
  persistence, concurrent-build protection, and trace retention.
- Added a strict 100-case benchmark, review packets, a four-way retrieval
  comparison, a 30-call variability canary, and an identical-packet model
  bake-off.
- Repaired a visually verified multi-column PDF page and rebuilt the governed
  corpus/index to 180 chunks and 1,536 dimensions.
- Connected the Source Lens frontend to `/api/v1/ask` with typed generated API
  contracts, explicit states, evidence inspection, accessibility tests, and
  desktop/mobile browser flows.
- Added packet-specific quote-ID enums after the canary exposed inconsistent
  model use of passage IDs.

The V1 numbers formerly shown in top-level documentation are preserved in the
historical section of `docs/releases/V1_EVIDENCE.md`; they are not V1.1 release
evidence.
