# Gamatermic Dash

Sistema interno de dashboards da Gamatermic: carga de relatórios (XLSX/CSV do Ploomes), dashboards para gestores (desktop/celular) e **modo TV** com pareamento de dispositivos.
Plano técnico completo: [`.cursor/plans/plano_técnico_gamatermic_dash_f12dd096.plan.md`](.cursor/plans/plano_técnico_gamatermic_dash_f12dd096.plan.md). Decisões e desvios: [`docs/adr`](docs/adr).

**Stack:** FastAPI + SQLAlchemy 2 async + Alembic + PostgreSQL · React 18 + TypeScript + Vite + TanStack Query + ECharts · Caddy (TLS) · Docker Compose em VPS.

## Rodando localmente

Pré-requisitos: Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16+ (Docker **ou** instalação local).

```bash
make db                      # Postgres em :5433 (Docker). Sem Docker: initdb/pg_ctl local na porta 5433, usuário "gama", bancos gamatermic e gamatermic_test
make migrate
GAMA_ADMIN_PASSWORD='uma frase longa' make bootstrap     # admin@gamatermic.local + datasets e dashboards de partida
make import FILE=".cursor/docs/Vendas Ploomes 2025_2026.xlsx"   # carrega as 4 abas do relatório atual
make dev-api                 # http://localhost:8000/api/docs
make dev-web                 # http://localhost:5173
```

Entre com o admin criado no bootstrap. Para uma TV: abra `http://localhost:5173/tv`, copie o código e aprove em **TVs e playlists** (ou escaneie o QR).

## Testes e qualidade

```bash
make test    # backend (pytest + Postgres real) e frontend (vitest)
make lint    # ruff, mypy, import-linter, eslint, tsc
```

Backend: 98+ testes (auth, RBAC, auditoria, ingestão, query engine, dispositivos, migrações). Os testes usam o banco `gamatermic_test` e recriam o schema a cada execução.

## Operação (produção)

`docker compose -f docker-compose.prod.yml --env-file .env up -d` — veja [`docs/runbooks`](docs/runbooks): deploy/rollback, backup e restore, rotação de segredos, TV (kiosk), carga travada.

## Estrutura

```
backend/   app/{core,modules/<domínio>/{router,service,repository,models,schemas},workers,bootstrap}  alembic/  tests/
frontend/  src/{app,shared,features/<feature>,pages}
docs/      adr/  runbooks/  contracts/ (CSV/XLSX e OpenAPI)
scripts/   backup.sh restore.sh restore-test.sh
```

## Dados reais

O relatório `Vendas Ploomes 2025_2026.xlsx` (em `.cursor/docs`) **não é versionado** (`.gitignore`). Ele alimenta os datasets `vendas`, `propostas_ganhas`, `propostas_perdidas` e `propostas_abertas`; o contrato de colunas está em [`docs/contracts/datasets.md`](docs/contracts/datasets.md).
