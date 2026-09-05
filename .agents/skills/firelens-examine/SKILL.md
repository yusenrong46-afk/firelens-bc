---
name: firelens-examine
description: Reproduce a FireLens failure and identify the first incorrect structured layer without changing production behavior.
---

# FireLens examine

## Trigger

Use when a case is wrong, inconsistent, unavailable, or suspected unsafe and its
first divergence has not been established.

## Purpose and input

Input is a case ID or reproducible request plus exact application/evaluator
identity. Produce a confirmed or review-only FailureRecord.

## Allowed actions

- Read code, maps, traces, fixtures, and evaluation artifacts.
- Run deterministic/offline reproductions and focused existing tests.
- Use `trace_case.py` with content-redacted output by default.

## Forbidden actions

- Do not edit production behavior or expected answers.
- Do not call a paid provider without a user-approved positive budget.
- Do not inspect or persist unnecessary personal content.

## Workflow

1. Use `firelens-map` to identify likely owners and protected neighbors.
2. Pin commit, tree, dataset, evaluator, models, and execution mode.
3. Reproduce the structured pipeline.
4. Compare understanding, binding, authority, planning, retrieval, reranking,
   evidence, generation, validation, composition, and frontend in order.
5. Treat the first observed divergence as a localization clue, not proof of
   causation. Use a direct reproducer or competing hypotheses and controlled
   interventions to identify the responsible owner; assess visible semantics
   as well as enum differences.
6. Emit a schema-valid FailureRecord with confidence and oracle type.

## Output schema

Use exactly `evals/eval_lab/schema/failure_record.schema.json`; `reproduction`
and `evidence` are schema fields. Put `neighboring_cases` and
`recommended_next_step` in an outer examination handoff, never inside the
schema-valid FailureRecord.

## Stop and handoff

Stop as `review` when the oracle is ambiguous or reproduction is incomplete.
Hand `confirmed_fail` records to `firelens-fix`.
