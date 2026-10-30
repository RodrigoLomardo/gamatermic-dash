# ADR 0000 — Desvios conscientes em relação ao plano técnico

Status: aceito · Data: 30/10/2026

O plano foi seguido de ponta a ponta. Os desvios abaixo foram feitos por motivos concretos (dados reais, simplicidade operacional) e estão reversíveis.

| # | Plano | Implementado | Motivo |
|---|-------|--------------|--------|
| 1 | Datasets "Vendas" e "Contratos" (hipótese) | `vendas`, `propostas_ganhas`, `propostas_perdidas`, `propostas_abertas` | O relatório real (XLSX Ploomes) contém pedidos e propostas, **não contratos**. Dashboards: *Vendas – Visão Geral* e *Propostas – Funil Comercial*. Contratos entram quando houver arquivo/contrato de dados. |
| 2 | XLSX só na Fase 2 | XLSX já no MVP (leitura somente-leitura, limite anti zip-bomb, macros recusadas) | A fonte atual é XLSX multi-aba. Mesmo pipeline do CSV. |
| 3 | Fila com Procrastinate | Fila própria em Postgres (`jobs`, `FOR UPDATE SKIP LOCKED`) atrás de `workers/queue.py` | Mesma garantia (job nasce na mesma transação do run), zero dependência extra; interface fina permite trocar por Procrastinate/Celery. Ver ADR 0003. |
| 4 | Staging UNLOGGED por run + merge | Merge em lotes direto em `dataset_rows` numa única transação | Atomicidade idêntica (rollback total, testado) com menos I/O. Contadores inserido/atualizado/inalterado por pré-consulta de hash. |
| 5 | `dataset.version` incrementa a cada carga | Idem (incrementa a cada carga com sucesso) | — |
| 6 | Meta de vendas (gauge) a partir de `metas_vendas` | Meta fixa editável em `viz_config.target` (placeholder R$ 4 mi/mês) | Não há arquivo de metas. Quando existir, vira dataset e o gauge passa a lê-lo. |
| 7 | SSE autenticado + polling | Idem; heartbeat 25 s; polling 60 s com ETag | — |
| 8 | Cache de resultados em IndexedDB na TV | `localStorage` (último dado por dashboard) | Suficiente para o volume; IndexedDB se o cache crescer. |
| 9 | Conector HTTP / Ploomes / Omie | Contrato (`connectors/base.py`) + conector `file_upload` | Fase 2 depois do spike de documentação (ADR 0008). |
| 10 | Rate limit no Caddy + slowapi | Janela deslizante em memória por processo (`core/rate_limit.py`) + lockout em banco | Com 2 workers o limite é por processo; Redis/Caddy rate-limit na Fase 2/3. |
| 11 | Sentry, Uptime Kuma, Grafana | `/metrics` Prometheus + logs JSON + Uptime Kuma (profile `monitoring`) | Sentry fica para quando houver DSN. |
