PYTHON := .venv/bin/python

.PHONY: help setup database migrate ingest check-data train train-one forward-test refresh compare \
        analysis eval-assistant run snapshot portfolio-summary web-install web-dev web-build test

help:             ## list the targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------------------------
setup:            ## create the virtual environment and install pinned dependencies
	python3.11 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

database:         ## create the database and both roles, apply migrations, grant read access (safe to re-run)
	./scripts/setup_database.sh

migrate:          ## apply pending sql/migrations only
	$(PYTHON) -m src.database_migrations

# --- Market data -------------------------------------------------------------------------------
ingest:           ## download full price history into Postgres (safe to re-run)
	$(PYTHON) -m src.market_data.price_download

check-data:       ## check the stored prices, write evals/results/price_data_checks_<date>.json
	$(PYTHON) -m src.market_data.price_quality_checks

# --- Agents ------------------------------------------------------------------------------------
train:            ## train and test the full grid (skips agents already stored), then compare with buy-and-hold
	$(PYTHON) -m src.trading.experiment_grid

train-one:        ## one agent: make train-one ALGORITHM=PPO TICKER=NVDA FEATURE_SET=indicators SEED=0
	$(PYTHON) -m src.trading.experiment_grid --algorithm $(or $(ALGORITHM),PPO) --ticker $(or $(TICKER),NVDA) \
		--feature-set $(or $(FEATURE_SET),standard) --seed $(or $(SEED),0)

forward-test:     ## run stored agents on the days after TEST_END
	$(PYTHON) -m src.trading.forward_test

refresh:          ## download new days, check the data, then forward-test every agent on them
	$(PYTHON) -m src.market_data.price_download --refresh
	$(PYTHON) -m src.market_data.price_quality_checks
	$(PYTHON) -m src.trading.forward_test

compare:          ## recompute the strategy vs buy-and-hold comparisons from stored curves
	$(PYTHON) -m src.trading.strategy_comparison

analysis:         ## re-run the analysis notebook in place
	.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/results_analysis.ipynb

# --- Assistant and API -------------------------------------------------------------------------
eval-assistant:   ## run evals/assistant_questions.json through Qwen: make eval-assistant [MODEL=qwen3:4b]
	$(PYTHON) -m src.assistant.assistant_evaluation $(if $(MODEL),--model $(MODEL))

run:              ## start the API on API_HOST:API_PORT (docs at /docs); needs Ollama running
	$(PYTHON) -m src.api_server

# --- Dashboard ---------------------------------------------------------------------------------
snapshot:         ## export results and pre-generated answers to DASHBOARD_DATA_DIR for the static site
	$(PYTHON) -m src.dashboard_snapshot

portfolio-summary: ## write results for the portfolio site: make portfolio-summary FILE=../Portfolio/portfolio/data/rlStrategyLabResults.json
	$(PYTHON) -m src.portfolio_summary $(or $(FILE),../Portfolio/portfolio/data/rlStrategyLabResults.json)

web-install:      ## install the dashboard's npm packages
	cd web && npm install

web-dev:          ## run the dashboard locally at http://localhost:3000
	cd web && npm run dev

web-build:        ## build the static dashboard into web/out
	cd web && npm run build

# --- Tests -------------------------------------------------------------------------------------
test:             ## unit tests (no network; database tests skip if Postgres is not set up)
	$(PYTHON) -m pytest -q
