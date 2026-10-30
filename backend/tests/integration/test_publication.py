from tests.conftest import create_user, login
from tests.integration.test_devices import _pair, _playlist

API = "/api/v1"


async def test_new_and_duplicated_dashboards_start_offline(client, admin, seeded):
    d = (await client.post(f"{API}/dashboards", headers=admin, json={"slug": "novo", "name": "Novo painel"})).json()
    assert d["status"] == "offline"
    dup = (await client.post(f"{API}/dashboards/{seeded['dashboards'][0]}/duplicate", headers=admin)).json()
    assert dup["status"] == "offline"


async def test_offline_hidden_from_viewers_but_visible_to_editors(client, admin, seeded):
    did = seeded["dashboards"][0]
    gid = await create_user("gestor@gama.com.br", ["Gestor"])
    await client.put(f"{API}/resources/dashboard/{did}/grants", headers=admin,
                     json={"grants": [{"subject_type": "user", "subject_id": str(gid), "access_level": "view"}]})
    h = await login(client, "gestor@gama.com.br")
    assert len((await client.get(f"{API}/dashboards", headers=h)).json()) == 1

    r = await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": False})
    assert r.status_code == 200 and r.json()["status"] == "offline"
    assert (await client.get(f"{API}/dashboards", headers=h)).json() == []
    g = await client.get(f"{API}/dashboards/{did}", headers=h)
    assert g.status_code == 403 and g.json()["code"] == "dashboard_offline"
    assert (await client.post(f"{API}/dashboards/{did}/data", headers=h, json={})).status_code == 403
    # quem edita continua vendo e pode ate pre-visualizar
    assert any(x["id"] == str(did) and x["status"] == "offline" for x in (await client.get(f"{API}/dashboards", headers=admin)).json())
    assert (await client.get(f"{API}/display/dashboards/{did}", headers=admin)).status_code == 200

    await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": True})
    assert len((await client.get(f"{API}/dashboards", headers=h)).json()) == 1
    assert (await client.get(f"{API}/dashboards/{did}", headers=h)).status_code == 200


async def test_only_editors_can_toggle_and_audit_is_recorded(client, admin, seeded):
    did = seeded["dashboards"][0]
    await create_user("v@gama.com.br", ["Visualizador"])
    h = await login(client, "v@gama.com.br")
    assert (await client.put(f"{API}/dashboards/{did}/publication", headers=h, json={"online": False})).status_code == 403
    await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": False})
    await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": True})
    actions = [x["action"] for x in (await client.get(f"{API}/audit-logs?action=dashboard.*&limit=50", headers=admin)).json()]
    assert "dashboard.unpublished" in actions and "dashboard.published" in actions


async def test_tv_skips_offline_dashboard(client, admin, seeded):
    plid = await _playlist(client, admin, seeded)
    did = seeded["dashboards"][0]
    tv, _, _, _ = await _pair(client, admin, plid)
    h = {"Authorization": f"Bearer {(await tv.post(f'{API}/device/token')).json()['access_token']}"}
    assert len((await tv.get(f"{API}/display/config", headers=h)).json()["playlist"]) == 1
    await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": False})
    assert (await tv.get(f"{API}/display/config", headers=h)).json()["playlist"] == []
    assert (await tv.get(f"{API}/display/dashboards/{did}/data", headers=h)).status_code == 403
    await client.put(f"{API}/dashboards/{did}/publication", headers=admin, json={"online": True})
    assert (await tv.get(f"{API}/display/dashboards/{did}/data", headers=h)).status_code == 200
