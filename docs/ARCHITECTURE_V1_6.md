# FireLens V1.6 architecture

Status: current architecture authority for Ask, trust, packaging, and proof UX.
Date: 2026-08-17

The RC2 label names the current hardening and qualification campaign. The
public package, runtime, and OpenAPI identity remains `1.6.0-rc.1` until a
separately authorized version change; evidence must record that actual identity.

This document replaces the V1.5 technical handbook for runtime Ask behaviour.
`docs/TECHNICAL_HANDBOOK.md` is historical (2026-07-30). Qualification evidence
is still separate from architecture.

## Product boundary

FireLens is a map-first assistant over reviewed British Columbia wildfire
preparedness guidance and three official BC live layers (incidents, perimeters,
fire-related evacuations). It is not an emergency-warning system, evacuation
router, medical advisor, or open-web agent.

Models may choose bounded tools and propose wording. Deterministic code and
authorized humans decide what may be published as supported fact.

## Ask path

Public Ask is `FireLensAgent` in `src/firelens/agent/coordinator.py` plus the
bounded loop in `src/firelens/agent/loop.py` (ADR 0011, ADR 0013).

```text
QueryRequest
  -> input seatbelt (prohibited / medical / jailbreak)
  -> capability overview (local, zero provider inference)
  -> prefetch official layers and, when warranted, reviewed guidance
  -> pure accepted static: return validated AskResponse (outer_chat_turns = 0)
  -> ready live / mixed: at most one outer write from the official packet
  -> unresolved tools: max two rounds + one terminal write
  -> output rails; at most one rewrite; typed fallback
  -> compose_response (lanes, freshness, Proof Cards)
```

`src/firelens/answering/service.py` is the **static RAG orchestrator** (plan,
retrieve, support, grounded generate, validate). It is not the public Ask
brain. Live answering helpers compute geodesic kilometres after fetch; Luna
must not invent a different distance.

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
| unresolved tool loop | two rounds + one terminal write |
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
  deterministic validation. Uncovered high-risk material remains an exact-source
  quote-only, partial, or handoff response; it is not a reviewed structured
  claim.
- The permanent hard-probe dataset remains immutable. The named, hash-bound
  `rc2` expectation profile records ten safer response-mode migrations while
  preserving the historical questions, case count, and `86/105` floor. The
  effective expectation hash and exact Git identity travel with report v2.

## Failures, ops, packaging

Public-agent failures are typed in `src/firelens/errors.py`. Unexpected
programming errors become a sanitized public kind, a content-free ops event,
and a loud local/test failure — never a source outage. Operational events are
`firelens.operational_event.v3` (no question, answer, history, coordinates,
evidence text, or secrets).

Vercel and Docker share `config/runtime_artifact_allowlist.v1.json`. Source
Change Radar hashes approved sources and opens a human review packet; it never
auto-publishes.

## Proof-carrying UX

Additive Ask fields: `status_banner`, `supported_items`, `unknown_items`,
`proof_cards`. Tile failure must not remove official record lists. Trust is
labelled in text, not colour alone. Presentation is a projection of
`publication.kind`: reviewed structured claims and extraction-only source
wording are labelled independently, including in mixed answers. Extraction-only
source wording is never strengthened by a legacy status banner. Rejected
validation forces an unknown presentation even when an older response supplies
no claims and carries stale strengthening banner copy.

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

Untouched `live.py` / `live_answering.py` remain under the 800-line cap only.

## Golden traces

Executable offline traces: `src/firelens/evaluation/golden_traces.py` and
`tests/test_v1_6_golden_traces.py`.

## Related documents

- ADR 0011 — Luna as Ask brain over a thin application
- ADR 0013 — evidence-efficient V1.6 agent
- `docs/releases/V1_6_RUNBOOK.md`
- `docs/plans/V1_6_IMPLEMENTATION.md` (frozen before implementation)
