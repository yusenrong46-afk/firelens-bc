# ADR 0017: Deterministic AgentQueryPlan ownership

Status: accepted
Date: 2026-08-25

## Context

ADRs 0011 and 0013 bounded a provider's fixed tool vocabulary and tool-loop
budgets, but still described the provider as choosing tools. A fixed vocabulary
does not itself prove that one request cannot widen its geography, add a live
layer, substitute a record, alter a reviewed-guidance query, or repeat work.

Those decisions are evidence and privacy boundaries, not prose preferences.
They must be inspectable before provider interaction and independently enforced
at runtime.

## Decision

Build one immutable `AgentQueryPlan` before external evidence work for every
public Ask request. It is the sole authorization for:

- request mode: static, live, mixed, selected-record, or terminal;
- official live layers and geography: none, selected record, location radius,
  or province-wide;
- the exact selected-record identifier, where relevant;
- the exact reviewed-guidance subrequest, where relevant; and
- the complete tuple of tool names and normalized arguments that may execute.

The plan may return a deterministic terminal response for prohibited scope or a
missing/unresolved location. Location resolution may turn a location-radius
plan into `requires_input`, but may not add tools, layers, records, or scope.

The loop prefetches only planned calls. Runtime dispatch checks every subsequent
provider tool request against the plan's exact name and arguments, and records a
per-request fingerprint to reject repeat dispatch. A provider may propose prose
from the resulting evidence packet only; it cannot authorize retrieval or
geographic scope.

Default local traces are content-minimized: no raw question, answer, history,
coordinates, evidence text, or deterministic query hash. An explicit local
`FIRELENS_TRACE_CONTENT=true` debugging opt-in may retain the raw question.
Configuration rejects that opt-in in preview and production.

## Consequences

- Query authorization is deterministic, testable, and separate from model
  fluency. A rejected provider request cannot cause an unplanned fetch.
- Mixed questions retain their separately authorized current-record and
  reviewed-guidance portions rather than allowing either half to expand the
  other.
- The provider still receives only the packet needed to write an answer and
  remains subject to output rails, deterministic publication, and typed
  fallback.
- This decision does not establish full-suite success, preview/production
  qualification, provider privacy certification, or release approval.

## Supersedes in part

ADR 0011's Luna tool-selection responsibility and ADR 0013's
provider-directed tool-loop framing are superseded. Their bounded-provider,
packet, budget, and deterministic-publication principles remain in force.
