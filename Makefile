PYTHON := .venv/bin/python
FIRELENS := .venv/bin/firelens
FRONTEND := prototype/firelens-rag-ui

.PHONY: setup verify run benchmark benchmark-live benchmark-retrieval model-bakeoff canary live-smoke openapi secret-scan

setup:
	@test -d .venv || python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .
	npm --prefix $(FRONTEND) ci

openapi:
	$(PYTHON) scripts/export_openapi.py
	npm --prefix $(FRONTEND) run generate:api

secret-scan:
	$(PYTHON) scripts/secret_scan.py

verify: secret-scan openapi
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts
	$(PYTHON) -m mypy
	$(PYTHON) -m pytest -q
	npm --prefix $(FRONTEND) test
	npm --prefix $(FRONTEND) run build
	npm --prefix $(FRONTEND) run test:sites
	npm --prefix $(FRONTEND) run test:e2e

run:
	npm --prefix $(FRONTEND) run build
	$(FIRELENS) serve --host 127.0.0.1 --port 8000

benchmark:
	$(FIRELENS) benchmark --split red_team \
		--output output/benchmark/v1_red_team_report.json \
		--review-packet output/benchmark/v1_red_team_review.md

benchmark-live:
	$(FIRELENS) benchmark --max-cost-usd 1.90 \
		--output output/benchmark/v1_report.json \
		--review-packet output/benchmark/v1_semantic_review.md

benchmark-retrieval:
	$(FIRELENS) tune-retrieval --max-cost-usd 1.25

canary:
	$(FIRELENS) canary --calls 30 --max-cost-usd 0.50

model-bakeoff:
	$(FIRELENS) bakeoff-models --case-limit 12 --max-cost-usd 0.50

live-smoke:
	FIRELENS_RUN_OPENROUTER_SMOKE=1 $(PYTHON) -m pytest tests/test_openrouter_smoke.py -q
