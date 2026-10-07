COMPOSE := docker compose
RUN     := $(COMPOSE) run --rm

.DEFAULT_GOAL := help
.PHONY: help dev down logs reset test lint fmt migrations lock shell import-assets

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

# First run: copy the example and replace every "change-me" with a random secret
.env:
	@while IFS= read -r line; do \
	  case "$$line" in \
	    *=change-me) printf '%s=%s\n' "$${line%%=*}" "$$(od -An -tx1 -N24 /dev/urandom | tr -d ' \n')" ;; \
	    *) printf '%s\n' "$$line" ;; \
	  esac; \
	done < .env.example > .env
	@echo ".env created with random secrets"

dev: .env ## Build and start the stack (app, database, Keycloak)
	$(COMPOSE) up --build --detach --wait
	@echo ""
	@echo "  App:       http://localhost:8000"
	@echo "  Keycloak:  http://localhost:8080/admin  (admin / KEYCLOAK_ADMIN_PASSWORD in .env)"
	@echo "  Demo users: melder, rm.mueller, rm.schmidt, ciso, app-admin, ohne-rolle (DEMO_USER_PASSWORD in .env)"

down: ## Stop the stack, keep data
	$(COMPOSE) down

logs: ## Follow the logs of all services
	$(COMPOSE) logs --follow

reset: ## Stop the stack and DELETE database and Keycloak volumes
	$(COMPOSE) --profile tools down --volumes

test: .env ## Run the test suite against PostgreSQL (ARGS="-k name" to filter)
	$(RUN) --build test pytest $(ARGS)

lint: .env ## ruff (lint + format check) and mypy
	$(RUN) --build tools sh -c "ruff check . && ruff format --check . && mypy ."

fmt: .env ## Apply ruff formatting and safe fixes
	$(RUN) tools sh -c "ruff check --fix . && ruff format ."

migrations: .env ## Create migrations after model changes
	$(RUN) test python src/manage.py makemigrations

lock: .env ## Re-resolve uv.lock after editing pyproject.toml
	$(RUN) tools uv lock

shell: .env ## Django shell inside the running web container
	$(COMPOSE) exec web python src/manage.py shell

import-assets: .env ## Re-import the CMDB sample data
	$(COMPOSE) exec web python src/manage.py import_assets src/apps/cmdb/data/assets.csv
