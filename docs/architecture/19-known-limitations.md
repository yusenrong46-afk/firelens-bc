# 19 — Known Limitations

## Product and data

- FireLens is not an emergency warning, evacuation routing, prediction, property-risk, medical, or open-web system.
- Live coverage is limited to three supported official BC layers. Upstream correctness, completeness, uptime, and timestamp quality are outside FireLens control.
- The live wire contract has no partial-layer state; one malformed strict row or one invalid/unclassifiable geometry currently quarantines that whole layer to avoid silent undercount or false spatial exclusion.
- Coarse geocoding can be ambiguous. Exact addresses are intentionally rejected.
- Stale cached records may remain useful but are explicitly not current conditions.

## Reasoning and evidence

- Request understanding still has multiple text-parsing helpers around the typed automaton, creating divergence risk.
- Retrieval can miss relevant material; exact quotation is not equivalent to semantic entailment.
- Tier C/lower-risk validation is bounded lexical and deterministic checking, not a complete semantic verifier. Optional semantic checking is not a current qualification authority.
- Human-reviewed typed inventory coverage is incomplete; unsupported high-risk material must remain quote-only, partial, or handed off.
- `LiveAnswerCoordinator.answer()` remains a parallel legacy/test composer.

## Operations

- Planner/embedding/rerank budget fields are not consistently enforced at every provider boundary.
- Request telemetry has coarse total timing, a misleading `tool_attempts` derivation, and incomplete early-error coverage.
- Anonymous rate limiting is instance-local, not a distributed production firewall.
- Default model names in configuration do not prove deployed provider/model identity.
- Local content tracing can retain a raw question when explicitly enabled.

## Product validation

- The September 5 `37de779` preview has a verified deployment/build identity.
  Its desktop/mobile browser checks used synthetic API responses; readiness
  and asset success do not prove deployed real-provider task quality.
- Early provincewide captures rejected invalid perimeter/evacuation polygons;
  later bounded V8 requests returned valid records. The independently verified
  135 active incidents and other V8 records are dated source snapshots, not
  assurances about current availability, conditions or safety.
- External backend scope is independently accepted at 37de779 with 12 fresh
  and nine retained cases. The preview browser journeys use fixture responses;
  sustained provider availability and real-provider preview tasks are unmeasured.
  The [System Card](../system-card/FIRELENS_SYSTEM_CARD.md) binds exact evidence.
- Sealed retrieval, participant usability, human accessibility assessment,
  and full production qualification are not established. Native 200% Chromium
  zoom was exercised locally at edd3de9 with fixture data; the map requires
  ordinary vertical scrolling, and this does not establish human usability.
- Historical reports and screenshots bind older states only.

See [Current state](../firelens-current-state/README.md) for the active evidence boundary and [Testing and release](17-testing-and-release.md) for required gates.
