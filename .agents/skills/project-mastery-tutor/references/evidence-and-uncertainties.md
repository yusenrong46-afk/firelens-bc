# Evidence and uncertainties

This file records the state discovered while creating the skill. It is a starting ledger, not permanent truth. Recheck the current commit and relevant artifacts before using a row as evidence.

## Observed

- `main` was clean at `b00544c1927ffa12d98689f6a4b0b44b6c7de7e1` during skill creation.
- `README.md:9-13` explicitly says the principal-remediation candidate, paid probe rerun, owner retrieval review, and semantic review remain deferred; do not call the current tree production-qualified solely from README metrics.
- `README.md:38-44` states that local Python code owns policy, routing, retrieval, source metadata, evidence construction, validation, and public responses; OpenRouter supplies bounded planning, embeddings, reranking, and generation.
- `README.md:148-152` reports 170 chunks across eight approved sources, a 170 × 1,536 vector index, and ten quarantined repair-derived chunks; verify manifests before repeating the claim.
- `pyproject.toml` pins Python dependencies; `requirements.lock` and the frontend `package-lock.json` provide locked install inputs.
- `Makefile:11-25` defines setup and zero-cost verification; `.github/workflows/verify.yml` runs it in a fresh Python 3.12/Node 22 environment with pinned installs.
- `src/firelens/answering/service.py`, `retrieval/pipeline.py`, `answering/context.py`, `answering/grounded.py`, and `answering/validate.py` expose the main static request lifecycle.
- `src/firelens/live.py:145-580` provides one typed live data service for chat and map.

## Inferred

- The repository is intended to be learned as a vertical slice: product boundary → contracts → startup → one grounded request → live path → tests/evaluation → operations.
- `StaticRAGService` is the central orchestration seam for static search/answer behavior; this is supported by its constructor and `execute_search`/`execute_ask` methods, but ownership may evolve.
- `docs/TECHNICAL_HANDBOOK.md` and `docs/learning/` are useful teaching aids, yet current source and executed tests outrank them when they disagree.

## Unknown or requiring refresh

- Whether the current local environment has every locked dependency; a shared editable environment can import a different checkout than the current worktree.
- Whether OpenRouter, ArcGIS, geocoder, Vercel, Render, or production preview behavior is currently available; local inspection cannot prove live availability.
- Whether historical paid reports match the current corpus/index hashes; rerun only with a deliberate budget and current manifests.
- Whether all human owner-review artifacts are complete and signed; inspect the current review sidecars and reports rather than relying on historical counts.
- Whether generated frontend/build artifacts are current after future changes; regenerate and inspect diffs.

## How to report uncertainty

Say what was checked, what was not checked, and what evidence would resolve it. Example: “**OBSERVED:** the route is declared in `api.py`; **UNKNOWN:** anonymous preview behavior was not exercised in this session.”
