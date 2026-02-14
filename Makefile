# beara_bones Makefile. Run from repo root. Use `make help` for targets.
.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@echo ""
	@echo "Usage: make [option]"
	@echo ""
	@echo "Options:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

.PHONY: run-dev
run-dev:  ## Run Django dev server (SQLite, settings_dev)
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py runserver

.PHONY: test
test:  ## Run Django tests
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py test

# Football pipeline (run from repo root; requires uv and optional deps: uv pip install -e ".[data]")
.PHONY: ingest
ingest:  ## Phase 1: Fetch fixtures from RapidAPI → MinIO
	uv run python -m football.ingest

.PHONY: transform
transform:  ## Phase 2: Raw JSON → CSV/Parquet
	uv run python -m football.transform

.PHONY: soda-check
soda-check:  ## Phase 3: Soda Core quality checks (local, no cloud)
	uv run soda scan -d football -c football/soda/configuration.yml football/soda/checks/fixtures.yml

.PHONY: dbt-build
dbt-build:  ## Phase 4: dbt-duckdb build
	cd data_modelling && uv run dbt build

.PHONY: dbt-test
dbt-test:  ## Alias for dbt-build
	$(MAKE) dbt-build

.PHONY: dbt-full
dbt-full:  ## Run dbt with full data (requires data_modelling/)
	cd data_modelling && uv run dbt build --vars '{"is_dev_run": false}'

.PHONY: pipeline
pipeline:  ## Ingest → transform → load DuckDB → soda-check → dbt-build
	uv run python -m football.pipeline
