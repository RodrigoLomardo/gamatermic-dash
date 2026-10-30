"""Spike A (desempenho): dataset sintetico de 1M linhas em JSONB e QuerySpecs tipicos.

Uso: uv run python scripts/bench_spike_a.py [--rows 1000000] [--db postgresql+asyncpg://...]
Cria o dataset 'bench_spike_a' (e remove ao final). Mede p50/p95 de cada consulta com cache desligado (versao nova a cada rodada).
"""
import argparse
import asyncio
import os
import statistics
import time
import uuid

ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=1_000_000)
ap.add_argument("--db", default=os.environ.get("GAMA_DATABASE_URL", "postgresql+asyncpg://gama@localhost:5433/gamatermic_test"))
ap.add_argument("--runs", type=int, default=15)
args = ap.parse_args()
os.environ["GAMA_DATABASE_URL"] = args.db

from sqlalchemy import text  # noqa: E402

from app.core.db import dispose_engine, get_sessionmaker  # noqa: E402
from app.modules.query import executor  # noqa: E402
from app.modules.query.spec import QuerySpec  # noqa: E402

QUERIES = {
    "kpi_soma_mes": {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "period": {"mode": "relative", "preset": "this_month"}, "compare_previous_period": True},
    "linha_12_meses": {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "time": {"granularity": "month"}, "period": {"mode": "relative", "preset": "last_12_months"}},
    "top10_clientes": {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "dimensions": ["cliente"], "sort": [{"by": "t", "dir": "desc"}], "limit": 10, "period": {"mode": "relative", "preset": "this_year"}},
    "pizza_empresa": {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "dimensions": ["empresa"], "period": {"mode": "relative", "preset": "all"}},
    "tabela_ultimos": {"columns": ["data", "cliente", "empresa", "valor"], "sort": [{"by": "data", "dir": "desc"}], "limit": 15},
}


async def main() -> None:
    sm = get_sessionmaker()
    did = uuid.uuid4()
    async with sm() as s:
        await s.execute(text("INSERT INTO datasets (id, slug, name, storage_kind, load_mode, key_fields, time_field, version, row_count, max_reject_pct, strict_mode) "
                             "VALUES (:i, :s, 'bench', 'jsonb', 'upsert', '[]', 'data', 1, 0, 20, false)"), {"i": did, "s": f"bench_{did.hex[:6]}"})
        for n, t, r in [("data", "date", "time"), ("valor", "decimal", "measure"), ("cliente", "string", "dimension"), ("empresa", "string", "dimension")]:
            await s.execute(text("INSERT INTO dataset_fields (id, dataset_id, name, label, data_type, role, nullable, is_key, is_indexed, sensitivity, parse_options, position) "
                                 "VALUES (gen_random_uuid(), :d, :n, :n, :t, :r, true, false, false, 'none', '{}', 0)"), {"d": did, "n": n, "t": t, "r": r})
        t0 = time.perf_counter()
        await s.execute(text("""
            INSERT INTO dataset_rows (dataset_id, row_key, data, row_hash, occurred_at, created_at, updated_at)
            SELECT :d, g::text,
                   jsonb_build_object('data', to_char(d, 'YYYY-MM-DD'), 'valor', round((random()*50000)::numeric, 2)::text,
                                      'cliente', 'Cliente ' || (g % 800), 'empresa', (ARRAY['GAMATERMIC','ENGEPARTS','GSU','SEMIN'])[1 + g % 4]),
                   md5(g::text), d, now(), now()
            FROM (SELECT g, (timestamptz '2025-01-01' + ((g % 660) || ' days')::interval) AS d FROM generate_series(1, :n) g) x
        """), {"d": did, "n": args.rows})
        await s.execute(text("ANALYZE dataset_rows"))
        await s.commit()
        print(f"carga sintetica: {args.rows:,} linhas em {time.perf_counter() - t0:.1f}s")

    async def bench(label: str) -> None:
        print(f"\n== {label}")
        for name, q in QUERIES.items():
            ts = []
            for _ in range(args.runs):
                executor.clear_cache()
                async with sm() as s:
                    t = time.perf_counter()
                    await executor.execute(s, did, QuerySpec.model_validate(q))
                    ts.append((time.perf_counter() - t) * 1000)
            ts.sort()
            p95 = ts[max(0, int(len(ts) * 0.95) - 1)]
            print(f"{name:18s} p50={statistics.median(ts):7.1f} ms  p95={p95:7.1f} ms")

    await bench("sem indices extras (so ix dataset_id+occurred_at)")
    async with sm() as s:
        await s.execute(text(f"CREATE INDEX IF NOT EXISTS bench_cliente ON dataset_rows ((data->>'cliente')) WHERE dataset_id = '{did}'"))
        await s.commit()
    await bench("com indice de expressao em cliente")
    async with sm() as s:
        await s.execute(text("DROP INDEX IF EXISTS bench_cliente"))
        await s.execute(text("DELETE FROM datasets WHERE id = :d"), {"d": did})
        await s.commit()
    await dispose_engine()


asyncio.run(main())
