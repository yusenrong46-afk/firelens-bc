---
name: firelens-map
description: Locate FireLens owners, callers, tests, evaluation families, and impact before broad repository reading or code changes.
---

# FireLens map

## Trigger

Use for ownership, architecture navigation, dependency impact, or “where is this
implemented?” questions. Use before examining a localized failure.

## Purpose and input

Input is a file, symbol, capability, invariant, or observed product behavior.
Return the smallest evidence-backed slice of the system that owns it.

## Allowed actions

- Read tracked code and `docs/firelens-map/`.
- Run `build_map.py`, `validate_map.py`, and `impact.py` without network access.
- Report direct and inferred relationships distinctly.

## Forbidden actions

- Do not modify production behavior, tests, frozen datasets, or release state.
- Do not infer semantic authority from import shape alone.
- Do not call providers or live adapters.

## Workflow

1. Validate the generated map against the current tree.
2. Search the map for the requested file, symbol, capability, or invariant.
3. Confirm the primary owner in source.
4. Return callers, downstream consumers, tests, eval families, and duplicates.
5. Name uncertainty and stale-map evidence explicitly.

## Output schema

`target`, `primary_owner`, `direct_callers`, `downstream_consumers`,
`contracts`, `tests`, `evaluation_families`, `impact`, `duplicates`, `gaps`.

## Stop and handoff

Stop if the map is stale or ownership is ambiguous; do not invent an owner.
Hand confirmed behavioral failures to `firelens-examine`.
