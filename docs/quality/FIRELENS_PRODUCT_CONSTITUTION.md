# FireLens Product Constitution

## Purpose and boundary

FireLens is a B.C.-focused information product, not an emergency authority or
personal safety decision-maker. This constitution defines the product-quality
rules for the V1.6.2 engineering campaign. It describes a development
standard, not a certification, deployment result, or release decision.

The operating principle is **broad interpretation, narrow authority**:

- understand a user’s wording generously enough to find a useful route;
- grant factual publication authority only from the appropriate live record,
  reviewed typed claim, exact admitted quotation, or explicitly labelled
  background lane;
- make uncertainty visible without turning a relevant question into an
  unrelated-question refusal.

Safety-sensitive is not out of scope. A request such as “Should I evacuate?”
is relevant, but FireLens must not make the personal decision. It can ask for a
B.C. community, check the bounded official evacuation layer where available,
and direct the person to the issuing authority.

## Eight contracts

### 1. Scope understanding

The request parser should distinguish live-record questions, reviewed
guidance, general background, product help, mixed requests, and genuine
out-of-scope requests. Ambiguity should lead to a bounded interpretation or
one short clarification. `OUT_OF_SCOPE` is a high bar, not the default for an
uncertain wildfire question.

### 2. Capability decomposition

Scope, capability, safety policy, tool plan, evidence selection, composition,
and publication are distinct decisions. The deterministic request plan owns
tools, live layers, geography, and static subrequests; a model does not expand
those capabilities at runtime. See [ADR 0017](../adr/0017-deterministic-agent-query-plan.md)
and [ADR 0018](../adr/0018-typed-intent-automaton.md).

### 3. Evidence authority

Retrieval score, a source URL, and a model statement are not authority by
themselves. Current incident and evacuation facts come from typed official
records. Stable high-risk guidance requires an approved typed claim or an
exact admitted official quotation. General background remains visibly labelled
as background.

### 4. Deterministic ownership

Code owns routing, selection, geometry, distances, record identity, and
publication constraints. A provider may support only the bounded lanes already
permitted by the implementation; it cannot promote an unverified fact or
choose an evacuation action for a person.

### 5. Publication authority

Every public claim must retain its publication kind: official live typed,
structured reviewed, official quote-only, source-linked explanation, general
background, unknown, or handoff. Quote-only wording is exact source text, not
a FireLens interpretation. Atomicity and evidence-identity checks fail closed
before publication.

### 6. Useful failure

When FireLens cannot establish an answer, it should state what is missing and
offer the smallest useful next action: select a record, provide a B.C.
community, open the official service, or ask a narrower question. It must not
invent a safe condition, fabricate a live record, or silently substitute a
nearby incident.

### 7. User-first presentation

The answer comes before implementation detail. Trust labels are local to each
claim rather than one global “grounded” badge. Maps appear for geographically
useful live questions; multi-record analytical questions use the analysis
workspace; general discussion remains chat-first with only relevant source
support. The frontend surface is exercised by
[its fixture protocol](../../data/evaluation/frontend_surface.v1.yaml).

### 8. Runtime and release truth

Local tests, fixtures, and artifacts prove only what they actually executed.
They do not prove live-feed availability, human comprehension, accessibility
review, deployment, firewall behavior, or release readiness. The authoritative
release process remains the [V1.6 runbook](../releases/V1_6_RUNBOOK.md).

## Required repair discipline

Every release-relevant finding follows this order:

```text
Observe → Reproduce → Falsify → Identify violated contract → Root cause
→ Red test → Small fix → Narrow verification → Regression suite
→ Falsify again → Gate decision
```

Keep at most **three active issue clusters**. A cluster may be closed only when
the behavioral reproducer, relevant regression test, and affected benchmark
all agree. A passing implementation explanation is not verification.

## Evidence grades

| Grade | Meaning | Does not establish |
| --- | --- | --- |
| Inspected | Read-only source or artifact review | Runtime behavior |
| Executed | Repeatable local command or fixture result | Live or production behavior |
| Measured | Recorded metric with command, identity, and method | Human comprehension or release approval |
| Human | Named human review/session result | Broader deployment qualification |
| Release | Exact candidate, gate evidence, and authorized decision | Future changes or continuous correctness |

## Current engineering limits

The public [ProductBench v2 protocol](../protocols/PRODUCTBENCH_V2.md),
[50-question user suite](../reports/V1_6_USER_END_QUESTIONS_50.md), and
[hard-probe inputs](../../data/evaluation/hard_probe.v1.yaml) are development
and regression evidence with distinct roles. They do not replace sealed
assessment, paid evaluation, participant testing, manual accessibility review,
or release authorization.

PB15-style malformed source extraction remains a source-repair concern: an
exact but unreadable span must be omitted or handed off, never cleaned up into
a FireLens claim. That limitation is intentionally visible until a source
repair is independently validated.
