# Commands and tests

Run from the repository root. Confirm current branch and status first. Commands below are grounded in `Makefile`, `README.md:46-116`, `pyproject.toml`, and frontend `package.json`.

## Setup and local run

| Command | Purpose | Modifies? | Prerequisites / notes |
|---|---|---:|---|
| `make setup` | Create `.venv`, install `requirements.lock`, install package, run `npm ci` | Yes, local dependency files | Network and Python/Node; never print `.env`. |
| `make run` | Build frontend and serve FastAPI/UI at `127.0.0.1:8000` | Yes, build output | Requires setup, corpus/index, and normally `OPENROUTER_API_KEY` for readiness. |
| `.venv/bin/firelens doctor` | Check corpus, index, and provider readiness | No intended app changes | May report missing key/resources. |
| `.venv/bin/firelens search "..."` | Run a search-oriented inspection | No intended app changes | Provider calls may occur; use only with authorization and a cost budget. |
| `.venv/bin/firelens ask "..."` | Run a full answer path | No intended app changes | May call OpenRouter and write traces. |

## Zero-cost verification

| Command | Purpose | Modifies? | Expected result |
|---|---|---:|---|
| `make verify` | Secret scan, generated OpenAPI/types, Ruff, format check, mypy, Python tests, frontend tests/build, Sites packaging, Playwright | Build/generated artifacts may be refreshed | All configured checks pass and `git diff --exit-code` is clean afterward. |
| `.venv/bin/python -m pytest -q` | Python suite from `pyproject.toml` | No intended app changes | Test summary; use focused paths for lessons. |
| `npm --prefix prototype/firelens-rag-ui test` | Frontend unit/accessibility tests | No intended app changes | Vitest summary. |
| `npm --prefix prototype/firelens-rag-ui run build` | Typecheck and Vite/Sites build | Yes, frontend `dist` output | Build succeeds; generated output is disposable. |
| `.venv/bin/python scripts/run_hard_probe.py --mode offline` | 105-case deterministic hard probe with controlled doubles | Writes output artifact | No network/provider cost; does not prove live model quality. |
| `git diff --check` | Whitespace/error check | No | Empty output is expected. |

## Evaluation and paid/network commands

Treat these as opt-in and require a positive explicit budget where supported:

- `make benchmark-v1-1-paid` — cost-capped live conversation benchmark.
- `make benchmark-retrieval-v1-5` — development retrieval comparison with a hash-bound addendum.
- `make qualify-retrieval-v1-5` — three-repetition sealed retrieval qualification; do not tune from its holdout.
- `make canary` — 30 repeated live calls.
- `make model-bakeoff` — identical-evidence generation comparison.
- `make live-smoke` — opt-in OpenRouter smoke tests.
- `make qualify-live-v1-5` — official live-source qualification.

**Evidence rule:** paid output is an observation tied to its report manifest, not a blanket release claim. Human semantic review remains distinct from exact citation checks.

## Test-reading map

- `tests/test_static_rag.py` — core service contracts, evidence, routing, and response behavior.
- `tests/test_v1_5_rag.py` — V1.5 routing, evidence sufficiency, conflict/aspect behavior.
- `tests/test_provider_api.py` — provider schema, retries, deadlines, cancellation, body bounds.
- `tests/test_live.py` and `tests/test_live_answering.py` — live fetch, geometry, cache, freshness, chat/map composition.
- `tests/test_benchmark.py`, `test_qualification.py`, `test_owner_review.py`, `test_retrieval_review.py` — evaluation and review contracts.
- `tests/test_security_operations.py`, `test_request_guard.py`, `test_release_operations.py` — security and release boundaries.
- `prototype/firelens-rag-ui/tests/App.test.tsx` and `tests/e2e/app.spec.ts` — UI state, accessibility, and browser flows.

For every test, ask: what failure does it detect, what boundary does it protect, and what remains untested?
