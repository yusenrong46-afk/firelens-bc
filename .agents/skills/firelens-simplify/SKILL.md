---
name: firelens-simplify
description: Remove duplicated ownership, dead paths, or obsolete compatibility from a mature FireLens subsystem protected by evaluation.
---

# FireLens simplify

## Trigger

Use when duplication or dead code has measured cost and its behavior is already
protected by a stable evaluation family.

## Purpose and input

Input is a bounded subsystem, its authoritative owner, baseline metrics, and
protecting tests/evaluations. Produce less internal complexity without drift.

## Allowed actions

- Edit only the bounded mature subsystem and its tests/docs.
- Remove confirmed unused code and consolidate decisions into one typed owner.
- Measure LOC, owners, branches, regex sites, imports, calls, latency, and bundle.

## Forbidden actions

- Do not simplify unprotected behavior or delete historical evidence.
- Do not treat fewer lines as success by itself.
- Do not combine authority lanes or move deterministic facts into a model.

## Workflow

1. Use `firelens-map` to enumerate callers, compatibility needs, and duplicates.
2. Run the protecting suite and record before metrics.
3. Make one bounded ownership/deletion change.
4. Re-run protected and neighboring suites.
5. Record after metrics and any retained compatibility rationale.

## Output schema

`scope`, `authoritative_owner`, `removed_or_consolidated`, `before`, `after`,
`behavior_results`, `compatibility_retained`, `remaining_duplicates`.

## Stop and handoff

Stop if evaluation coverage is missing or behavior changes ambiguously. Hand a
qualified exact candidate to `firelens-release`.
