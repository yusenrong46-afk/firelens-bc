# Changelog

## Unreleased — V1.1 conversational RC

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
