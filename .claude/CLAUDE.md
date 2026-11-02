# gamatermic-dash

Sistema interno de dashboards da Gamatermic. Carrega relatórios (XLSX/CSV exportados do
Ploomes), mostra dashboards para gestores (desktop e celular) e roda em **modo TV**, com
pareamento de dispositivos, playlists e atualização quase em tempo real. Um tenant, uma VPS,
poucos usuários (~50) e poucas TVs (~20). Login local, sem SSO, sem SaaS de terceiros no
caminho crítico.

Conversa, documentação e comentários em português. Identificadores de código em inglês,
como no plano técnico.

## Fontes da verdade

Não reabrir o que estes arquivos já decidiram. Se o código divergir deles, o documento
vence até existir um ADR em `docs/adr/` explicando o que mudou.

| Arquivo | Papel |
|---|---|
| [`.cursor/plans/plano_técnico_gamatermic_dash_f12dd096.plan.md`](../.cursor/plans/plano_técnico_gamatermic_dash_f12dd096.plan.md) | Como: arquitetura, modelo de dados, API, fluxos, segurança/LGPD, fases e critérios de aceite |
| [`docs/adr/`](../docs/adr/) | Decisões e desvios. `0000-desvios-do-plano.md` lista onde o implementado difere do plano |
| [`docs/contracts/datasets.md`](../docs/contracts/datasets.md) | Contrato de colunas dos datasets do relatório Ploomes |
| [`docs/contracts/openapi.snapshot.json`](../docs/contracts/openapi.snapshot.json) | Contrato da API. Mudança exige regerar o snapshot e o cliente TS |
| [`docs/runbooks/`](../docs/runbooks/) | Deploy e rollback, backup e restore, rotação de segredos, TV em kiosk, carga travada |
| [`README.md`](../README.md) | Como rodar, testar e operar |

Ler o plano (seções 4 a 8) antes de desenhar uma feature. Ler o ADR 0000 antes de assumir
que o código segue o plano à risca.

## Estado

**MVP (Fase 0 a E10) implementado em 30/10/2026**: autenticação (E1), RBAC com concessões e
painel admin (E2), auditoria (E3), datasets e ingestão CSV/XLSX (E4), query engine e
widgets (E5), editor de dashboards (E6), dispositivos e playlists (E7), player TV (E8),
visualização para gestão (E9), arquivos de deploy e runbooks (E10). Verificado: 98+ testes
de backend, testes de frontend (vitest), E2E Playwright, ruff/mypy/import-linter/eslint/tsc
limpos; pareamento → exibição → revogação validado em navegador real.

Dados reais: `Vendas Ploomes 2025_2026.xlsx` (em `.cursor/docs/`, **não versionado**) alimenta
`vendas`, `propostas_ganhas`, `propostas_perdidas` e `propostas_abertas`. O relatório não
tem contratos nem metas: dashboards atuais são *Vendas – Visão Geral* e *Propostas – Funil
Comercial*, e a meta do gauge é um placeholder editável (R$ 4 mi/mês).

**Assistente de IA (Groq) e aba Configurações implementados em 30/10/2026** ([ADR 0010](../docs/adr/0010-ia-geracao-de-dashboards.md),
plano em `docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`): `modules/settings` (chave cifrada, somente escrita, `settings:manage`)
e `modules/ai` (prompt só com metadados não-`pii`, saída JSON estrita, tradução para `QuerySpec` validado). Testes usam
Groq falsa (`httpx.MockTransport`, `frontend/e2e/fake-groq.mjs`); qualidade com a conta real ainda não medida.

**Painel analítico (desktop) implementado em 01/11/2026** ([ADR 0012](../docs/adr/0012-painel-analitico.md), plano `docs/planos/GAMA-FEAT-PAINEL-ANALITICO.md`): rota `/dashboards/:id/analise`, `modules/analysis` (campos, valores, busca, registros, exportação, visões), `DataRequest.overrides` para regrupar widgets sem gravar. **Chat por IA e POC de tradução (Etapas 1 e 5) não começaram.**

**Pendentes que dependem de terceiros:**

- Spike B no hardware real da TV (24 h, rede da empresa).
- Validação dos KPIs e metas com a diretoria.
- Documentação oficial Ploomes/Omie ([ADR 0008](../docs/adr/0008-conectores-ploomes-omie.md)).
- VPS e domínio. `docker compose` de produção **nunca foi executado** (sem daemon Docker na
  máquina de desenvolvimento).

**Fase 2 e 3 não começaram** (conectores reais, webhooks, rascunho/versionamento de
dashboards, rollups, MFA/SSO, reset por e-mail, alertas, novos setores). Não antecipar sem
ADR. A primeira entrega da Fase 2 é o pull incremental de Negócios/Propostas do Ploomes,
depois do spike de documentação.

## Princípios que recusam código

Toda ideia passa por estes. Se não passar, não implementar.

1. **Autorização no backend.** Frontend só esconde UI. Toda rota não pública declara política; o teste que varre o OpenAPI falha se uma rota não declarar.
2. **Sem SQL livre.** Dados só saem por `QuerySpec` declarativo. Nome de campo é resolvido contra `dataset_fields` (lista branca), nunca interpolado.
3. **Carga atômica e idempotente.** Falha no meio não altera os dados vigentes. Reenviar o mesmo arquivo não duplica linhas.
4. **A TV nunca fica em branco.** Sem conexão ou com fonte atrasada, mantém o último dado e mostra o estado. *Conexão* e *fonte* são estados distintos.
5. **Um widget com erro não derruba a dashboard.**
6. **Dispositivo não é usuário.** Principal `device` só acessa `/display/*` e só as dashboards da playlist. Token de usuário e de dispositivo não se misturam.
7. **Segredo nunca em log, git ou token.** Tokens e credenciais só como hash no banco; segredos de conectores cifrados; `.env` fora do git.
8. **Dado de cliente é minimizado.** Campos pessoais marcados `pii` e mascarados sem permissão. Não carregar CPF/dados de pessoa física.
9. **Tempo no servidor.** UTC no banco, `America/Sao_Paulo` na resolução de períodos relativos e na exibição.
10. **Dinheiro é `decimal`.** A API serializa como string; o frontend formata com `Intl` pt-BR/BRL.

### Anti-escopo

Não propor nem implementar no MVP: SSO, MFA, reset de senha por e-mail, conectores reais
Ploomes/Omie, webhooks de entrada, rascunho/versionamento de dashboards, rollups, alertas
(WhatsApp/e-mail), exportação PDF/PNG, campos calculados, segurança por linha, multi-tenant,
app nativo, edição colaborativa em tempo real, SQL livre pelo usuário.

Também fora: microserviços, Redis/Celery, GraphQL, WebSocket (SSE basta), Kubernetes, motor
analítico separado (DuckDB/ClickHouse), Redux. Se algum passar a fazer sentido, entra como ADR.

## Arquitetura que não se renegocia

```
frontend (React SPA)  →  API FastAPI  →  PostgreSQL
                          Worker       →  PostgreSQL   (fila, ingestão, housekeeping)
Caddy (TLS, mesma origem: / → web, /api → API)
```

Monólito modular: API e worker compartilham o mesmo código em `backend/app`.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic (env async), Pydantic v2, argon2-cffi, PyJWT, structlog, uv.
- **Frontend:** React 18 + TypeScript strict, Vite, React Router, TanStack Query, Zustand, ECharts, react-grid-layout (só no editor), Tailwind, `@microsoft/fetch-event-source`.
- **Armazenamento híbrido:** metadados tipados (`datasets`, `dataset_fields`, `ingestion_runs`…) + linhas em `dataset_rows` com `data` JSONB. Novo dataset não exige DDL nem deploy. Promoção a tabela tipada só se p95 > 300 ms medido ([ADR 0002](../docs/adr/0002-armazenamento-hibrido-jsonb.md)); `QueryExecutor` isola essa troca.
- **Fila em Postgres** (`jobs`, `FOR UPDATE SKIP LOCKED`) atrás de `workers/queue.py`, não Procrastinate (ADR 0000 #3, [ADR 0003](../docs/adr/0003-fila-em-postgres.md)). O job nasce na **mesma transação** que `uploaded_files` e `ingestion_runs`. Worker em processo próprio em produção (`python -m app.workers.runner`); dentro da API só em dev (`GAMA_RUN_WORKER_INPROCESS`).
- **Atualização da TV** ([ADR 0005](../docs/adr/0005-tempo-quase-real-tv.md)): `pg_notify` no commit da carga → `Broker` (LISTEN) → SSE `dataset_updated {dataset_id, version}` → player invalida com debounce e refaz o lote por REST com ETag (304). Fallback: polling de 60 s. SLO: carga → TV em ≤ 5 s (p95). Heartbeat SSE de 25 s.
- **Autenticação** ([ADR 0006](../docs/adr/0006-autenticacao.md)): access JWT HS256 de 10 min, só em memória no frontend; refresh opaco rotativo em cookie `HttpOnly; SameSite=Strict; Path=/api/v1/auth`, reuso fora da janela de 10 s revoga a família. **Permissões não vão no token**: resolvidas no servidor, cache de 60 s invalidado por `authz_version`. Senha argon2id, mínimo 12 caracteres, lockout de 5 falhas por 15 min.
- **TV:** pareamento estilo RFC 8628 (`user_code` de 8 caracteres, 10 min, uso único), credencial opaca revogável + JWT `typ=device` de 15 min. TV recebe 401 em rota de usuário.
- **RBAC com escopo:** permissão global via roles + escopo `all|granted` + `resource_grants` por recurso/setor. Guarda anti-escalonamento e do último Administrador.
- **Lançamento de painéis** ([ADR 0009](../docs/adr/0009-lancamento-de-paineis.md)): `dashboards.status` `published`/`offline`; fora do ar só editores veem e a TV pula. Link de compartilhamento é interno (login + permissão), nunca público.
- **Auditoria** `audit_logs` é append-only, gravada na mesma transação da ação, sem segredos no diff.
- **Migrações:** Alembic, revisão manual do autogenerate, `alembic check` no CI. Migração aplicada em produção é imutável: correção é migração nova.
- **IDs:** UUID. **Sem `DELETE` de dado de negócio** onde o plano prevê soft delete (`deleted_at`, `status`).
- **Contrato da API:** OpenAPI é a fonte única. Cliente TS gerado em `frontend/src/shared/api/schema.d.ts`; nunca editar à mão.

## Camadas

Backend por domínio, com camadas dentro de cada módulo em `backend/app/modules/<domínio>/`:

`router` → `service` → `repository` → `models` (+ `schemas` Pydantic)

O router só chama service. Repository só toca modelos e banco. Regra imposta pelo
`import-linter` (`pyproject.toml`). Listagens são filtradas por autorização **no repositório**,
nunca «buscar tudo e filtrar no router». Transversal em `app/core` (config, db, security,
authz, errors, crypto, rate limit, `csvsafe`).

Ingestão: `connectors` (contrato `kind`, `config_schema`, `test_connection`, `fetch`) →
`pipeline` extract → transform → validate → load. Conector novo só muda o `fetch`.

Frontend por feature em `frontend/src/features/<feature>`; features não importam umas das
outras, só `shared`. Páginas finas. Registry de widgets em `features/widgets`.

Erros em `application/problem+json`. Logs JSON (structlog) com `request_id`. Sem `print`.

## O que testar

- **Backend:** pytest + pytest-asyncio contra **Postgres real** (banco `gamatermic_test`, schema recriado a cada execução). Nunca SQLite: JSONB, `ON CONFLICT` e LISTEN/NOTIFY só se validam no mesmo motor. Alvos: auth e refresh, matriz RBAC, auditoria, ingestão (idempotência, `replace_snapshot`, rollback), compilador do QuerySpec, períodos, pareamento, migrações.
- **Frontend:** vitest + Testing Library + MSW; axe para acessibilidade; máquina de estados do player TV.
- **E2E:** Playwright (`frontend/e2e`), incluindo mobile. Snapshots visuais não vão ao git.
- **Contrato:** o CI compara o OpenAPI gerado com `docs/contracts/openapi.snapshot.json` e o cliente TS com o snapshot.

Teste de borda de mês, virada de dia e fuso nos períodos relativos.

## Build

- Backend: `uv`, Python 3.12. Frontend: Node 22.
- `make db` (Postgres em `:5433`, usuário `gama`, bancos `gamatermic` e `gamatermic_test`; sem Docker, `initdb`/`pg_ctl` local nessa porta) → `make migrate` → `GAMA_ADMIN_PASSWORD='…' make bootstrap` → `make import FILE=".cursor/docs/Vendas Ploomes 2025_2026.xlsx"` → `make dev-api` (`:8000`, docs em `/api/docs`) e `make dev-web` (`:5173`).
- `make test` roda pytest e vitest. `make lint` roda ruff, mypy, import-linter, eslint e `tsc`.
- Mudou a API: `scripts/update-openapi-snapshot.sh`, revisar o diff e rodar `npm run gen:api` no frontend.
- Configuração por variáveis `GAMA_*` (`backend/app/core/config.py`). `.env.example` é o modelo; `.env` nunca vai ao git. Segredos de produção com `openssl rand -base64 48` e chave Fernet própria.
- Produção: `docker compose -f docker-compose.prod.yml --env-file .env up -d`, serviço `migrate` antes da API, Caddy com TLS automático, backups criptografados (`scripts/backup.sh`, restore testado por `restore-test.sh`). O `docker-compose.yml` de dev sobe só o Postgres.
- CI (`.github/workflows`): ruff, mypy, import-linter, pytest, drift de migrations, contrato OpenAPI, eslint, tsc, vitest, build, `pip-audit`, `npm audit`, Trivy.

## Armadilhas já medidas

Não redescobrir:

- Caddy precisa de `flush_interval -1` para o SSE não ser bufferizado. Cliente SSE usa `fetch-event-source` com header `Authorization` (o `EventSource` nativo não envia header e token em query string vaza em log).
- O relatório Ploomes tem uma coluna calculada (*Prazo de Pagamento*): ler o XLSX com `data_only` (valor em cache). Colunas extras viram aviso; coluna obrigatória ausente **falha a carga inteira**; rejeição acima de 20 % das linhas não altera nada.
- O relatório traz pedidos e propostas, **não contratos**. Propostas têm revisões: widgets filtram `ultima_revisao = true` para não contar revisão antiga duas vezes. Chave natural das propostas é `Código` + `Número da revisão`; `propostas_abertas` usa `replace_snapshot`.
- «Faturamento» = soma de `Valor` dos pedidos por `Data do Pedido` (não é nota fiscal). Comparação com período anterior usa o mesmo recorte decorrido. Regras assumidas, a confirmar com a diretoria.
- Campo `contato` é `pii`: mascarado para quem não tem `dataset:manage`.
- Rate limit é janela deslizante **em memória por processo** (ADR 0000 #10): com 2 workers o limite é por processo. Redis ou Caddy só na Fase 2/3.
- Cache de último dado da TV fica em `localStorage`, não IndexedDB (ADR 0000 #8).
- SQLAlchemy async: `expire_on_commit=False` e eager loading explícito. Sem lazy load. Carga em lote via Core, não ORM.
- Export CSV/XLSX e relatório de erros neutralizam células que começam com `= + - @` (`core/csvsafe.py`). Dado é sempre renderizado como texto.
- Tema TV vem de `[data-theme="tv"]`, aplicado de forma síncrona (os gráficos leem as CSS vars na montagem). Cores e fontes oficiais (extraídas do site, ADR 0007) estão em `frontend/src/styles.css`; texto sobre laranja é azul-escuro por contraste AA.
- `.cursor/docs/*.xlsx|csv` são dados reais de negócio e estão no `.gitignore`. Nunca commitar.

## Como mudar o plano

Escopo novo que caiba na fase atual: implementar. Escopo que antecipe fase, viole um princípio
ou troque uma decisão da tabela da seção 12 do plano: parar e dizer o conflito, em vez de
codar em volta. Decisão que substitua o plano vai para `docs/adr/`, um arquivo por decisão
(próximo número livre).

## Regras de output

1. Resumo O que foi feito
2. Arquivos alterados
3. Sugestao de commit
4. O que o usuario deve fazer
