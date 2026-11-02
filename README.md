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

Backend: 126 testes (auth, RBAC, auditoria, ingestão, query engine, dispositivos, migrações, configurações e IA com Groq falsa). Os testes usam o banco `gamatermic_test` e recriam o schema a cada execução.

## Painel analítico (desktop)

No painel, o botão **Análise** abre `/dashboards/:id/analise` ([ADR 0012](docs/adr/0012-painel-analitico.md)): período, filtros por campo (vários valores, exclusão, intervalo, texto), drill por clique em hierarquia (`viz_config.drill_path`) e por tempo (ano → trimestre → mês → dia), breadcrumb, tela cheia com troca de visual e "agrupar por", registros de origem paginados, busca, exportação CSV (`analysis:export`) e visões salvas. Tudo fica na URL (link reabre a mesma visão). **Perguntar à IA** (botão no topo, precisa da Groq ativa em Configurações): perguntas em português viram consultas validadas; o backend calcula e o gráfico aparece no chat, com "Aplicar à tela" e "Adicionar ao painel". Depois de atualizar: `make migrate` e `make bootstrap`.

## Assistente de IA (Groq)

Gera sugestões de gráficos a partir de um pedido em texto ([ADR 0010](docs/adr/0010-ia-geracao-de-dashboards.md)). A IA recebe só nomes e tipos dos campos, nunca as linhas nem campos `pii`.

1. Crie a chave em [console.groq.com/keys](https://console.groq.com/keys) (de preferência ative *Zero Data Retention* em *Data Controls*).
2. No sistema, como Administrador: **Configurações → IA (Groq)**, cole a chave, escolha o modelo, marque *IA ativa*, **Salvar** e **Testar conexão**. A chave fica cifrada (Fernet) e nunca é exibida de volta.
3. Quem cria dashboards usa **Dashboards → Criar com IA**: escolhe um dataset (ou anexa CSV/XLSX, que vira dataset novo), descreve o que quer ver e marca os gráficos que quer usar. O painel nasce fora do ar.
4. Para completar um painel existente: no editor, **Gráficos com IA** usa o dataset do painel, não repete gráficos, sugere onde encaixar cada um e, se precisar, mudanças nos existentes (com prévia do layout); você marca o que aceitar.

No editor, os gráficos se redimensionam arrastando o canto e o layout é salvo ao soltar. Abaixo do tamanho completo, cada tipo troca para uma visão compacta (ranking, valor com tendência, lista); nada fica menor que 2×2 ([ADR 0011](docs/adr/0011-graficos-adaptaveis-e-autosave-do-layout.md)).

E2E sem a Groq real: `node frontend/e2e/fake-groq.mjs` (porta 8765), API com `GAMA_GROQ_BASE_URL=http://127.0.0.1:8765/openai/v1` e `E2E_FAKE_GROQ=1 npx playwright test e2e/ai.spec.ts`. As configurações `fake-groq`, `api-e2e` e `web-e2e` em `.claude/launch.json` sobem esse ambiente contra o banco `gamatermic_e2e`.

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
