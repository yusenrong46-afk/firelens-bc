# 17 — Testing and Release

Current repair gates and exact evidence are documented in the
[bounded repair record](../reports/BOUNDED_REPAIR.md). `make verify` includes
mocked browsers; `make verify-candidate-browser` is the separate required
synthetic built-stack lane for this handoff. The versioned current J01 contract
permits only independently verified, admitted same-topic rationale with no
generation. Its legacy RC2 profile still reports FAIL; the current harness test
asserts that failure precisely. Other draft contracts remain pending.

## Final release successor — 2026-09-05

The release starts from accepted documentation candidate `6d41a4c` and includes
UI follow-up `2a9ecb6` (tree `6c4e9348d7f046a557e067bba5814a3349379f6d`).
The latter docks the composer at the bottom and submits guided questions on
selection. Backend source, provider configuration defaults, API contracts and
corpus/index inputs remain identical to qualified runtime `37de779`; UI evidence
requires the follow-up's own checks. Its retained 198 frontend tests, 45 mocked
browser passes, one skip and three-width fixture preview are separately bound.
The [final release record](../releases/firelens-final-ship.md) tracks integration, final review and production
results. Release execution is authorized subject to its gates; this is not
emergency-authority endorsement or a claim that production checks have passed.

## Candidate evidence — 2026-09-05

Application `37de7791d1ce0198e3e2db012f6bc9442d4b8f6b`, tree
`862a8b9fda91eda380b6e3ef7e8722a1d26ffe12`, adds optional generation endpoint
selection to the contents, requested-source and background repairs. Full local
verification passed. Independent High accepted external backend qualification
with declared limitations: 12 fresh responses and nine retained prior cases. The
[System Card](../system-card/FIRELENS_SYSTEM_CARD.md) tracks external acceptance
and the verified preview separately. `0c6b81a` is the V8 predecessor.
The retained qualified-runtime preview is `37de779`; the broader synthetic UI matrix
remains historical evidence at `b887cb4`.
The [System Card](../system-card/FIRELENS_SYSTEM_CARD.md) owns the current
result table and evidence identities. Predecessor local verification and synthetic UI
journeys passed; retained preceding backend core remains FAIL 565/574.
Earlier provincewide captures rejected malformed perimeter/evacuation geometry.
The later V8 bounded snapshots had valid perimeters and evacuation records,
independently checked alongside 135 active incidents. Each observation retains
its capture time and application identity. The 37de779 preview readiness
matched the current runtime; its browser checks used synthetic API responses.

The System Card separately tracks repaired-source checks, full verification and
provider-backed qualification; earlier observations do not qualify the successor.
Accepted backend work stays closed within scope. Historical Sol/Astra numbers
below retain their original identity and do not describe a new candidate run.

The publication compiler owns direct informational quote selection when a mixed
packet contains incidental high-risk text. Its bounded path uses the existing
static guidance subject owner to preserve kit, pet and smoke applicability,
selects against the user request rather than planner-expanded aspects, and keeps
source admission, atomicity and exactness checks. The original rank-definition
failure and the two subsequent kit/pregnancy regressions are retained in campaign
`repair-C3`; High V2 accepted the narrowing after protected tests and an exact
three-response offline replay. This local repair does not establish a new
provider result or deployment.

Successor contents and source scope are owned by the existing static-tool boundary,
request facets and source-metadata packet binding. Embedded actors do not become
publisher identities. Adjacent explanations retain the existing compiler-first
background route; tangent discovery remains bounded untrusted context with no
new lookup or evidence authority. The follow-up protected set passed 403 tests
plus 99 subtests. Full verification then passed at `edd3de9`; external acceptance
remains a separate gate.

The optional `FIRELENS_GENERATION_PROVIDER_ONLY` setting restricts generation
endpoints only; default empty preserves normal routing. For the qualified preview
configuration, pass `--generation-provider-only azure/eu` to the existing
`scripts/deploy_vercel.py` wrapper. It supplies the value to both build and runtime
without changing model, privacy, fallback or embedding/rerank policy. Final
receipts and deployment configuration must bind the same explicit subset.

## Test layers

| Layer | Purpose | Examples |
| --- | --- | --- |
| Unit/contract | Pure invariants, parsing, identities, validation | live, typed intent, publication, contracts |
| Integrated offline | Public agent with deterministic providers/live fixtures | golden traces, mixed clauses, source-aware conversation |
| Package/static | Formatting, types, artifacts, generated OpenAPI, frontend build | `make check`, `make verify`, package verification |
| Authorized external | Real OpenRouter/live source/preview/browser origin | provider, live, and preview qualification |
| Independent/human | Semantic examiner, sealed retrieval, accessibility, product/safety judgment | review protocols and signed artifacts |
| Production | Exact deployed build/deployment and post-deploy reality checks | release runbook after all prerequisites |

## Historical Sol local repair evidence

**HISTORICAL SOL, 2026-09-04:** candidate identity is the exact clean
branch `HEAD`; the final retained EvalLab envelope and campaign handoff bind its
full SHA/tree. Important evaluator/source hashes are:

- `tests/test_typed_intent_automaton.py`:
  `660e0812ba87fabcf0716b56e3c2e0c68433cc631870559f31bbf0448bb8fdcd`;
- `tests/test_live.py`:
  `a3d4b614090b21c1765037db26f7b5f90cf000f781884ced7a11c00eb4787aa5`;
- `tests/test_luna_brain_agent.py`:
  `3ea86fa7421afd76d68bc8b469bd09a9b58541184629216a87e6f3b42a503798`;
- `apps/web/tests/liveAnswerSummary.test.tsx`:
  `cd8034e2689ffcdfd454446c80f58905aada5f781ceebb34efdc87e9d715cd67`;
- `tests/test_firelens_eval.py`:
  `6e03c48a63fbe5f226ab735d2a5e40a1528467748f29d007d9363eff756b744e`.

Focused final suites passed 284 typed intent/agent tests plus 35 subtests, 122
live/safety/architecture tests plus 48 subtests, 36 EvalLab implementation
tests, and 183 frontend tests. Full `make verify`, `make docs-check`, and map
validation pass on the settled local candidate. Tests use fakes/fixtures where
configured and do not establish provider quality, real-feed behavior, preview,
production, human review, or release qualification.

## Historical Sol zero-cost evaluation result

The clean-candidate EvalLab core run executes 574 rows without network/provider
calls and finishes **FAIL 562/574**: ProductBench 31/31, ClaimBench 332/332,
hard probe 93/105, and source-aware conversation 106/106. Ten hard-probe
expectation mismatches are `CRITICAL`; the declared 86/105 aggregate floor
cannot waive them. Those mismatches remain under evaluation-contract ownership
review and do not by themselves prove product defects.

EvalLab blocks dirty or source-changing evidence. Historical compare validates
each envelope against its own detached commit snapshot, replays the four core
adapters, and refuses incompatible policy/schema/dataset/evaluator bindings.
This is deterministic local evidence, not a provider, sealed, live-feed, human,
preview, or production result.

## Release boundary

The current [`V1_6_RUNBOOK.md`](../releases/V1_6_RUNBOOK.md) describes a local
engineering candidate. Release requires matching CI and candidate artifacts,
authorized live/provider checks, sealed/independent/human gates, preview
verification, deployment identity, post-deploy verification, rollback target,
and an explicit human decision.

Vercel `READY`, a health 200, a passing local suite, an offline score, or an old
production report is insufficient by itself. The dated candidate evidence above records the current qualification boundary;
production still requires its own explicit authorization.
