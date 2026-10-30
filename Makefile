.PHONY: db dev-api dev-web migrate bootstrap import test lint all
PG_BIN ?= /opt/homebrew/opt/postgresql@18/bin

db:            ## Postgres de desenvolvimento (Docker)
	docker compose up -d db
migrate:       ## Aplica migrations
	cd backend && uv run alembic upgrade head
bootstrap:     ## Semeia catalogo, roles, setor, datasets, dashboards e admin (GAMA_ADMIN_PASSWORD opcional)
	cd backend && uv run python -m app.cli bootstrap
import:        ## Importa o relatorio Ploomes (XLSX) pelo pipeline de ingestao: make import FILE="caminho.xlsx"
	cd backend && uv run python -m app.cli import-xlsx "$(FILE)"
dev-api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000
dev-web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
	cd frontend && npm test
lint:
	cd backend && uv run ruff check . && uv run mypy app && uv run lint-imports
	cd frontend && npm run lint && npm run typecheck
