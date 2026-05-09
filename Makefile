SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---- Tooling versions (advisory; CI pins exact) ----
PNPM ?= pnpm
UV ?= uv
DOCKER ?= docker
COMPOSE ?= docker compose

# ---- Paths ----
COMPOSE_FILE := deploy/docker-compose.yml

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- Setup ----
.PHONY: install
install: install-js install-py ## Install all workspace dependencies
	@echo "✓ install complete"

.PHONY: install-js
install-js: ## Install JS workspace dependencies
	$(PNPM) install

.PHONY: install-py
install-py: ## Install Python workspace dependencies via uv
	$(UV) sync --all-packages

# ---- Dev loop ----
.PHONY: dev
dev: ## Bring up all containers (PG, CH, MinIO, Redis, services)
	$(COMPOSE) -f $(COMPOSE_FILE) up --build

.PHONY: dev-detached
dev-detached: ## Bring up all containers in the background
	$(COMPOSE) -f $(COMPOSE_FILE) up --build -d

.PHONY: down
down: ## Tear down dev containers
	$(COMPOSE) -f $(COMPOSE_FILE) down

.PHONY: down-volumes
down-volumes: ## Tear down dev containers AND wipe volumes
	$(COMPOSE) -f $(COMPOSE_FILE) down -v

# ---- Migrations + bootstrap ----
.PHONY: migrate
migrate: migrate-pg migrate-ch ## Apply PG + CH migrations

.PHONY: migrate-pg
migrate-pg: ## Apply Postgres migrations (alembic upgrade head)
	cd services/api && $(UV) run judge-cli migrate-pg

.PHONY: migrate-ch
migrate-ch: ## Apply ClickHouse SQL migrations (idempotent)
	cd services/api && $(UV) run judge-cli migrate-ch

.PHONY: bootstrap
bootstrap: ## Create default org/project/api_key (prints API key once)
	cd services/api && $(UV) run judge-cli bootstrap

.PHONY: logs
logs: ## Tail logs from all dev containers
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f --tail=100

# ---- Quality ----
.PHONY: lint
lint: lint-js lint-py lint-go ## Lint everything

.PHONY: lint-js
lint-js:
	$(PNPM) lint

.PHONY: lint-py
lint-py:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

.PHONY: lint-go
lint-go:
	@for d in services/ingest; do \
	  if [ -d "$$d" ] && [ -f "$$d/go.mod" ]; then \
	    echo "==> golangci-lint $$d"; \
	    (cd $$d && golangci-lint run ./...); \
	  fi; \
	done

.PHONY: fmt
fmt: ## Format all code
	$(PNPM) format
	$(UV) run ruff format .
	@for d in services/ingest; do \
	  if [ -d "$$d" ] && [ -f "$$d/go.mod" ]; then \
	    (cd $$d && gofmt -w .); \
	  fi; \
	done

.PHONY: typecheck
typecheck: ## Type-check everything
	$(PNPM) typecheck
	$(UV) run pyright

.PHONY: test
test: test-js test-py test-go ## Run all unit tests

.PHONY: test-js
test-js:
	$(PNPM) test

.PHONY: test-py
test-py:
	$(UV) run pytest

.PHONY: test-go
test-go:
	@for d in services/ingest; do \
	  if [ -d "$$d" ] && [ -f "$$d/go.mod" ]; then \
	    echo "==> go test $$d"; \
	    (cd $$d && go test ./...); \
	  fi; \
	done

# ---- Build ----
.PHONY: build
build: ## Build all artifacts
	$(PNPM) build
	@for d in services/ingest; do \
	  if [ -d "$$d" ] && [ -f "$$d/go.mod" ]; then \
	    (cd $$d && go build ./...); \
	  fi; \
	done

# ---- Clean ----
.PHONY: clean
clean: ## Remove build artifacts
	$(PNPM) clean
	rm -rf .turbo node_modules **/dist **/build **/.next
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
