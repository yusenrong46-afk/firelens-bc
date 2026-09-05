# 18 — Maintenance and Simplification

Maintenance should reduce semantic owners, not merely file size. Start from the generated repository map and the failing case, identify the earliest owner, then run its semantic neighbors.

## Current concentration points

The current map inspection identified large/high-branch modules around typed intent, place parsing, runtime artifact assembly, live analysis/support, proof presentation, composition, contracts, live normalization, and query planning. High size is not itself a defect, but it raises the cost of determining which rule owns a behavior.

## Duplicate owners to retire carefully

1. `LiveAnswerCoordinator.answer()` remains a legacy/test-facing full composer while public Ask uses `FireLensAgent`. Migrate tests to the public owner before removing it.
2. `fallback_brain.py` derives tool/static intent beside immutable `AgentQueryPlan`; make it a projection of the plan or remove the re-parse.
3. Frontend `proofPresentation.ts` rebuilds trust/freshness/status logic beside backend proof construction; preserve only weak display fallbacks.
4. Multiple clause/location/live-intent helpers re-read raw text after the typed automaton; route new concepts through a typed projection.
5. Live publication constructors are split between `publication/compiler.py` and internal publication helpers; define one runtime constructor.
6. Static/mixed operation logging has more than one emission owner; centralize one request-completion event.

## Change protocol

- Freeze the failing input and all externally visible structured fields.
- Add a red regression at the earliest boundary and at least one legitimate neighbor.
- Apply the smallest generalized rule; avoid phrase-specific exceptions unless the product grammar explicitly requires one.
- Verify answer, API, map/list, proof, suggestions, and continuation identity together.
- Delete the superseded path only after direct callers and evaluation families move.
- Update the [module map](appendices/module-map.md), [ADR index](appendices/adr-index.md), and [current state](../firelens-current-state/README.md) when ownership changes.

The historical Sol campaign removed two confirmed-unused TypeScript modules and redundant
mobile history UI, while replacing handwritten API unions with generated
OpenAPI types. Production runtime Python changed from 76,953 to 77,297 lines;
EvalLab adds a separate 3,391-line evaluation package. TypeScript/TSX changed
from 8,526 to 8,460 lines and CSS from 3,276 to 3,284. Regex call-site
occurrences changed from 519 to 520 across the same 89 files; modules over 650
and 800 lines stayed 18 and zero. Semantic-owner count, fallback-branch count,
and import fan-out were not measured and are not inferred from LOC.

No architecture simplification is qualified merely because LOC falls. Behavior
and authority must remain falsifiable.

Astra removes a second, singular-only source-attribution recheck and its
stopword inventory. Mixed terminal and executed answers share boundary
composition; the outer guard no longer separately requires a location for a
mixed request. The sidebar clear action has one reset owner rather than two
calls. Independent publication validation, quote binding, live-layer
completeness and browser request-ownership checks remain separate safeguards.
