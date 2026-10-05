.PHONY: setup test lint security build up down eval doctor
PY ?= python3
setup:            ## Install backend (venv) and frontend deps
	cd backend && $(PY) -m venv venv && ./venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm ci
test:             ## Backend + frontend tests with coverage
	cd backend && ./venv/bin/python -m pytest --cov=. --cov-report=term-missing:skip-covered
	cd frontend && npm test
lint:             ## Strict lint on rewritten modules, ratchet on legacy, ESLint
	cd backend && ./venv/bin/ruff check $$(cat ../.strict-lint-paths)
	PATH=backend/venv/bin:$$PATH ./scripts/lint_ratchet.sh
	cd frontend && npx eslint src --quiet
security:         ## Dependency + SAST scans
	cd backend && ./venv/bin/pip-audit -r requirements.txt && ./venv/bin/bandit -q -r . -x ./tests,./venv -ll
	cd frontend && npm audit --omit=dev
doctor:           ## What is still dummy / unsafe?
	cd backend && ./venv/bin/python -m scripts.doctor
eval:             ## Synthetic smoke eval (NOT a benchmark)
	cd backend && ./venv/bin/python -m eval.run_eval eval/cases.synthetic.json --allow-synthetic
build:
	cd frontend && npm run build
up:               ## Full stack in containers
	docker compose up --build
down:
	docker compose down
