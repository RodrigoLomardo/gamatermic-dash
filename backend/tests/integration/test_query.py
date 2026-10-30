import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.core.db import get_sessionmaker
from app.modules.query.compiler import FieldMeta, compile_query
from app.modules.query.spec import QuerySpec
from tests.integration.helpers import API, make_dataset, upload_and_run

CSV = ("Pedido;Cliente;Data;Valor;Marca\n"
       "1;ACME;03/01/2026;100,00;Parker\n2;ACME;15/01/2026;50,00;Danfoss\n3;Beta;10/02/2026;300,00;Parker\n"
       "4;Beta;20/02/2026;0,50;IMI\n5;Gama;01/03/2026;1.000,00;Parker\n")


async def _setup(client, admin):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV.encode())
    return ds


def body(ds, qc, type_="bar"):
    return {"dataset_id": ds["id"], "type": type_, "query_config": qc}


async def test_aggregations_are_exact(client, admin):
    ds = await _setup(client, admin)
    qc = {"measures": [{"agg": "sum", "field": "valor", "alias": "total"}, {"agg": "count", "alias": "n"}],
          "dimensions": ["cliente"], "sort": [{"by": "total", "dir": "desc"}]}
    r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc))
    assert r.status_code == 200, r.text
    assert r.json()["data"] == [{"cliente": "Gama", "total": "1000", "n": 1}, {"cliente": "Beta", "total": "300.5", "n": 2},
                                {"cliente": "ACME", "total": "150", "n": 2}]


async def test_time_granularity_and_period_and_filters(client, admin):
    ds = await _setup(client, admin)
    qc = {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "time": {"granularity": "month"},
          "period": {"mode": "absolute", "from": "2026-01-01", "to": "2026-02-28"},
          "filters": [{"field": "marca", "op": "eq", "value": "Parker"}]}
    r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "line"))
    assert r.json()["data"] == [{"time": "2026-01-01", "t": "100"}, {"time": "2026-02-01", "t": "300"}]


async def test_filter_ops(client, admin):
    ds = await _setup(client, admin)

    async def count(flt):
        qc = {"measures": [{"agg": "count", "alias": "n"}], "filters": [flt]}
        r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "kpi"))
        assert r.status_code == 200, r.text
        return r.json()["data"][0]["n"]

    assert await count({"field": "marca", "op": "in", "value": ["Parker", "IMI"]}) == 4
    assert await count({"field": "valor", "op": "gt", "value": "99,99"}) == 3
    assert await count({"field": "valor", "op": "between", "value": [0, 100]}) == 3
    assert await count({"field": "cliente", "op": "contains", "value": "ac"}) == 2
    assert await count({"field": "data", "op": "gte", "value": "2026-02-01"}) == 3
    assert await count({"field": "cliente", "op": "contains", "value": "%"}) == 0  # curinga escapado


async def test_unknown_field_is_422(client, admin):
    ds = await _setup(client, admin)
    for qc in ({"measures": [{"agg": "sum", "field": "nao_existe", "alias": "t"}]},
               {"measures": [{"agg": "count", "alias": "n"}], "dimensions": ["inexistente"]},
               {"measures": [{"agg": "count", "alias": "n"}], "filters": [{"field": "x", "op": "eq", "value": 1}]},
               {"measures": [{"agg": "sum", "field": "cliente", "alias": "t"}]}):
        r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc))
        assert r.status_code == 422, (qc, r.text)


async def test_sql_injection_attempts_are_inert(client, admin):
    ds = await _setup(client, admin)
    evil = "x'; DROP TABLE dataset_rows; --"
    for qc in ({"measures": [{"agg": "count", "alias": "n"}], "filters": [{"field": "cliente", "op": "eq", "value": evil}]},
               {"measures": [{"agg": "count", "alias": "n"}], "filters": [{"field": "cliente", "op": "contains", "value": evil}]},
               {"measures": [{"agg": "count", "alias": "n"}], "dimensions": [evil]},
               {"measures": [{"agg": "count", "alias": "n; drop table users"}]}):
        r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc))
        assert r.status_code in (200, 422), r.text
    async with get_sessionmaker()() as s:
        assert await s.scalar(text("select count(*) from dataset_rows")) == 5


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(v=st.text(max_size=60), f=st.text(max_size=30), op=st.sampled_from(["eq", "neq", "in", "contains", "gt", "between"]))
def test_compiler_never_interpolates_user_text(v, f, op):
    v = "ZQ" + v  # sentinela: nunca deve aparecer no SQL (so como parametro)
    fields = {"cliente": FieldMeta("cliente", "string", "dimension"), "valor": FieldMeta("valor", "decimal", "measure")}
    try:
        spec = QuerySpec.model_validate({"measures": [{"agg": "count", "alias": "n"}],
                                         "filters": [{"field": f, "op": op, "value": [v, v] if op in ("in", "between") else v}]})
        q, _ = compile_query(spec, uuid.uuid4(), fields, None, None)
    except Exception as e:  # nomes invalidos/valores invalidos viram erro de validacao, nunca SQL
        assert type(e).__name__ in ("ValidationError", "Unprocessable")
        return
    assert "ZQ" not in str(q.compile(compile_kwargs={"literal_binds": False}))


async def test_kpi_previous_period_comparison(client, admin):
    ds = await _setup(client, admin)
    qc = {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}], "period": {"mode": "absolute", "from": "2026-02-01", "to": "2026-02-28"},
          "compare_previous_period": True}
    r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "kpi"))
    assert r.status_code == 200  # absoluto: janela anterior de mesmo tamanho (jan) -> 50 (04/01..31/01: janela de 28 dias)
    assert r.json()["data"] == [{"t": "300.5"}] and r.json()["previous"] == [{"t": "50"}]


async def test_cache_by_version_single_flight(client, admin):
    from app.modules.query import executor

    ds = await _setup(client, admin)
    qc = {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}]}
    executor.STATS.update(hits=0, misses=0)
    for _ in range(3):
        await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "kpi"))
    assert executor.STATS == {"hits": 2, "misses": 1}
    await upload_and_run(client, admin, ds["id"], (CSV + "6;Z;02/03/2026;1,00;P\n").encode())  # nova versao invalida o cache
    r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "kpi"))
    assert r.json()["data"] == [{"t": "1451.5"}] and executor.STATS["misses"] == 2


@pytest.mark.parametrize("qc", [
    {"measures": [{"agg": "count", "alias": "n"}], "limit": 99999},
    {"measures": [{"agg": "count", "alias": "n"}], "dimensions": ["a", "b", "c", "d"]},
])
async def test_limits_validated(client, admin, qc):
    ds = await _setup(client, admin)
    assert (await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc))).status_code == 422


async def test_pii_masked_in_raw_table_for_non_managers(client, admin):
    from tests.conftest import create_user, login

    ds = await make_dataset(client, admin, slug="pii")
    fields = [dict(f) for f in ds["fields"]]
    for f in fields:
        if f["name"] == "cliente":
            f["sensitivity"] = "pii"
    await client.put(f"{API}/datasets/{ds['id']}/fields", headers=admin, json=fields)
    await upload_and_run(client, admin, ds["id"], CSV.encode())
    await create_user("ed@gama.com.br", ["Editor de Dashboards"])
    h = await login(client, "ed@gama.com.br")
    qc = {"columns": ["cliente", "valor"], "limit": 2}
    r = await client.post(f"{API}/query/preview", headers=h, json=body(ds, qc, "table"))
    assert r.status_code == 200 and all(row["cliente"] == "•••" for row in r.json()["data"])
    r = await client.post(f"{API}/query/preview", headers=admin, json=body(ds, qc, "table"))
    assert all(row["cliente"] != "•••" for row in r.json()["data"])
    prev = (await client.get(f"{API}/datasets/{ds['id']}/preview", headers=h)).json()
    assert all(row["cliente"] == "•••" for row in prev["rows"])
