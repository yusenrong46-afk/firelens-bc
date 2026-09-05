# 01 — Product Contract

FireLens provides evidence-bound wildfire information for British Columbia through three distinct evidence lanes.

| Lane | Application promise | Primary owner |
| --- | --- | --- |
| Official live | Current typed incident, perimeter, and fire-related evacuation records, with source and retrieval timestamps | [`live.py`](../../src/firelens/live.py), [`live_contracts.py`](../../src/firelens/live_contracts.py) |
| Reviewed guidance | Stable admitted-corpus guidance with exact support and publication authority | [`answering/service.py`](../../src/firelens/answering/service.py), [`publication/`](../../src/firelens/publication/) |
| General background | Clearly labelled explanation that is not represented as reviewed or current | [`answering/generate.py`](../../src/firelens/answering/generate.py), [`contracts.py`](../../src/firelens/contracts.py) |

## Non-negotiable invariants

- Source failure is not zero.
- Unavailable is not empty; empty is not safe.
- Stale is not current; partial is not complete.
- A missing record is not evidence of no danger.
- Models cannot grant themselves tools, layers, geography, sources, or publication authority.
- Official identity, count, status, size, geometry, distance, ranking, and timestamps are application-owned.
- FireLens does not decide whether a person is safe, should stay, should return, or should evacuate.
- General model knowledge cannot appear as official current information, reviewed guidance, or official quotation.

`AskResponse` makes these distinctions visible through response mode, authority-labelled sections, live layer status, limitations, claims, evidence, and proof cards. The exact contract is in [Data contracts](appendices/data-contracts.md).

## Intended use

- Explore official BC wildfire records and bounded coarse-location results.
- Read reviewed preparedness guidance with inspectable supporting passages.
- Ask follow-ups that preserve bounded source and selected-record context.
- Reach official sources when FireLens cannot establish an answer.

## Out of scope

Emergency warning, evacuation routing, property-specific risk, prediction, medical advice, exact-address processing, unrestricted open-web research, and autonomous safety decisions. See [Safety and authority](09-safety-and-authority.md) and the [System Card](../system-card/FIRELENS_SYSTEM_CARD.md).

