# 15 — Security and Privacy

## Request boundary

[`BoundedAnonymousRequestMiddleware`](../../src/firelens/api/middleware.py) guards Ask, live map/nearby, and feedback writes. It checks declared and streamed body size, applies an instance-local anonymous rate limit, and replays a bounded ASGI body to FastAPI. Defaults are 65,536 bytes and 30 requests per 60 seconds; these are configuration defaults, not a distributed abuse-control guarantee.

Strict Pydantic models reject unknown fields and bound question, history, location, map context, pagination, evidence, and response sizes. Exception handlers return typed sanitized envelopes. Security headers are applied in middleware.

## Provider privacy boundary

[`privacy_policy.py`](../../src/firelens/privacy_policy.py), [`config.py`](../../src/firelens/config.py), and [`providers/openrouter.py`](../../src/firelens/providers/openrouter.py) define the OpenRouter boundary. Production configuration requires data collection denial, disabled provider fallbacks, and required ZDR for embedding and generation; startup preflights required models. Reranking has a separately represented ZDR state and must not be described as universally protected unless its observed configuration says so.

The current campaign observed the named production baseline’s readiness identity and configured model names but did not make a provider call or inspect provider receipts/secrets. Eligible endpoint inventory, actual routing/fallback, platform retention, and secret configuration therefore remain **UNPROVEN**.

## Location and telemetry

The public location contract accepts only a community label or coarse coordinates rounded to two decimals. Exact-address-like labels are rejected. The browser requests approximate geolocation only after user action and holds it in session memory. Operational/feedback/product schemas exclude raw question, answer, history, exact location, evidence text, and secrets.

Local content tracing is the intentional exception: when explicitly enabled, it may retain raw question text. Preview/production reject this setting. Local trace files and development outputs still require access control and deletion discipline.

## Threats and tests

Primary threats are prompt-injection authority widening, oversized/streamed bodies, anonymous abuse, secret leakage, exact-location capture, provider retention mismatch, malicious upstream data, stale bundle execution, and unsafe rendering. Relevant tests include `test_request_body_middleware.py`, `test_request_guard.py`, `test_api_privacy_boundary.py`, `test_security_operations.py`, `test_stage_privacy_policy.py`, `test_intent_capability_bypass.py`, and frontend asset/security tests.

This chapter is an implementation review, not a penetration test, privacy certification, threat-model sign-off, or deployed-control attestation.
