# FireLens V1.6 architecture

Status: current architecture authority for Ask, trust, packaging, and proof UX.
Date: 2026-08-28

The V1.6.4 branch candidate is committed. Exact current HEAD/tree identity is
required in the external current candidate-evidence record after execution;
this architecture document does not embed a self-referential commit identifier
and does not affirm that matching CI evidence already exists. The tracked
package, runtime, Docker, and OpenAPI identity is `1.6.4`, but that identity is
not a deployment or release statement. Exact-Git qualification evidence remains
separate and incomplete until its required local, CI, independent, paid,
preview, and human gates are recorded.

The RC1/RC2 standards and their recorded reports remain historical, frozen
materials. V1.6.3 remains the historical functional parent. V1.6.4 is a
separate patch promotion: it binds that parent, a new exact commit/tree, and
immutable governed artifacts without rewriting an older standard, hard-probe
input, human decision, or report to claim patch qualification.

This document replaces the V1.5 technical handbook for runtime Ask behaviour.
`docs/TECHNICAL_HANDBOOK.md` is historical (2026-07-30). Qualification evidence
is still separate from architecture.

## Product boundary

FireLens is an answer-first general conversational assistant with specialized
reviewed British Columbia wildfire guidance and three official BC live layers
(incidents, perimeters, fire-related evacuations). General background is visibly
labelled and never upgraded into reviewed or current evidence. The map is
offered on demand and opens first only for explicit map or geographic-analysis
requests. FireLens is not an emergency-warning system, evacuation router,
medical advisor, or open-web agent.

The application builds an immutable `AgentQueryPlan` before evidence work. It
is the sole authority for a request's tools, live layers, geography, and exact
reviewed-guidance subrequest. Models may propose wording from the resulting
packet; deterministic code and authorized humans decide what may be published
as supported fact.

## Ask path

Public Ask is `FireLensAgent` in `src/firelens/agent/coordinator.py`, the
immutable planner in `src/firelens/agent/query_plan.py`, and the bounded loop
in `src/firelens/agent/loop.py` (ADR 0018, ADR 0017; ADR 0011 and ADR 0013 are
superseded in part).

```text
QueryRequest
  -> input seatbelt (prohibited / medical / jailbreak)
  -> capability overview (local, zero provider inference)
  -> AgentQueryPlan (exact tools, layers, geography, static subrequest, or terminal response)
  -> execute only plan-authorized official layers and reviewed guidance
  -> pure accepted static: return validated AskResponse (outer_chat_turns = 0)
  -> ready live / mixed: at most one outer write from the authorized packet
  -> any provider tool request outside the plan: reject; duplicates: reject
  -> output rails; at most one rewrite; typed fallback
  -> compose_response (lanes, freshness, Proof Cards)
```

`src/firelens/answering/service.py` is the **static RAG orchestrator** (plan,
retrieve, support, grounded generate, validate). It is not the public Ask
brain. Live answering helpers compute geodesic kilometres after fetch; Luna
must not invent a different distance.

## Deterministic request-plan boundary

Request shape is owned by the typed intent automaton in
`src/firelens/answering/intent_automaton.py` (ADR 0018). One parse supplies
clause boundaries, temporal scope, live operations and layers, national scope,
reviewed-guidance signals, and location candidates. `AgentQueryPlan` authorizes
tools from that projection. Downstream modules must not re-parse the question
with an independent phrase grammar. Current-advice and preparedness-checklist
clauses stay on the reviewed-guidance lane. A preparedness noun does not let
static documents answer whether an evacuation order or incident is active. The
route applies broad interpretation and narrow authority: relevant but ambiguous
wording receives the smallest useful bounded route; safety-sensitive does not
mean out of scope, but personal decisions stay outside FireLens authority.

`AgentQueryPlan` is a frozen per-request value. It can authorize only the
specific fixed tool calls it contains, including normalized arguments. It
expresses one of five modes: static, live, mixed, selected-record, or a
deterministic terminal response. Location binding may turn an unresolved
community into a `requires_input` terminal response, but it cannot add layers,
replace a selected record, or broaden geography.

The loop prefetches the plan's calls. If a provider later proposes a tool call,
runtime dispatch compares its exact name and arguments with the plan and rejects
anything else. A per-request fingerprint also rejects a repeated dispatch. The
provider therefore cannot convert a local request to province-wide, add an
evacuation layer, fetch another record, or retrieve a different guidance query.
Its remaining role is bounded connective prose over reviewed-guidance packets,
subject to output rails. Live current-record text is rendered from fetched
typed official records; provider prose cannot become the public live answer.

## Route budgets

`RequestExecutionPolicy` in `src/firelens/agent/budget.py` counts outer writes
separately from static `grounded_generation`. Frozen budgets live in
`data/evaluation/firelens_v1_6_upgrade_standard.yaml` (`FL-V16-S1`).

| Route | Bound |
| --- | --- |
| capability / prohibited / missing location / deterministic redirect | zero provider inference |
| pure static accepted | outer writes = 0; at most one grounded generation |
| ready live | at most one outer write; no duplicate tool dispatch |
| ready mixed | one validated static generation + at most one connective write |
| provider tool request outside the plan | rejected; no dispatch |
| repeated planned tool request | rejected; no repeat dispatch |
| rejected output | one rewrite, then deterministic fallback |

## Retrieval

Default `FIRELENS_RETRIEVAL_STRATEGY=baseline`. `adaptive_v1` may run at most
two cycles and six queries, then merge/dedup/select before generation. It does
not search the open web, override review/authority, or retrieve during repair
(ADR 0009). Promote to default only if paired development comparison clears H4
and H8.

`max_evidence_spans` default remains 5; the V1.6 cap is 8.

## Trust and claims

`evidence_status` stays for compatibility. Additive `ClaimTrust` and public
wording live in `src/firelens/claim_trust.py`. Grounded answers are “Grounded
in reviewed official sources with exact supporting quotations and automated
critical-field checks,” not unqualified “verified.” Frozen ClaimBench is
`data/evaluation/claimbench_v1_6.yaml`. A semantic model checker, if present,
may only reject and is off by default.

Round 2 improved engineering but failed fresh semantic adversarial testing.
Round 3 introduces risk-tiered typed claims and deterministic rendering.
Visible development benchmarks are not independent proof.

- Tier A (action-critical) and Tier B (quantitative/status-critical) public
  facts are compared as typed snapshots (`typed_snapshot.py`,
  `typed_compare.py`) and, where a human-reviewed record exists, rendered
  from `data/typed_claims/high_risk_v1.yaml`. Unreviewed extractions cannot
  become production-supported Tier A or Tier B claims.
- Official source update time and FireLens retrieval time are separate
  fields. Models do not own trust, freshness, authority, or time.
- Remaining corpus coverage is a human-review debt. Most high-risk spans
  are still checker-gated rather than inventory-rendered.
- High-risk structured publication is deterministic and has zero generation.
  An eligible lower-risk ready packet may use one bounded generation only after
  deterministic validation.   Uncovered high-risk material remains an exact-source
  quote-only, partial, or handoff response; it is not a reviewed structured
  claim. Quote-only official wording requires an admitted static-corpus chunk
  identity and the exact quote in that chunk, not only a gov.bc.ca host and
  64-hex hash. Alert/order comparison packets reserve a fused candidate for
  each still-uncovered atomic definition aspect after rerank, without raising
  default `rerank_top_k`.
- The permanent hard-probe dataset remains immutable. The named, hash-bound
  `rc2` profile preserves ten safer response-mode migrations. The frozen
  `rc2.1` profile copies those ten unchanged and appends A01's exact
  `{structured_reviewed, official_quote_only}` mixed-publication contract. The
  active `rc2.2` profile copies rc2.1 unchanged and migrates only A09 and A10
  to two-sided `structured_reviewed` coverage of `TC-EVAC-ALERT-001` and
  `TC-EVAC-ORDER-001` while preserving the historical questions, 105-case
  roster, and `86/105` floor. The effective expectation hash and exact Git
  identity travel with report v2. Frozen RC2 and RC2.1 remain separately bound
  materials; they are not rewritten.

## Failures, ops, packaging

Public-agent failures are typed in `src/firelens/errors.py`. Unexpected
programming errors become a sanitized public kind, a content-free ops event,
and a loud local/test failure — never a source outage. Operational events are
`firelens.operational_event.v3` (no question, answer, history, coordinates,
evidence text, or secrets).

Local JSON traces apply the same content-minimization boundary by default: they
contain no question, answer, history, coordinates, evidence text, or query hash.
`FIRELENS_TRACE_CONTENT=true` is an explicit local-only debugging opt-in that
may retain the raw question; preview and production reject it during
configuration validation. This is an executed application boundary, not a
privacy certification or deployed-sink attestation.

Vercel and Docker share `config/runtime_artifact_allowlist.v1.json`. Source
Change Radar hashes approved sources and opens a human review packet; it never
auto-publishes.

## Proof-carrying UX

Additive Ask fields: `status_banner`, `supported_items`, `unknown_items`,
`proof_cards`. Tile failure must not remove official record lists. Trust is
labelled in text, not colour alone. Presentation is a projection of
`publication.kind`: reviewed structured claims and extraction-only source
wording are labelled independently, including in mixed answers. Publication
kind owns that authority; a Proof Card profile is a projection of the owning
claim, not an independent `verified` source of truth. `ProofCard.publication` is
internal fail-closed constructor authority and is not a public OpenAPI field.
`PublicClaim.publication` remains optional/nullable on the public contract;
verified corpus claims still require it internally. A stored card that
disagrees with `publication.kind` is rebuilt from the claim or fails closed.
Extraction-only source wording is never strengthened by a legacy status banner.
Rejected validation forces an unknown presentation even when an older response
supplies no claims and carries stale strengthening banner copy.

## Module sizes and exceptions

Targets from `FL-V16-S1`:

- `src/firelens/agent/loop.py` ≤ 350 lines (helpers in `loop_support.py`)
- modified production modules ≤ 650 lines unless listed here
- remaining production cap 800 lines
- split upgrade-benchmark tests preferably ≤ 1,200 lines

**Written exceptions (this campaign edited these files without a full split):**

- `src/firelens/answering/service.py` — static RAG orchestrator; adaptive
  retrieval was extracted to `adaptive_retrieval.py` instead of rewriting the
  whole module.
- `src/firelens/contracts.py` — public Ask schema; proof models live in
  `proof_presentation.py` and history helpers in `assistant_history.py`, but
  the remaining response contract stays one owner.

The repair also had to touch the following modules that were already above the
650-line modified-module target at `V16_STARTING_COMMIT` (`3de745a2`). Counts
use the same `splitlines()` measure as `tests/test_architecture.py`. These are
exceptions only to the 650-line target: the hard 800-line cap still applies.

| Module | Baseline | Current | Bounded repair and deferred split |
| --- | ---: | ---: | --- |
| `src/firelens/agent/compose.py` | 612 | 686 | Added packet identity fields, selected-record follow-up binding, and public limitation/suggestion binding. The one-turn compose owner stays intact so live, mixed, and clarification routes keep a single result-set writer. |
| `src/firelens/agent/query_plan.py` | 633 | 684 | Added mixed-clause tool planning and selected-record follow-up LIST recovery. The immutable planner stays one owner so live, mixed, and selected routes cannot diverge. |
| `src/firelens/answering/live_analysis.py` | 640 | 662 | Added deterministic sample ranking and honest unnamed-record labels. Distance, roster, and official-prose rendering remain one owner so the ranked sample cannot diverge from the authorized set. |
| `src/firelens/evaluation/capture.py` | 734 | 754 | Added paired private-attestation and preview-raw-evidence capture guards. The immutable before/after artifact roster remains one owner; splitting it during this repair would add serializer and evidence-schema churn. |
| `src/firelens/evaluation/release_surfaces.py` | 778 | 797 | Extracted raw preview-response validation to `preview_raw_evidence.py`. The remaining preview/deployment qualification surface is deferred because a wider split would change governed report validation during an active qualification campaign. |
| `src/firelens/live.py` | 739 | 739 | Corrected paginated aggregate freshness in place. A full adapter split is deferred because the one-line safety fix does not justify moving the fail-closed fetch and normalization boundary. |
| `src/firelens/live_support.py` | 650 | 673 | Added multi–Fire Centre extraction so “Kamloops or Cariboo” asks which official scope to use. Geometry helpers and official-layer policy stay one owner; a wider adapter split is deferred. |
| `src/firelens/review_workspace/cli.py` | 746 | 748 | Plumbed the required development-registry path through the existing semantic-holdout command. Parser/recipe decomposition is deferred rather than broadening a two-line CLI contract repair. |
| `src/firelens/review_workspace/inputs.py` | 792 | 762 | Extracted private semantic-payload validation to `input_semantic.py`. The stable importer facade and commitment assembly remain together so this repair does not migrate the blinded review contract. |
| `src/firelens/runtime_artifact.py` | 780 | 756 | Extracted candidate identity and active-artifact hash binding to `runtime_artifact_candidate.py`. Inventory sequencing and its CLI remain together to avoid changing the staged-artifact verification boundary. |

## Golden traces

Executable offline traces: `src/firelens/evaluation/golden_traces.py` and
`tests/test_v1_6_golden_traces.py`.

## Related documents

- ADR 0017 — deterministic AgentQueryPlan ownership
- ADR 0011 — Luna as Ask brain over a thin application (historical, superseded in part)
- ADR 0013 — evidence-efficient V1.6 agent (historical, superseded in part)
- `docs/releases/V1_6_RUNBOOK.md`
- `docs/plans/V1_6_IMPLEMENTATION.md` (frozen before implementation)
