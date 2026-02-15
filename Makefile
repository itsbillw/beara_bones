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
test:  ## Run Django tests (home + data apps)
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py test

.PHONY: test-football
test-football:  ## Run football package unit tests (from repo root)
	uv run pytest tests/test_football.py -v

.PHONY: test-all
test-all: test test-football  ## Run Django and football tests

.PHONY: coverage
coverage:  ## Run all tests with combined coverage report
	uv run coverage erase
	(cd beara_bones && COVERAGE_FILE=$(CURDIR)/.coverage DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run coverage run -m django test home data)
	COVERAGE_FILE=$(CURDIR)/.coverage uv run coverage run -a -m pytest tests/ -q
	uv run coverage report --omit='*/migrations/*,*/tests.py,*/test_*.py,manage.py'

# --- Linting & pre-commit ---
.PHONY: install-hooks
install-hooks:  ## Install pre-commit git hooks (run once per clone)
	uv run pre-commit install

.PHONY: lint
lint:  ## Run all pre-commit checks (ruff, mypy, bandit, etc.)
	uv run pre-commit run --all-files

.PHONY: check
check: lint test-all  ## Run lint + all tests (use before push)

# Football pipeline (run from repo root; requires uv and optional deps: uv pip install -e ".[data]")
.PHONY: ingest
ingest:  ## Phase 1: Fetch fixtures from RapidAPI → MinIO
	uv run python -m football.ingest

.PHONY: transform
transform:  ## Phase 2: Raw JSON → CSV/Parquet
	uv run python -m football.transform

.PHONY: soda-check
soda-check:  ## Phase 3: Soda 4 contract verification (local, no cloud)
	uv run soda contract verify --data-source football/soda/ds_config.yml --contract football/soda/contracts/fixtures.yaml

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
pipeline:  ## Ingest → transform → DuckDB → Soda → dbt → MariaDB → processed Parquet
	uv run python -m football.pipeline

.PHONY: pipeline-all
pipeline-all:  ## Same as pipeline but for all League×Season from Admin (uses run_football_pipeline)
	cd beara_bones && uv run python manage.py run_football_pipeline

.PHONY: rebuild-football
rebuild-football:  ## Rebuild MariaDB from MinIO (no API; raw or processed)
	cd beara_bones && uv run python manage.py rebuild_football_from_minio

# --- Production deploy (run after git pull on server) ---
SYSTEMCTL_SERVICE ?= uvicorn
.PHONY: deploy
deploy:  ## After git pull: uv sync, migrate, collectstatic, restart service (SYSTEMCTL_SERVICE=uvicorn)
	uv sync
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings uv run python manage.py migrate
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings uv run python manage.py collectstatic --noinput --clear
	sudo systemctl restart $(SYSTEMCTL_SERVICE)
