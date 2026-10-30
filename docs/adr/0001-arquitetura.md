# ADR 0001 — Monólito modular + worker

Monólito FastAPI organizado por domínio (`modules/<domínio>/{router,service,repository,models,schemas}`) e um worker com o mesmo código. A regra *router → service → repository → models* é imposta por `import-linter` (contrato `Routers nao tocam repositories`). Postgres é o único datastore (dados, analítico em JSONB, fila, auditoria, NOTIFY/LISTEN). Caddy serve o frontend estático e faz proxy de `/api` (mesma origem; `flush_interval -1` para SSE).
Alternativas: microserviços/serverless (custo operacional sem ganho para 1 VPS).
