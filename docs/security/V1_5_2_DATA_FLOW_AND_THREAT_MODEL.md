# V1.5-2 data flow and LLM threat model

Status: implemented controls plus explicitly open deployment evidence. This document is not a
production privacy attestation or security approval.

## Data inventory

| Boundary | Data sent | Retained by FireLens | Enforced control | Open release evidence |
|---|---|---|---|---|
| Browser to FireLens API | Question, at most six bounded conversation turns, or a user-entered community/coarse coordinates after a Near Me action | Request content is not accepted by operational logging; process memory is transient | Request/body bounds, same-origin API, no-store API responses, coordinates rounded to two decimals by client and server | Browser privacy probes against URLs, history, service workers, analytics, and traces |
| API to official BC sources | Bounded layer queries, coarse bounding box, or community lookup | Privacy-safe source-version-bound live cache only | Official allowlisted adapters, deadlines, bounded concurrency, fail-closed parsing, explicit partial/unavailable state | Three-region production SLO capture and upstream contribution measurements |
| API to OpenRouter | Bounded messages/evidence needed by the selected response plan | FireLens does not persist provider payloads | Production requires ZDR; requests deny data collection and provider fallback; model output is untrusted until deterministic validation passes | Eligible-endpoint canary and deployed ZDR/readiness evidence |
| API to Vercel logs/drain | Content-free request/feedback event | Intended retention is exactly 30 days | Strict Pydantic event schemas do not accept question, answer, evidence, coordinates, names, email, device fingerprint, or arbitrary metadata | Vercel Pro drain configuration, deletion/retention proof, and access-control review |
| Browser to product analytics | Content-free task and failure-class events only | Aggregate anonymous analytics, separate from trace-linked feedback | No conversation/location fields are part of the event contract | Deployed analytics configuration and network capture |
| Feedback to restricted operations view | 32-character trace ID and one allowlisted category | Intended retention is exactly 30 days | `POST /api/v1/feedback` forbids free text and extra fields; rate and body limits apply | Durable sink, role access, daily critical-feedback review, and expiry proof |
| Static corpus/build to deployed runtime | Governed corpus, vector index, repair registry, runtime candidate, and built client | Immutable build artifact | Artifact allowlist, corpus/vector hashes, candidate identity, evaluation-data exclusion | Real Vercel export and Docker staged-artifact comparison |

Precise coordinates, raw questions, answers, source passages, deterministic question hashes,
authorization headers, human-review content, and arbitrary client metadata are prohibited from
telemetry. Location is session-scoped and is not introduced into URLs, caches, or persistence.

## Trust boundaries

The browser, model output, upstream live payloads, corpus changes, generated code, and benchmark
summaries are untrusted inputs. Deterministic contracts validate structure, provenance, authority,
freshness, claim support, privacy, and release identity. Human reviewers remain authoritative for
semantic correctness, accessibility, product safety, and release adjudication.

## OWASP LLM control map

| Risk family | V1.5-2 control | Required verification |
|---|---|---|
| Prompt injection | No arbitrary tools; retrieved text is evidence, not executable instruction; system contract and response validation remain authoritative | Adversarial corpus and live-source probes |
| Sensitive information disclosure | Content-free telemetry, coarse location, no query hash, ZDR/no-fallback provider policy, no-store API responses | Production network/log/privacy probes |
| Supply-chain and source poisoning | Official-source registry, hashes, quarantine/repair provenance, corpus admission, lockfiles, SBOM workflow | Human review of every quarantined repair and current advisory scans |
| Improper output handling | React text rendering, validated typed response contracts, canonical official links, restrictive CSP | Browser XSS/link/markup probes and human safety review |
| Excessive agency | Models cannot call tools, change labels, select providers, declare live safety, or bypass validation | Architecture tests and critical-code review |
| Misinformation | Claim-to-evidence validation, semantic invariants, conflict/abstention states, static/live separation | Dual human semantic review, untouched holdout, V3 qualification |
| Unbounded consumption | Request and body limits, deadlines, context/output caps, bounded provider retries/concurrency/circuit state | Vercel Firewall proof, distributed abuse test, cost ledger |
| Vector/embedding weakness | Governed development evaluation, V2 permanent regression, fresh sealed V3, stage-specific experiments only | Three V3 repetitions and slice-level case evidence |

## Deletion and incident handling

No account, saved location, alert, or location-history store exists. Operational feedback and
content-free telemetry must expire after 30 days in the deployed sink. A privacy leak, ZDR failure,
silent partial live response, wrong artifact, or safety-boundary breach is a rollback condition.
Rollback evidence must include both the immutable artifact and environment snapshot because code
rollback alone does not restore environment values.

## Primary references

- OpenRouter Zero Data Retention and programmatic ZDR endpoint roster:
  <https://openrouter.ai/docs/guides/features/zdr>
- OpenRouter provider routing controls:
  <https://openrouter.ai/docs/guides/routing/provider-selection>
- OWASP Top 10 for Large Language Model Applications:
  <https://owasp.org/www-project-top-10-for-large-language-model-applications/>
- Office of the Privacy Commissioner of Canada mobile privacy guidance:
  <https://www.priv.gc.ca/en/privacy-topics/technology/mobile-and-digital-devices/mobile-apps/gd_app_201210/>
