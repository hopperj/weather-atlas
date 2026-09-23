SHELL := /bin/bash
COMPOSE := docker compose
COMPOSE_WAIT_TIMEOUT ?= 300
.DEFAULT_GOAL := help

.PHONY: help install run check-env deps dev-up dev-down dev-restart dev-logs ps observability-up observability-down db-create db-verify test test-python test-frontend lint format airflow-test production-build clean

help: ## Show available development commands
	@awk 'BEGIN {FS = ":.*## "; printf "Available targets:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Prepare configuration, storage, dependencies, and all images
	./install.sh

run: ## Start and verify the complete platform, including observability
	./run.sh

check-env:
	@test -f .env || (echo "Copy .env.example to .env first" && exit 1)
	@$(COMPOSE) config --quiet

deps: ## Install the locked host-side test and development dependencies
	uv sync --frozen --group dev
	npm --prefix frontend ci

dev-up: check-env ## Build, start, and wait for the development stack
	$(COMPOSE) up --build -d --wait --wait-timeout $(COMPOSE_WAIT_TIMEOUT)

dev-down: check-env ## Stop containers without deleting persistent data
	$(COMPOSE) down

dev-restart: check-env ## Restart the development stack
	$(COMPOSE) restart

dev-logs: check-env ## Follow logs from all services
	$(COMPOSE) logs -f --tail=200

ps: check-env ## Show service status
	$(COMPOSE) ps

observability-up: check-env ## Start the optional Prometheus and Grafana profile
	$(COMPOSE) --profile observability up -d --wait prometheus grafana

observability-down: check-env ## Stop the optional observability services
	$(COMPOSE) --profile observability stop prometheus grafana

db-create: check-env ## Manually apply all unapplied application migrations
	./scripts/apply_migrations.sh --yes

db-verify: check-env ## Verify the application database and migration checksums
	./scripts/verify_database.sh

test: test-python test-frontend ## Run all tests that do not require the full Compose stack

test-python: ## Run Python unit tests
	uv run --frozen --group dev pytest

test-frontend: ## Run frontend tests and production build
	npm --prefix frontend ci
	npm --prefix frontend run test
	npm --prefix frontend run build

lint: deps ## Lint Python and frontend code
	uv run --frozen --group dev ruff check python tests airflow
	npm --prefix frontend run lint

format: deps ## Format Python and frontend code
	uv run --frozen --group dev ruff format python tests airflow
	npm --prefix frontend run format

airflow-test: check-env ## List every Airflow DAG and verify there are no import errors
	$(COMPOSE) run --rm airflow-cli dags list
	$(COMPOSE) run --rm airflow-cli dags list-import-errors

production-build: check-env ## Build deployable service images
	$(COMPOSE) build weather-api tile-api frontend

clean: ## Remove local build/test caches (persistent Docker data is preserved)
	rm -rf .pytest_cache .ruff_cache htmlcov frontend/dist
