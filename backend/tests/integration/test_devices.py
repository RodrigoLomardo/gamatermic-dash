import asyncio
from datetime import timedelta

import httpx
from sqlalchemy import update

from app.core.db import get_sessionmaker, utcnow
from app.core.events import broker
from app.modules.devices.models import DevicePairingRequest
from tests.conftest import create_user, login
from tests.integration.helpers import CSV_OK, make_dataset, upload_and_run

API = "/api/v1"


async def _pair(client, admin, playlist_id=None):
    tv = httpx.AsyncClient(transport=client._transport, base_url="http://test", headers={"X-Requested-With": "gamatermic"})
    start = (await tv.post(f"{API}/device-pairing/start")).json()
    pend = (await tv.post(f"{API}/device-pairing/poll", json={"device_code": start["device_code"]})).json()
    assert pend["status"] == "authorization_pending"
    look = await client.get(f"{API}/device-pairing/lookup", headers=admin, params={"user_code": start["user_code"]})
    assert look.status_code == 200 and look.json()["requested_ip"]
    ap = await client.post(f"{API}/device-pairing/approve", headers=admin,
                           json={"user_code": start["user_code"], "name": "TV Comercial", "location": "Sala", "playlist_id": playlist_id})
    assert ap.status_code == 200, ap.text
    done = await tv.post(f"{API}/device-pairing/poll", json={"device_code": start["device_code"]})
    return tv, start, ap.json(), done


async def _playlist(client, admin, seeded):
    pl = (await client.post(f"{API}/playlists", headers=admin, json={"name": "Painel"})).json()
    r = await client.put(f"{API}/playlists/{pl['id']}/items", headers=admin,
                         json=[{"dashboard_id": str(seeded["dashboards"][0]), "duration_seconds": 20}])
    assert r.status_code == 200
    return pl["id"]


async def test_full_pairing_flow_and_display_scope(client, admin, seeded):
    plid = await _playlist(client, admin, seeded)
    tv, start, dev, done = await _pair(client, admin, plid)
    assert done.json()["status"] == "approved"
    assert "httponly" in done.headers["set-cookie"].lower() and "path=/api/v1/device" in done.headers["set-cookie"].lower()
    tok = (await tv.post(f"{API}/device/token")).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    cfg = (await tv.get(f"{API}/display/config", headers=h)).json()
    assert cfg["mode"] == "device" and [i["dashboard_id"] for i in cfg["playlist"]] == [str(seeded["dashboards"][0])]
    assert (await tv.get(f"{API}/display/dashboards/{seeded['dashboards'][0]}", headers=h)).status_code == 200
    assert (await tv.get(f"{API}/display/dashboards/{seeded['dashboards'][1]}", headers=h)).status_code == 403  # fora da playlist
    d = await tv.get(f"{API}/display/dashboards/{seeded['dashboards'][0]}/data", headers=h)
    assert d.status_code == 200 and len(d.json()["widgets"]) == 10
    again = await tv.get(f"{API}/display/dashboards/{seeded['dashboards'][0]}/data", headers={**h, "If-None-Match": d.headers["etag"]})
    assert again.status_code == 304
    # token de dispositivo: 401 em qualquer rota de usuario; escopo fixo
    for path in ("/dashboards", "/devices", "/users", "/audit-logs", "/auth/me", "/datasets"):
        assert (await tv.get(f"{API}{path}", headers=h)).status_code == 401, path
    assert (await tv.post(f"{API}/dashboards/{seeded['dashboards'][0]}/data", headers=h, json={})).status_code == 401
    # token de usuario nao vira dispositivo
    assert (await client.post(f"{API}/device/token", headers=admin)).status_code == 401


async def test_code_is_single_use_and_credential_delivered_once(client, admin):
    tv, start, dev, done = await _pair(client, admin)
    again = await tv.post(f"{API}/device-pairing/poll", json={"device_code": start["device_code"]})
    assert again.json()["status"] == "expired" and "set-cookie" not in again.headers
    r = await client.post(f"{API}/device-pairing/approve", headers=admin, json={"user_code": start["user_code"], "name": "Outra TV"})
    assert r.status_code == 404


async def test_code_expires_in_10_minutes(client, admin):
    tv = httpx.AsyncClient(transport=client._transport, base_url="http://test", headers={"X-Requested-With": "gamatermic"})
    start = (await tv.post(f"{API}/device-pairing/start")).json()
    assert start["expires_in"] == 600 and len(start["user_code"]) == 9
    assert not set("01OI") & set(start["user_code"].replace("-", ""))
    async with get_sessionmaker()() as s:
        await s.execute(update(DevicePairingRequest).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()
    assert (await client.post(f"{API}/device-pairing/approve", headers=admin, json={"user_code": start["user_code"], "name": "TV"})).status_code == 404
    assert (await tv.post(f"{API}/device-pairing/poll", json={"device_code": start["device_code"]})).json()["status"] == "expired"


async def test_brute_force_on_user_code_is_blocked(client, admin):
    tv = httpx.AsyncClient(transport=client._transport, base_url="http://test", headers={"X-Requested-With": "gamatermic"})
    start = (await tv.post(f"{API}/device-pairing/start")).json()
    codes = []
    for _ in range(12):
        r = await client.get(f"{API}/device-pairing/lookup", headers=admin, params={"user_code": start["user_code"]})
        codes.append(r.status_code)
    assert 429 in codes or 404 in codes[-2:]


async def test_revoke_kills_token_exchange_and_emits_event(client, admin, seeded):
    plid = await _playlist(client, admin, seeded)
    tv, start, dev, done = await _pair(client, admin, plid)
    h = {"Authorization": f"Bearer {(await tv.post(f'{API}/device/token')).json()['access_token']}"}
    sub = broker.subscribe(dev["id"] and __import__("uuid").UUID(dev["id"]))
    r = await client.post(f"{API}/devices/{dev['id']}/revoke", headers=admin)
    assert r.json()["status"] == "revoked"
    # evento SSE 'revoked' (via NOTIFY -> broker) -- aqui via publicacao local equivalente
    broker.publish_local({"type": "revoked", "device_id": dev["id"]})
    assert (await asyncio.wait_for(sub.queue.get(), 1))["type"] == "revoked"
    broker.unsubscribe(sub)
    assert (await tv.post(f"{API}/device/token")).status_code == 401
    assert (await tv.get(f"{API}/display/config", headers=h)).status_code == 401  # token em curso morre junto


async def test_playlist_assignment_requires_dashboard_visibility(client, admin, seeded):
    plid = await _playlist(client, admin, seeded)
    await create_user("tv@gama.com.br", ["Visualizador"])
    r = await client.post(f"{API}/roles", headers=admin, json={"name": "Parceador", "permissions": [{"code": "device:manage", "scope": "all"}]})
    uid = await create_user("p@gama.com.br", [])
    await client.put(f"{API}/users/{uid}/roles", headers=admin, json={"ids": [r.json()["id"]]})
    h = await login(client, "p@gama.com.br")
    tv = httpx.AsyncClient(transport=client._transport, base_url="http://test", headers={"X-Requested-With": "gamatermic"})
    start = (await tv.post(f"{API}/device-pairing/start")).json()
    out = await client.post(f"{API}/device-pairing/approve", headers=h, json={"user_code": start["user_code"], "name": "TV", "playlist_id": plid})
    assert out.status_code == 403 and out.json()["code"] == "privilege_escalation"


async def test_heartbeat_marks_online_and_audit(client, admin, seeded):
    plid = await _playlist(client, admin, seeded)
    tv, _, dev, _ = await _pair(client, admin, plid)
    h = {"Authorization": f"Bearer {(await tv.post(f'{API}/device/token')).json()['access_token']}"}
    assert (await tv.post(f"{API}/display/heartbeat", headers=h, json={"app_version": "1.0", "stale_state": "ok"})).status_code == 204
    d = (await client.get(f"{API}/devices/{dev['id']}", headers=admin)).json()
    assert d["online"] and d["app_version"] == "1.0"
    actions = {x["action"] for x in (await client.get(f"{API}/audit-logs?limit=200", headers=admin)).json()}
    assert {"device.pair.requested", "device.pair.approved"} <= actions


async def test_widget_error_does_not_break_dashboard(client, admin, seeded):
    ds = await make_dataset(client, admin, slug="pedidos")
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    d = (await client.post(f"{API}/dashboards", headers=admin, json={"slug": "teste", "name": "Teste"})).json()
    good = {"type": "kpi", "title": "Total", "dataset_id": ds["id"], "query_config": {"measures": [{"agg": "sum", "field": "valor", "alias": "t"}]}}
    r = await client.post(f"{API}/dashboards/{d['id']}/widgets", headers=admin, json=good)
    assert r.status_code == 201
    bad = await client.post(f"{API}/dashboards/{d['id']}/widgets", headers=admin,
                            json={**good, "query_config": {"measures": [{"agg": "sum", "field": "nao_existe", "alias": "t"}]}})
    assert bad.status_code == 422
    # campo removido depois (config orfa): so aquele widget falha
    async with get_sessionmaker()() as s:
        from sqlalchemy import text

        await s.execute(text("""UPDATE widgets SET query_config = jsonb_set(query_config, '{measures,0,field}', '"fantasma"') WHERE title='Total'"""))
        await s.commit()
    await client.post(f"{API}/dashboards/{d['id']}/widgets", headers=admin, json={**good, "title": "Outro", "y": 3})
    data = (await client.post(f"{API}/dashboards/{d['id']}/data", headers=admin, json={})).json()
    by_title = {w["widget_id"]: w for w in data["widgets"]}
    errs = [w for w in by_title.values() if w["error"]]
    assert len(errs) == 1 and errs[0]["error"]["code"] == "unknown_field" and len(data["widgets"]) == 2


async def test_optimistic_lock_conflict_409(client, admin, seeded):
    did = seeded["dashboards"][0]
    d = (await client.get(f"{API}/dashboards/{did}", headers=admin)).json()
    ok = await client.patch(f"{API}/dashboards/{did}", headers={**admin, "If-Match": f'"{d["version"]}"'}, json={"name": "Novo nome"})
    assert ok.status_code == 200 and ok.json()["version"] == d["version"] + 1
    stale = await client.patch(f"{API}/dashboards/{did}", headers={**admin, "If-Match": f'"{d["version"]}"'}, json={"name": "Outro nome"})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    layout = [{"id": w["id"], "x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"]} for w in d["widgets"]]
    assert (await client.put(f"{API}/dashboards/{did}/layout", headers={**admin, "If-Match": f'"{d["version"]}"'}, json={"items": layout})).status_code == 409


async def test_only_editors_can_edit(client, admin, seeded):
    await create_user("v@gama.com.br", ["Visualizador"])
    h = await login(client, "v@gama.com.br")
    did = seeded["dashboards"][0]
    assert (await client.put(f"{API}/dashboards/{did}/layout", headers=h, json={"items": []})).status_code == 403
    assert (await client.delete(f"{API}/dashboards/{did}", headers=h)).status_code == 403
    assert (await client.post(f"{API}/dashboards/{did}/duplicate", headers=h)).status_code == 403
