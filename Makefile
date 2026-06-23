# Daily Scholar — local-mode shortcuts.
#
# All targets are thin wrappers over setup.sh / start.sh / pytest so the
# shell scripts stay the source of truth. `make help` lists every target.

.PHONY: help setup start backend test clean stop migrate vapid

help: ## Show this help
	@awk 'BEGIN{FS=":.*##";printf "Daily Scholar — make targets:\n\n"} \
		/^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## One-shot setup: venv, deps, .env, migrations, frontend install
	@./setup.sh

start: ## Launch backend + frontend, wait for /health, attach until Ctrl-C
	@./start.sh

backend: ## Launch backend only (no frontend)
	@./start.sh --backend-only

test: ## Run the pytest suite
	@. venv/bin/activate && pytest

clean: ## Stop any rogue dev servers on :8000 / :3000
	@-lsof -ti:8000 | xargs -r kill -9
	@-lsof -ti:3000 | xargs -r kill -9
	@echo "✓ Ports cleared."

stop: clean ## Alias for `make clean`

migrate: ## Apply pending alembic migrations against the configured DB
	@. venv/bin/activate && alembic upgrade head

vapid: ## Generate a VAPID keypair for Web Push (one-time)
	@. venv/bin/activate && python scripts/generate_vapid_keys.py
