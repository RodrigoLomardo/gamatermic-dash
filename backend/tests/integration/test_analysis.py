from sqlalchemy import text

from app.core.db import get_sessionmaker
from tests.conftest import create_user, login
from tests.integration.helpers import API, make_dataset, upload_and_run

CSV = ("Pedido;Cliente;Data;Valor;Marca\n"
       "1;ACME;03/01/2026;100,00;Parker\n2;ACME;15/01/2026;50,00;Danfoss\n3;Beta;10/02/2026;300,00;Parker\n"
       "4;Beta;20/02/2026;0,50;IMI\n5;Gama;01/03/2026;1.000,00;Parker\n")
ABS = {"mode": "absolute", "from": "2026-01-01", "to": "2026-12-31"}


async def _setup(client, admin):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV.encode())
    d = (await client.post(f"{API}/dashboards", headers=admin, json={"slug": "analise", "name": "Análise"})).json()
    qc = {"measures": [{"agg": "sum", "field": "valor", "alias": "total"}], "dimensions": ["cliente"], "sort": [{"by": "total", "dir": "desc"}]}
    r = await client.post(f"{API}/dashboards/{d['id']}/widgets", headers=admin, json={
        "type": "bar", "title": "Por cliente", "dataset_id": ds["id"], "x": 0, "y": 0, "w": 6, "h": 4, "query_config": qc,
        "viz_config": {"drill_path": ["cliente", "marca"]}})
    assert r.status_code == 201, r.text
    wid = r.json()["widgets"][0]["id"]
    await client.put(f"{API}/dashboards/{d['id']}/publication", headers=admin, json={"online": True})
    return ds, d["id"], wid


async def test_drill_path_validates_fields(client, admin):
    ds, did, _ = await _setup(client, admin)
    r = await client.post(f"{API}/dashboards/{did}/widgets", headers=admin, json={
        "type": "bar", "title": "x", "dataset_id": ds["id"], "x": 0, "y": 4, "w": 6, "h": 4,
        "query_config": {"measures": [{"agg": "count", "alias": "n"}], "dimensions": ["cliente"]}, "viz_config": {"drill_path": ["cliente", "nao_existe"]}})
    assert r.status_code == 422 and r.json()["code"] == "unknown_field"


async def test_data_override_regroups_and_reports_ignored_filters(client, admin):
    ds, did, wid = await _setup(client, admin)
    body = {"period": ABS, "filters": [{"field": "cliente", "op": "eq", "value": "ACME"}, {"field": "inexistente", "op": "eq", "value": "x"}],
            "overrides": {wid: {"group_by": "marca"}}}
    w = (await client.post(f"{API}/dashboards/{did}/data", headers=admin, json=body)).json()["widgets"][0]
    assert w["error"] is None and w["ignored_filters"] == ["inexistente"]
    assert w["data"] == [{"marca": "Parker", "total": "100"}, {"marca": "Danfoss", "total": "50"}]
    bad = (await client.post(f"{API}/dashboards/{did}/data", headers=admin, json={"overrides": {wid: {"group_by": "zzz"}}})).json()["widgets"][0]
    assert bad["error"]["code"] == "unknown_field"  # erro isolado no widget


async def test_analysis_query_with_filter_in_and_neq(client, admin):
    ds, did, wid = await _setup(client, admin)
    r = await client.post(f"{API}/dashboards/{did}/analysis/query", headers=admin, json={
        "widget_id": wid, "period": ABS, "filters": [{"field": "cliente", "op": "in", "value": ["ACME", "Beta"]}, {"field": "marca", "op": "neq", "value": "IMI"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == [{"cliente": "Beta", "total": "300"}, {"cliente": "ACME", "total": "150"}]
    miss = await client.post(f"{API}/dashboards/{did}/analysis/query", headers=admin, json={"widget_id": "00000000-0000-0000-0000-000000000000"})
    assert miss.status_code == 404


async def test_values_and_search(client, admin):
    ds, did, _ = await _setup(client, admin)
    r = await client.get(f"{API}/dashboards/{did}/analysis/values", headers=admin, params={"dataset_id": ds["id"], "field": "marca"})
    assert [(v["value"], v["count"]) for v in r.json()["values"]] == [("Parker", 3), ("Danfoss", 1), ("IMI", 1)]
    r = await client.get(f"{API}/dashboards/{did}/analysis/values", headers=admin, params={"dataset_id": ds["id"], "field": "cliente", "q": "ac"})
    assert [v["value"] for v in r.json()["values"]] == ["ACME"]
    assert (await client.get(f"{API}/dashboards/{did}/analysis/values", headers=admin, params={"dataset_id": ds["id"], "field": "nope"})).status_code == 422
    hits = (await client.get(f"{API}/dashboards/{did}/analysis/search", headers=admin, params={"q": "park"})).json()["hits"]
    assert [(h["kind"], h["field"], h["value"]) for h in hits] == [("value", "marca", "Parker")]
    kinds = {h["kind"] for h in (await client.get(f"{API}/dashboards/{did}/analysis/search", headers=admin, params={"q": "client"})).json()["hits"]}
    assert kinds == {"field"}


async def test_records_paginate_and_total_matches_filters(client, admin):
    ds, did, wid = await _setup(client, admin)
    body = {"widget_id": wid, "period": ABS, "filters": [{"field": "marca", "op": "eq", "value": "Parker"}], "columns": ["pedido", "cliente", "valor"],
            "sort": {"by": "valor", "dir": "desc"}, "limit": 2}
    p1 = (await client.post(f"{API}/dashboards/{did}/analysis/records", headers=admin, json=body)).json()
    assert p1["total"] == 3 and p1["has_more"] and [r["pedido"] for r in p1["rows"]] == [5, 3]
    p2 = (await client.post(f"{API}/dashboards/{did}/analysis/records", headers=admin, json={**body, "offset": 2})).json()
    assert [r["pedido"] for r in p2["rows"]] == [1] and not p2["has_more"]
    bad = await client.post(f"{API}/dashboards/{did}/analysis/records", headers=admin, json={**body, "columns": ["pedido", "x"]})
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_field"
    bad = await client.post(f"{API}/dashboards/{did}/analysis/records", headers=admin, json={**body, "sort": {"by": "marca", "dir": "asc"}})
    assert bad.status_code == 422


async def _make_pii(field="marca"):
    async with get_sessionmaker()() as s:
        await s.execute(text("UPDATE dataset_fields SET sensitivity='pii' WHERE name=:n"), {"n": field})
        await s.commit()


async def test_pii_masked_in_records_blocked_in_filters_and_values(client, admin):
    ds, did, wid = await _setup(client, admin)
    await _make_pii("marca")
    await create_user("editor@gama.com.br", ["Editor de Dashboards"])
    h = await login(client, "editor@gama.com.br")  # tem dataset:view/query mas nao dataset:manage
    rec = (await client.post(f"{API}/dashboards/{did}/analysis/records", headers=h, json={"widget_id": wid, "period": ABS, "columns": ["cliente", "marca"]})).json()
    assert {r["marca"] for r in rec["rows"]} == {"•••"}
    adm = (await client.post(f"{API}/dashboards/{did}/analysis/records", headers=admin, json={"widget_id": wid, "period": ABS, "columns": ["marca"]})).json()
    assert "Parker" in {r["marca"] for r in adm["rows"]}
    flt = {"widget_id": wid, "filters": [{"field": "marca", "op": "eq", "value": "Parker"}]}
    r = await client.post(f"{API}/dashboards/{did}/analysis/query", headers=h, json=flt)
    assert r.json()["error"]["code"] == "pii_filter"
    r = await client.get(f"{API}/dashboards/{did}/analysis/values", headers=h, params={"dataset_id": ds["id"], "field": "marca"})
    assert r.status_code == 422 and r.json()["code"] == "pii_filter"
    names = [f["name"] for f in (await client.get(f"{API}/dashboards/{did}/analysis/fields", headers=h)).json()["datasets"][0]["fields"]]
    assert "marca" not in names and "cliente" in names
    hits = (await client.get(f"{API}/dashboards/{did}/analysis/search", headers=h, params={"q": "park"})).json()["hits"]
    assert hits == []


async def test_export_requires_permission_audits_and_neutralizes(client, admin):
    ds, did, wid = await _setup(client, admin)
    body = {"widget_id": wid, "period": ABS, "columns": ["pedido", "cliente", "valor"], "sort": {"by": "pedido", "dir": "asc"}}
    r = await client.post(f"{API}/dashboards/{did}/analysis/export", headers=admin, json=body)
    assert r.status_code == 200 and r.headers["x-row-count"] == "5"
    lines = r.text.lstrip("﻿").strip().split("\r\n")
    assert lines[0] == "Pedido;Cliente;Valor" and lines[1] == "1;ACME;100"
    await create_user("gestor@gama.com.br", ["Gestor"])
    gid = (await client.get(f"{API}/users", headers=admin)).json()
    uid = next(u["id"] for u in (gid if isinstance(gid, list) else gid["items"]) if u["email"] == "gestor@gama.com.br")
    await client.put(f"{API}/resources/dashboard/{did}/grants", headers=admin, json={"grants": [{"subject_type": "user", "subject_id": uid, "access_level": "view"}]})
    h = await login(client, "gestor@gama.com.br")
    assert (await client.post(f"{API}/dashboards/{did}/analysis/export", headers=h, json=body)).status_code == 403
    assert (await client.post(f"{API}/dashboards/{did}/analysis/query", headers=h, json={"widget_id": wid})).status_code == 200
    actions = [x["action"] for x in (await client.get(f"{API}/audit-logs?action=analysis.*&limit=20", headers=admin)).json()]
    assert actions == ["analysis.export"]


async def test_saved_views_are_personal(client, admin):
    ds, did, wid = await _setup(client, admin)
    state = {"period": {"mode": "relative", "preset": "this_year"}, "filters": [{"field": "cliente", "op": "eq", "value": "ACME", "src": "drill"}], "focus_widget_id": wid}
    r = await client.post(f"{API}/dashboards/{did}/analysis/views", headers=admin, json={"name": "ACME 2026", "state": state})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert (await client.post(f"{API}/dashboards/{did}/analysis/views", headers=admin, json={"name": "ACME 2026", "state": state})).status_code == 409
    assert (await client.post(f"{API}/dashboards/{did}/analysis/views", headers=admin, json={"name": "x", "state": {"filters": [{"field": "a b", "op": "eq"}]}})).status_code == 422
    listed = (await client.get(f"{API}/dashboards/{did}/analysis/views", headers=admin)).json()
    assert [v["name"] for v in listed] == ["ACME 2026"] and listed[0]["state"]["filters"][0]["src"] == "drill"
    await create_user("outro@gama.com.br", ["Administrador"])
    h = await login(client, "outro@gama.com.br")
    assert (await client.get(f"{API}/dashboards/{did}/analysis/views", headers=h)).json() == []
    assert (await client.delete(f"{API}/dashboards/{did}/analysis/views/{vid}", headers=h)).status_code == 404
    assert (await client.delete(f"{API}/dashboards/{did}/analysis/views/{vid}", headers=admin)).status_code == 204


async def test_views_removed_with_dashboard_and_offline_hidden(client, admin):
    ds, did, wid = await _setup(client, admin)
    await client.post(f"{API}/dashboards/{did}/analysis/views", headers=admin, json={"name": "v", "state": {}})
    assert (await client.delete(f"{API}/dashboards/{did}", headers=admin)).status_code == 204
    async with get_sessionmaker()() as s:
        assert (await s.execute(text("SELECT count(*) FROM analysis_views"))).scalar() == 0


async def test_force_period_applies_to_widgets_with_own_period(client, admin):
    ds, did, wid = await _setup(client, admin)
    own = {"measures": [{"agg": "count", "alias": "n"}], "period": {"mode": "relative", "preset": "all"}}
    r = await client.post(f"{API}/dashboards/{did}/widgets", headers=admin, json={
        "type": "kpi", "title": "Fixo", "dataset_id": ds["id"], "x": 6, "y": 0, "w": 3, "h": 3, "query_config": own, "viz_config": {}, "follows_global_period": False})
    kid = r.json()["widgets"][-1]["id"]
    jan = {"mode": "absolute", "from": "2026-01-01", "to": "2026-01-31"}

    async def n(body):
        res = (await client.post(f"{API}/dashboards/{did}/data", headers=admin, json=body)).json()["widgets"]
        return next(w for w in res if w["widget_id"] == kid)["data"][0]["n"]

    assert await n({"period": jan}) == 5  # sem force: o periodo proprio do widget vence
    assert await n({"period": jan, "force_period": True}) == 2


async def test_follows_dashboard_uses_default_period_over_own(client, admin):
    ds, did, wid = await _setup(client, admin)
    assert (await client.patch(f"{API}/dashboards/{did}", headers=admin, json={"default_period": "all"})).status_code == 200
    own = {"measures": [{"agg": "count", "alias": "n"}], "period": {"mode": "relative", "preset": "this_month"}}
    r = await client.post(f"{API}/dashboards/{did}/widgets", headers=admin, json={
        "type": "kpi", "title": "Segue", "dataset_id": ds["id"], "x": 6, "y": 0, "w": 3, "h": 3, "query_config": own, "viz_config": {}, "follows_global_period": True})
    kid = r.json()["widgets"][-1]["id"]
    res = (await client.post(f"{API}/dashboards/{did}/data", headers=admin, json={})).json()["widgets"]  # sem periodo escolhido na tela
    assert next(w for w in res if w["widget_id"] == kid)["data"][0]["n"] == 5  # segue o padrao da dashboard, nao o proprio
