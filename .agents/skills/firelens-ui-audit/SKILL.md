---
name: firelens-ui-audit
description: Audit FireLens UI behavior, evidence visibility, accessibility, responsiveness, and answer-map coherence without redesigning or editing it.
---

# FireLens UI audit

## Trigger

Use before UI redesign, after a UI regression, or during candidate qualification.

## Purpose and input

Input is an exact deployment or local candidate URL plus required journeys and
viewports. Produce screenshot-backed functional and product findings.

## Allowed actions

- Navigate and interact with the selected browser in read-only user journeys.
- Capture baseline screenshots, accessibility output, console errors, and vitals.
- Verify source links and answer/list/map record identity.

## Forbidden actions

- Do not edit the product, redesign during the audit, submit personal data, or
  interpret a screenshot as proof of backend correctness.
- Do not use live absence as evidence of safety.

## Workflow

1. Pin deployment, build, assets, viewport, and state.
2. Exercise idle, live, reviewed, mixed, general, location-required, unavailable,
   evidence, map/list, follow-up, reset, keyboard, and responsive journeys.
3. Check task success, source visibility, no dead ends, coherence, accessibility,
   overflow, touch targets, lazy assets, console, and stale-chunk recovery.
4. Separate functional defects from subjective product judgments.
5. Preserve comparable baseline screenshots for any later candidate.

## Output schema

`identity`, `journey`, `viewport`, `functional_result`, `a11y`, `performance`,
`screenshots`, `defects`, `product_findings`, `unverified`.

## Stop and handoff

Stop on ambiguous identity or inaccessible required state. Hand confirmed code
defects to `firelens-examine`; use product findings to scope a bounded UI change.
