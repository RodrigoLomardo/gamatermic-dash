# Runbook — Carga travada ou com erro

1. *Dados e cargas → dataset → Histórico de cargas*: abra a carga. **Falhou**: leia o resumo (coluna ausente, % de rejeição) e baixe o CSV de erros (linha/coluna/motivo). Corrija a planilha e reenvie (reenviar o mesmo arquivo não duplica; use “Reprocessar” para repetir a mesma carga).
2. **Na fila há muito tempo**: confirme o worker (`docker compose ps worker`, `logs worker`). `GET /api/v1/health/ready` mostra `stuck_jobs`. Jobs presos há >30 min voltam à fila sozinhos; runs “Processando” há >45 min são marcadas como falha.
3. **Dado não mudou na TV**: verifique a versão do dataset (card do dataset) e o badge “fonte atrasada”. A TV usa SSE + polling de 60 s.
4. Falha no meio da carga **não altera** os dados vigentes (transação única).
