import uuid

from fastapi.routing import APIRoute

from tests.conftest import create_user, login

API = "/api/v1"


def _has_policy(dependant) -> bool:
    for d in dependant.dependencies:
        if getattr(d.call, "__gama_policy__", False) or _has_policy(d):
            return True
    return False


def test_every_route_declares_a_security_policy():
    from app.main import API_ROUTER

    missing = [f"{sorted(r.methods)} {r.path}" for r in API_ROUTER.routes if isinstance(r, APIRoute)
               and not _has_policy(r.dependant)]
    assert not missing, f"rotas sem politica de seguranca: {missing}"


async def test_gestor_sees_only_granted_dashboards(client, admin, seeded):
    gid = await create_user("gestor@gama.com.br", ["Gestor"])
    h = await login(client, "gestor@gama.com.br")
    d1, d2 = seeded["dashboards"]
    assert (await client.get(f"{API}/dashboards", headers=h)).json() == []
    assert (await client.get(f"{API}/dashboards/{d1}", headers=h)).status_code == 403
    r = await client.put(f"{API}/resources/dashboard/{d1}/grants", headers=admin,
                         json={"grants": [{"subject_type": "user", "subject_id": str(gid), "access_level": "view"}]})
    assert r.status_code == 200
    got = (await client.get(f"{API}/dashboards", headers=h)).json()
    assert [x["id"] for x in got] == [str(d1)]
    assert (await client.get(f"{API}/dashboards/{d1}", headers=h)).status_code == 200
    assert (await client.get(f"{API}/dashboards/{d2}", headers=h)).status_code == 403
    assert (await client.post(f"{API}/dashboards/{d1}/data", headers=h, json={})).status_code == 200
    assert (await client.post(f"{API}/dashboards/{d2}/data", headers=h, json={})).status_code == 403
    # sem permissao de edicao
    assert (await client.patch(f"{API}/dashboards/{d1}", headers=h, json={"name": "x x"})).status_code == 403


async def test_sector_grant_covers_all_dashboards_in_sector(client, admin, seeded):
    gid = await create_user("gestor@gama.com.br", ["Gestor"])
    h = await login(client, "gestor@gama.com.br")
    await client.put(f"{API}/resources/sector/{seeded['sector']}/grants", headers=admin,
                     json={"grants": [{"subject_type": "user", "subject_id": str(gid), "access_level": "view"}]})
    assert len((await client.get(f"{API}/dashboards", headers=h)).json()) == 2


async def test_group_grant_and_effective_permissions(client, admin, seeded):
    uid_ = await create_user("gestor@gama.com.br", ["Visualizador"])
    g = (await client.post(f"{API}/groups", headers=admin, json={"name": "Comercial"})).json()
    await client.put(f"{API}/groups/{g['id']}/members", headers=admin, json={"ids": [str(uid_)]})
    await client.put(f"{API}/resources/sector/{seeded['sector']}/grants", headers=admin,
                     json={"grants": [{"subject_type": "group", "subject_id": g["id"], "access_level": "view"}]})
    h = await login(client, "gestor@gama.com.br")
    assert len((await client.get(f"{API}/dashboards", headers=h)).json()) == 2
    eff = (await client.get(f"{API}/users/{uid_}/effective-permissions", headers=admin)).json()
    assert eff["permissions"] == {"dashboard:view": "granted"} and eff["groups"][0]["name"] == "Comercial"


async def test_permission_change_takes_effect_quickly(client, admin, seeded):
    uid_ = await create_user("ed@gama.com.br", ["Visualizador"])
    h = await login(client, "ed@gama.com.br")
    assert (await client.get(f"{API}/audit-logs", headers=h)).status_code == 403
    roles = {r["name"]: r["id"] for r in (await client.get(f"{API}/roles", headers=admin)).json()}
    r = await client.post(f"{API}/roles", headers=admin, json={"name": "Auditor", "permissions": [{"code": "audit:view", "scope": "all"}]})
    assert r.status_code == 201
    await client.put(f"{API}/users/{uid_}/roles", headers=admin, json={"ids": [r.json()["id"], roles["Visualizador"]]})
    assert (await client.get(f"{API}/audit-logs", headers=h)).status_code == 200  # authz_version invalida o cache


async def test_anti_escalation(client, admin):
    # usuario com user:manage mas sem role:manage nao pode se dar Administrador
    r = await client.post(f"{API}/roles", headers=admin, json={"name": "RH", "permissions": [
        {"code": "user:manage", "scope": "all"}, {"code": "role:manage", "scope": "all"}]})
    assert r.status_code == 201
    uid_ = await create_user("rh@gama.com.br", [])
    await client.put(f"{API}/users/{uid_}/roles", headers=admin, json={"ids": [r.json()["id"]]})
    h = await login(client, "rh@gama.com.br")
    roles = {x["name"]: x["id"] for x in (await client.get(f"{API}/roles", headers=h)).json()}
    out = await client.put(f"{API}/users/{uid_}/roles", headers=h, json={"ids": [roles["Administrador"]]})
    assert out.status_code == 403 and out.json()["code"] == "privilege_escalation"
    bad = await client.post(f"{API}/roles", headers=h, json={"name": "Super", "permissions": [{"code": "audit:view", "scope": "all"}]})
    assert bad.status_code == 403


async def test_cannot_remove_last_admin(client, admin):
    me = (await client.get(f"{API}/auth/me", headers=admin)).json()
    roles = {x["name"]: x["id"] for x in (await client.get(f"{API}/roles", headers=admin)).json()}
    r = await client.put(f"{API}/users/{me['id']}/roles", headers=admin, json={"ids": [roles["Visualizador"]]})
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    assert (await client.delete(f"{API}/users/{me['id']}", headers=admin)).status_code == 409


async def test_system_roles_are_immutable(client, admin):
    roles = {x["name"]: x["id"] for x in (await client.get(f"{API}/roles", headers=admin)).json()}
    assert (await client.put(f"{API}/roles/{roles['Gestor']}/permissions", headers=admin, json=[])).status_code == 403
    assert (await client.delete(f"{API}/roles/{roles['Gestor']}", headers=admin)).status_code == 403


async def test_user_admin_flow_temp_password(client, admin):
    r = await client.post(f"{API}/users", headers=admin, json={"email": "novo@gama.com.br", "full_name": "Novo Usuário", "role_ids": []})
    assert r.status_code == 201 and r.json()["temp_password"] and r.json()["must_change_password"]
    dup = await client.post(f"{API}/users", headers=admin, json={"email": "NOVO@gama.com.br", "full_name": "Outro Nome"})
    assert dup.status_code == 409
    listing = (await client.get(f"{API}/users", headers=admin)).json()
    assert all(u["temp_password"] is None for u in listing)


async def test_anonymize_and_export(client, admin):
    uid_ = await create_user("sai@gama.com.br", ["Visualizador"])
    h = await login(client, "sai@gama.com.br")
    exp = (await client.get(f"{API}/me/export", headers=h)).json()
    assert exp["email"] == "sai@gama.com.br"
    r = await client.post(f"{API}/users/{uid_}/anonymize", headers=admin)
    assert r.json()["email"].endswith("@anonimizado.invalid")
    assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 401


async def test_unknown_ids_404_not_500(client, admin):
    assert (await client.get(f"{API}/dashboards/{uuid.uuid4()}", headers=admin)).status_code == 404
    assert (await client.get(f"{API}/datasets/{uuid.uuid4()}", headers=admin)).status_code == 404
