COMPOSE := docker compose
RUN     := $(COMPOSE) run --rm

# Containers with the bind-mounted source run as the owner of the working tree
export APP_UID := $(shell id -u)
export APP_GID := $(shell id -g)

.DEFAULT_GOAL := help
.PHONY: help dev seed down logs reset test lint fmt migrations lock shell import-assets css sbom audit trace prod prod-down messages messages-check

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

dev: .env ## Build and start the stack (app, database, Keycloak) with demo data if empty
	$(COMPOSE) up --build --detach --wait
	$(COMPOSE) exec -T web python src/manage.py seed_demo
	@echo ""
	@echo "  App:       http://localhost:8000"
	@echo "  Keycloak:  http://localhost:8080/admin  (admin / KEYCLOAK_ADMIN_PASSWORD in .env)"
	@echo "  Mailpit:   http://localhost:8025  (e-mails of escalations and hand-overs)"
	@echo "  Demo users: melder, rm.mueller, rm.schmidt, ciso, app-admin, ohne-rolle (DEMO_USER_PASSWORD in .env)"

seed: .env ## Fill an empty register with demo risks (make dev does this too)
	$(COMPOSE) exec -T web python src/manage.py seed_demo

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

css: .env ## Build the stylesheet once, minified (the css service rebuilds it during make dev)
	$(RUN) --build --no-deps tools tailwindcss --input=src/assets/app.css --output=src/static/css/build/app.css --minify

sbom: .env ## Write the CycloneDX SBOM to sbom/is-risk-classifier.cdx.json (M-02)
	$(RUN) --build --no-deps tools python tools/sbom.py --output sbom/is-risk-classifier.cdx.json

audit: .env ## Check the runtime dependencies against known vulnerabilities (M-02)
	$(RUN) --build --no-deps tools sh -c "uv export --format requirements-txt --frozen --no-dev --no-emit-project --quiet -o /tmp/requirements.txt && pip-audit --requirement /tmp/requirements.txt --require-hashes --disable-pip --strict --progress-spinner off"

trace: .env ## Write docs/traceability.md: requirement -> tests
	$(RUN) --build test pytest --collect-only --quiet --trace-report=docs/traceability.md

prod: .env ## Start the production-like stack (runtime image, gunicorn, read-only)
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml up --build --detach --wait

prod-down: ## Stop the production-like stack, keep data
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml down

messages: .env ## Extract UI texts, apply tools/translations_en.py, compile the English catalogue
	$(RUN) --build --no-deps tools sh -c "cd src && python manage.py makemessages --locale en --no-obsolete --add-location file --ignore 'staticfiles/*' --ignore 'pdf_renderer/*' --ignore 'notify_gateway/*' && cd .. && python tools/fill_po.py && cd src && python manage.py compilemessages --locale en"

messages-check: .env ## Fail if a UI text has no English translation (CI)
	$(RUN) --build --no-deps tools sh -c "cd src && python manage.py makemessages --locale en --no-obsolete --add-location file --ignore 'staticfiles/*' --ignore 'pdf_renderer/*' --ignore 'notify_gateway/*' && cd .. && python tools/fill_po.py --check"

lock: .env ## Re-resolve uv.lock after editing pyproject.toml
	$(RUN) tools uv lock

shell: .env ## Django shell inside the running web container
	$(COMPOSE) exec web python src/manage.py shell

import-assets: .env ## Re-import the CMDB sample data
	$(COMPOSE) exec web python src/manage.py import_assets src/apps/cmdb/data/assets.csv
