PYTHON := .venv/bin/python
FIRELENS := .venv/bin/firelens
FRONTEND := prototype/firelens-rag-ui

.PHONY: setup verify run benchmark benchmark-v1-red-team benchmark-live benchmark-retrieval benchmark-retrieval-v1-5 benchmark-contextual benchmark-v1-1-zero-cost benchmark-v1-1-paid owner-review-template qualify-owner-review retrieval-review-template qualify-retrieval-review qualify-retrieval-v1-5 qualify-live-v1-5 model-bakeoff canary live-smoke openapi secret-scan

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

benchmark: benchmark-v1-red-team benchmark-v1-1-zero-cost

benchmark-v1-red-team:
	$(FIRELENS) benchmark --split red_team \
		--output output/benchmark/v1_red_team_report.json \
		--review-packet output/benchmark/v1_red_team_review.md

benchmark-live:
	$(FIRELENS) benchmark --max-cost-usd 1.90 \
		--output output/benchmark/v1_report.json \
		--review-packet output/benchmark/v1_semantic_review.md

benchmark-v1-1-zero-cost:
	$(FIRELENS) benchmark-conversation --offline \
		--output output/benchmark/v1_1_conversation_offline_report.json \
		--review-packet output/benchmark/v1_1_conversation_offline_review.md

benchmark-v1-1-paid:
	$(FIRELENS) benchmark-conversation --max-cost-usd 1.50 \
		--output output/benchmark/v1_1_conversation_live_report.json \
		--review-packet output/benchmark/v1_1_conversation_live_review.md

owner-review-template:
	$(PYTHON) scripts/owner_semantic_review.py template

qualify-owner-review:
	$(PYTHON) scripts/owner_semantic_review.py validate

retrieval-review-template:
	$(PYTHON) scripts/retrieval_owner_review.py template

qualify-retrieval-review:
	$(PYTHON) scripts/retrieval_owner_review.py validate

benchmark-retrieval:
	$(FIRELENS) tune-retrieval --max-cost-usd 1.25

benchmark-retrieval-v1-5:
	$(FIRELENS) tune-retrieval --max-cost-usd 1.25 \
		--relevance-addendum data/evaluation/benchmark_v1_5_relevance_addendum.yaml \
		--output output/benchmark/v1_5_retrieval_comparison.json

qualify-retrieval-v1-5:
	$(PYTHON) scripts/run_retrieval_qualification.py --repetitions 3 --max-cost-usd 0.75

qualify-live-v1-5:
	$(PYTHON) scripts/run_live_qualification.py

benchmark-contextual:
	$(FIRELENS) compare-contextual-retrieval

canary:
	$(FIRELENS) canary --calls 30 --max-cost-usd 0.50

model-bakeoff:
	$(FIRELENS) bakeoff-models --case-limit 12 --max-cost-usd 0.50

live-smoke:
	FIRELENS_RUN_OPENROUTER_SMOKE=1 $(PYTHON) -m pytest tests/test_openrouter_smoke.py -q
