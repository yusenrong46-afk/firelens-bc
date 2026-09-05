# 16 — Failure Modes

Failures should be classified at the earliest layer that produced an incorrect structured value. Repairing later prose can hide the defect while leaving map, list, evidence, and API consumers inconsistent.

| First divergence | Example | Required fail-closed outcome | Primary owner |
| --- | --- | --- | --- |
| Transport/request | Oversized chunked body, malformed JSON, rate limit | Typed 4xx envelope; no agent execution | API middleware/contracts |
| Runtime identity/readiness | Corpus/index/provider/candidate not ready | 503; never fabricate an answer | `runtime.py`, Ask route |
| Understanding | Current incident read as static guidance; two clauses collapsed | Smallest correct typed route or clarification | intent automaton + plan |
| Place/record binding | Ambiguous community, stale selected ID, ordinal mismatch | Requires input or exact-record miss; no substitute record | place/reference + plan |
| Authority | Model requests extra tool/layer/geography | Reject exact call; no dispatch | `AgentQueryPlan`, tool executor |
| Live source | HTTP/schema/metadata failure | Layer unavailable, not zero | `LiveDataService` |
| Live spatial contract | One in-scope feature has invalid or unclassifiable geometry | Quarantine affected layer; never treat it as outside or available-zero | `LiveDataService._map_layer_results` |
| Live row contract | One official feature violates `LiveResult` | Quarantine affected layer; preserve healthy siblings | `LiveDataService._map_layer_results` |
| Retrieval | Index mismatch, missing authority, incomplete stage | Partial/abstention with explicit limitation | retrieval pipeline/service |
| Evidence | Wrong packet ID or non-exact quote | Reject support | evidence packet/validation |
| Publication | High-risk text lacks reviewed typed or quote authority | Drop, quote-only, or official handoff | publication compiler/validator |
| Composition | Mixed clauses blend authority or live prose changes count/status | Canonical sections or fail closed | agent compose/contracts |
| Presentation | UI strengthens unknown/stale/extraction-only state | Weaker truthful projection | backend proof owner; frontend projection |
| Telemetry | Raw content or misleading counters | Reject field / correct metric owner | logging/traces |

## Cross-surface falsification

For every repair, compare answer text, `claims`, `live_results`, `layer_statuses`, `unavailable_layers`, roster/sample IDs, proof cards, map markers, lists, suggestions, and continuation history. A fix is incomplete if only one surface changes.

The live-row and invalid-geometry regressions are the current concrete examples: the first divergence was spatial classification/normalization in `live.py`, not answer prose. The repair changed the layer contract outcome and then exercised public-agent neighbors; it did not teach the composer a phrase about malformed rows.
