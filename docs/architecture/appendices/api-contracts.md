# Appendix — API Contracts

The checked-in public snapshot is [`docs/openapi.v1.json`](../../openapi.v1.json), SHA-256 `eb1030b495586e757e47e8cad4672a5ccf54a3ed7e4a1b8ad8ef573cf4413741` in the local candidate. Executable owners are the FastAPI route modules and strict models; `test_documentation_consistency.py` is the drift guard.

On 2026-09-04, the served schema at production deployment/build `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh` / `40c4c970bf33192ce6a543a6b8dcf5b4799036bd` had SHA-256 `df598029b423c7fbafa84be4e9086c9d1a7b5777abb9685e7d29d9762e38eff7`. The artifacts are not byte-identical; that alone does not establish a semantic contract change, and neither hash proves that the local candidate was deployed or qualified.

## Public endpoints

| Method | Path | Request | Response | Owner / notable failure |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/health/live` | none | `LivenessResponse` | `api/health_feedback.py`; process liveness only |
| GET | `/api/v1/health/ready` | none | `HealthResponse`; 503 when not ready | runtime identity/readiness |
| GET | `/api/v1/guided-questions` | none | hash-bound `GuidedQuestionsResponse` | advertised frozen registry |
| POST | `/api/v1/ask` | `QueryRequest` | `AskResponse` | 45-second default server deadline; typed error envelope |
| GET | `/api/v1/live/map` | `layers`, optional `bbox` query strings | `LiveMapResponse` | invalid layer/bounds 400; source failures 404/502/503 |
| GET | `/api/v1/live/summary` | none | `LiveCurrentSummary` | unavailable count is `null`, never zero |
| POST | `/api/v1/live/nearby` | `NearMeRequest` | `NearMeResponse` | coarse location, ordered layer status, explicit pagination |
| POST | `/api/v1/feedback` | trace ID + allowlisted category | 202 `FeedbackResponse` | content-free feedback event |
| POST | `/api/v1/product-events` | allowlisted event name | 202 `ProductEventResponse` | content-free product event |

When debug is enabled outside production, code also installs `POST /api/v1/search` and `GET /api/v1/debug/chunks/{chunk_id}`. They are deliberately absent from the public OpenAPI snapshot.

## Ask request

`QueryRequest` contains:

- `question`: normalized, 1–2,000 characters;
- `history`: at most six user/assistant turns, each normalized and at most 6,000 characters;
- `location`: optional `LocationInput` with a community label or coordinate pair, rounded/coarse and radius 1–200 km;
- `context`: selected live result ID, up to 100 unique visible live IDs, and optional bounded viewport.

Unknown model fields are rejected. Anonymous guarded writes default to a 65,536-byte body maximum and an instance-local 30-per-60-second limit.

## Ask response modes

`grounded`, `background`, `capability`, `scope_redirect`, `abstention`, `partial`, `live`, `mixed`, `conflict`, and `requires_input`. `status` is separately `answer`, `abstention`, or `error`. Consumers must not infer authority from status alone; use mode, sections, publication, freshness, layer status, and limitations.

The full field groups are documented in [Data contracts](data-contracts.md). Final response validation binds claims/evidence/live records/proof/roster IDs before serialization.

## Errors

Documented error statuses are 400, 404, 413, 429, 500, 502, and 503. `ErrorEnvelope` contains `trace_id`, `error_kind`, sanitized `message`, and `retryable`. Request validation can also produce FastAPI validation responses as configured by the installed handler. Provider invalid-request/invalid-response maps to 502; transient provider/source unavailability generally maps to 503; live selected-record miss maps to 404.
