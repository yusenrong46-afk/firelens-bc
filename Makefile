PYTHON := .venv/bin/python
FIRELENS := .venv/bin/firelens
FRONTEND := apps/web

.PHONY: setup check verify run benchmark benchmark-v1-red-team benchmark-live benchmark-retrieval benchmark-retrieval-v1-5 benchmark-contextual benchmark-v1-1-zero-cost benchmark-v1-1-paid owner-review-template qualify-owner-review retrieval-review-packet retrieval-review-template qualify-retrieval-review qualify-retrieval-v1-5 qualify-live-v1-5 capture-live-slo verify-live-slo prepare-firewall model-bakeoff canary live-smoke openapi secret-scan productbench-deterministic productbench-offline productbench-provider source-aware-conversation v1-6-baseline v1-6-gate v1-6-report v1-6-package-verify v1-6-round2-baseline claimbench-v2 v1-6-hard-probe v1-6-performance v1-6-pre-release-performance v1-6-retrieval-dry-run v1-6-round2-gate v1-6-round2-report v1-6-round3-eval v1-6-round3-report typed-claim-review-export v1-6-structured-publication-eval vercel-preview vercel-production

setup:
	@test -d .venv || python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .
	npm --prefix $(FRONTEND) ci
	npm --prefix $(FRONTEND) run setup:browsers

openapi:
	$(PYTHON) scripts/export_openapi.py
	npm --prefix $(FRONTEND) run generate:api

secret-scan:
	$(PYTHON) scripts/secret_scan.py

check: secret-scan openapi
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts
	$(PYTHON) -m mypy
	$(PYTHON) -m pytest -q -m "not browser and not qualification"
	npm --prefix $(FRONTEND) test
	npm --prefix $(FRONTEND) run test:tooling
	npm --prefix $(FRONTEND) run build

verify: check
	$(PYTHON) -m pytest -q
	npm --prefix $(FRONTEND) run test:sites
	@if [ -d "$(HOME)/Library/Caches/ms-playwright" ]; then \
		PLAYWRIGHT_BROWSERS_PATH="$(HOME)/Library/Caches/ms-playwright" npm --prefix $(FRONTEND) run test:e2e; \
	else \
		npm --prefix $(FRONTEND) run test:e2e; \
	fi

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

productbench-deterministic:
	$(PYTHON) scripts/run_productbench.py --mode offline \
		--output output/productbench/offline.json

productbench-offline: productbench-deterministic

source-aware-conversation:
	$(PYTHON) scripts/run_source_aware_conversation.py \
		--output output/evaluation/source_aware_conversation_offline.json

productbench-provider:
	@test -n "$(MAX_COST_USD)" || (echo "Set MAX_COST_USD to a positive ceiling."; exit 2)
	$(PYTHON) scripts/run_productbench.py --mode provider --max-cost-usd "$(MAX_COST_USD)" \
		--output output/productbench/provider.json

owner-review-template:
	$(PYTHON) scripts/owner_semantic_review.py template

qualify-owner-review:
	$(PYTHON) scripts/owner_semantic_review.py validate

retrieval-review-template:
	$(PYTHON) scripts/retrieval_owner_review.py template

retrieval-review-packet:
	$(PYTHON) scripts/retrieval_owner_review.py packet

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

capture-live-slo:
	$(PYTHON) scripts/live_slo_evidence.py capture

verify-live-slo:
	$(PYTHON) scripts/live_slo_evidence.py verify \
		--report output/qualification/v1_5_2_live_slo.json

prepare-firewall:
	$(PYTHON) scripts/prepare_vercel_firewall.py

benchmark-contextual:
	$(FIRELENS) compare-contextual-retrieval

canary:
	$(FIRELENS) canary --calls 30 --max-cost-usd 0.50

model-bakeoff:
	$(FIRELENS) bakeoff-models --case-limit 12 --max-cost-usd 0.50

live-smoke:
	FIRELENS_RUN_OPENROUTER_SMOKE=1 $(PYTHON) -m pytest tests/test_openrouter_smoke.py -q

v1-6-baseline:
	$(PYTHON) scripts/v1_6_upgrade.py baseline --run-tests --seal

v1-6-gate:
	$(PYTHON) scripts/v1_6_upgrade.py gate

v1-6-report:
	$(PYTHON) scripts/v1_6_upgrade.py report

v1-6-package-verify:
	$(PYTHON) scripts/v1_6_upgrade.py package-verify

v1-6-round2-baseline:
	@test -f docs/reports/V1_6_ROUND2_BEFORE_SNAPSHOT.json
	@test -f docs/reports/V1_6_ROUND2_FABLE_MUTATION_REPRODUCTION.json
	$(PYTHON) -c "import json; from pathlib import Path; p=Path('docs/reports/V1_6_ROUND2_BEFORE_SNAPSHOT.json'); json.loads(p.read_text())"

claimbench-v2:
	$(PYTHON) scripts/claimbench_v2.py evaluate

v1-6-hard-probe:
	$(PYTHON) scripts/run_hard_probe.py --mode offline --output output/benchmark/v1_6_round2/hard_probe.json

v1-6-performance:
	$(PYTHON) scripts/v1_6_round2_performance.py

v1-6-pre-release-performance:
	$(PYTHON) scripts/v1_6_round2_performance.py --measured 100 \
		--report-output docs/reports/V1_6_PRE_RELEASE_PERFORMANCE.json

v1-6-retrieval-dry-run:
	$(PYTHON) scripts/v1_6_round2_retrieval.py --dry-run

v1-6-round2-gate:
	$(PYTHON) scripts/v1_6_round2_gate.py

v1-6-round2-report:
	@test -f docs/reports/V1_6_ROUND2_ENGINEERING_REPORT.md
	@echo "docs/reports/V1_6_ROUND2_ENGINEERING_REPORT.md"

v1-6-round3-eval:
	$(PYTHON) scripts/v1_6_round3_eval.py --output-dir docs/reports

v1-6-round3-report:
	@test -f docs/reports/V1_6_ROUND3_ENGINEERING_REPORT.md
	@echo "docs/reports/V1_6_ROUND3_ENGINEERING_REPORT.md"

typed-claim-review-export:
	$(PYTHON) scripts/typed_claim_review_export.py --output tmp/typed_claim_review_queue.html

v1-6-structured-publication-eval:
	$(PYTHON) scripts/v1_6_structured_publication_eval.py

vercel-preview:
	$(PYTHON) scripts/deploy_vercel.py

vercel-production:
	$(PYTHON) scripts/deploy_vercel.py --prod
