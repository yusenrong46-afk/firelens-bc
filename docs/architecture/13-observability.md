# 13 — Observability

[`operational_logging.py`](../../src/firelens/operational_logging.py) defines content-free request, feedback, and product-event schemas. [`traces.py`](../../src/firelens/traces.py) writes bounded local JSON traces through an explicit allowlist.

## Recorded request fields

The `firelens.operational_event.v3` event can include trace ID, route, response mode/status, total latency, provider stages/models, error category, evidence/claim/live counts, validation disposition, corpus/release/build/environment identity, tool names/attempt count, retrieval cycles, cache state, fallback category, candidate ID, token counts, and cost.

Raw question, answer, history, coordinates, evidence text, secrets, and user identity are not accepted by this operational schema. Feedback accepts only trace ID and a category; product telemetry uses allowlisted event names.

## Current gaps

- `_answer_request()` emits the normal request event after a non-error response; early not-ready, deadline, and some provider-error branches do not carry the same complete event path.
- Static/mixed work may also be recorded inside the static service, creating parallel logging ownership.
- The Ask route reports `tool_attempts` as `tool_rounds + outer_chat_turns`, not `RequestExecutionPolicy.tool_calls`; the label can mislead.
- `request_stage_metrics()` currently creates only a `total` metric, even though the schema permits planning/live/retrieval/reranking/generation/validation stages.
- Per-layer live failure category and first-divergence stage are not first-class request fields.
- A log schema is not proof that a deployed sink is configured, retained appropriately, or free of platform-added fields.

## Privacy-sensitive traces

Default traces are content-minimized. Local `FIRELENS_TRACE_CONTENT=true` may retain the raw question for explicit debugging. Preview and production configuration rejects that option. Treat trace directories as sensitive local artifacts even when content mode is off.

Tests include `test_api_privacy_boundary.py`, `test_stage_privacy_policy.py`, `test_stage_metrics.py`, `test_product_events.py`, and `test_security_operations.py`. No current deployed-log-drain audit was run.

