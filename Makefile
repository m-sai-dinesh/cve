.PHONY: help up down seed demo-traces test eval build frontend-dev backend-dev

help:
	@echo "ModernRx — GxP-Aware AI Application Modernization Advisor"
	@echo ""
	@echo "Targets:"
	@echo "  make seed         Seed demo users and AcmeLIMS project in SQLite"
	@echo "  make test         Run backend unit & golden findings test suite (pytest)"
	@echo "  make eval         Run full PRD evaluation benchmarks (eval/run_eval.py)"
	@echo "  make backend-dev  Start FastAPI backend on http://localhost:8000"
	@echo "  make frontend-dev Start Next.js frontend dev server on http://localhost:3000"
	@echo "  make build        Build Next.js frontend production bundle"
	@echo "  make up           Start Neo4j docker container (optional)"
	@echo "  make down         Stop Neo4j docker container"

seed:
	python -m backend.app.seed

test:
	python -m pytest backend/tests -v

eval:
	python eval/run_eval.py

backend-dev:
	uvicorn backend.app.main:app --reload --port 8000

frontend-dev:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

up:
	docker compose up -d

down:
	docker compose down
