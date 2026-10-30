# ADR 0002 — Armazenamento híbrido (metadados tipados + linhas em JSONB)

`datasets`/`dataset_fields`/`source_bindings` definem o contrato; as linhas ficam em `dataset_rows(data jsonb)` com `row_key`, `row_hash`, `occurred_at` e soft delete. Consultas só via **QuerySpec** compilado para SQLAlchemy Core com cast pelo tipo do campo; nomes de campo são resolvidos contra `dataset_fields` (lista branca), valores sempre como parâmetros. Decimais são armazenados como string (precisão) e convertidos com `::numeric`.

## Spike A — baseline medido (1.000.000 linhas, Apple Silicon local, Postgres 18)
`scripts/bench_spike_a.py`, 15 execuções por consulta, cache desligado, índice `(dataset_id, occurred_at)` parcial:

| consulta | p50 | p95 |
|---|---|---|
| KPI soma do mês + período anterior | 21 ms | 22 ms |
| Linha 12 meses (group by mês) | 75 ms | 230 ms |
| Top 10 clientes (ano) | 311 ms | 318 ms |
| Pizza por empresa (todo o período) | 239 ms | 249 ms |
| Tabela últimos 15 | 134 ms | 136 ms |

Com índice de expressão em `cliente`, o Top 10 cai para 138 ms. **Conclusão:** dentro da meta (<300 ms/widget; dashboard completa <1 s) para 1 M linhas; promoção a tabela tipada (Fase 3) só se p95 > 300 ms em produção. **Ressalva:** medido em máquina de desenvolvimento; repetir na VPS-alvo (2 vCPU/4 GB) antes de tratar a meta como compromisso. O volume real hoje é ~10 mil linhas.
