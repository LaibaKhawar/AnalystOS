# Developer shortcuts. Backend commands run in backend/.venv (python3.11 -m venv backend/.venv).
PY := backend/.venv/bin/python
.PHONY: setup dev-db api worker frontend test lint typecheck models eval data sandbox up down

setup:            ## install backend + frontend dependencies and build the sandbox image
	python3.11 -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
	cd frontend && npm install
	docker build -t analystos-sandbox:latest sandbox

dev-db:           ## start Postgres (5434) and Redis (6380) for local development
	docker run -d --name analystos-devdb -e POSTGRES_USER=analystos -e POSTGRES_PASSWORD=analystos \
	  -e POSTGRES_DB=analystos -p 5434:5432 pgvector/pgvector:pg16
	docker run -d --name analystos-devredis -p 6380:6379 redis:7-alpine
	sleep 5 && docker exec analystos-devdb psql -U analystos -c "CREATE DATABASE analystos_test"
	docker exec analystos-devdb psql -U analystos -d analystos_test -c "CREATE EXTENSION IF NOT EXISTS vector"

api:              ## run the API with reload
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload --port 8000

worker:           ## run the Celery worker (thread pool works on macOS)
	cd backend && .venv/bin/celery -A app.workers.celery_app worker --loglevel=INFO --pool=threads --concurrency=2

frontend:         ## run the Vite dev server
	cd frontend && npm run dev

test:             ## backend unit + integration tests, frontend unit tests
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run test

lint:
	cd backend && .venv/bin/ruff check app evals tests && .venv/bin/ruff format --check app evals tests
	cd frontend && npm run lint

typecheck:
	cd backend && .venv/bin/mypy app
	cd frontend && npm run typecheck

data:             ## regenerate the deterministic benchmark datasets
	cd backend && .venv/bin/python -m evals.datasets.generate

models:           ## create the 16K-context Ollama models used by default
	ollama create analystos-qwen3-14b -f ollama/Modelfile.qwen3-14b
	ollama create analystos-qwen3-8b -f ollama/Modelfile.qwen3-8b

eval:             ## run the evaluation suite against the configured LLM
	cd backend && .venv/bin/python -m evals.run

sandbox:
	docker build -t analystos-sandbox:latest sandbox

up:               ## full stack in Docker
	docker compose up --build

down:
	docker compose down
