# beara_bones Makefile. Run from repo root. Use `make help` for targets.
DOCKER_COMPOSE_FILE=docker-compose.yml

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@echo ""
	@echo "Usage: make [option]"
	@echo ""
	@echo "Options:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

.PHONY: build
build:  ## Build docker services
	docker-compose -f $(DOCKER_COMPOSE_FILE) build

.PHONY: start
start:  ## Start docker services (detached mode)
	docker-compose -f $(DOCKER_COMPOSE_FILE) up -d

.PHONY: stop
stop:  ## Stop docker services
	docker-compose -f $(DOCKER_COMPOSE_FILE) stop

.PHONY: run-dev
run-dev:  ## Run Django dev server (SQLite, settings_dev)
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py runserver

.PHONY: test
test:  ## Run Django tests
	cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py test

.PHONY: dbt-test
dbt-test:  ## Run dbt with LIMIT 100 (requires data_modelling/)
	cd data_modelling && dbt build

.PHONY: dbt-full
dbt-full:  ## Run dbt with full data (requires data_modelling/)
	cd data_modelling && dbt build --vars '{"is_dev_run": false}'
