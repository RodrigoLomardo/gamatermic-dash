import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import get_sessionmaker
from tests.conftest import PASSWORD, create_user, login

API = "/api/v1"


async def test_events_recorded_with_actor_ip_request_id(client, admin, seeded):
    uid_ = await create_user("gestor@gama.com.br", ["Gestor"])
    await client.post(f"{API}/auth/login", json={"email": "gestor@gama.com.br", "password": "errada-errada-12"})
    await client.put(f"{API}/resources/dashboard/{seeded['dashboards'][0]}/grants", headers=admin,
                     json={"grants": [{"subject_type": "user", "subject_id": str(uid_), "access_level": "view"}]})
    logs = (await client.get(f"{API}/audit-logs?limit=100", headers=admin)).json()
    actions = {x["action"] for x in logs}
    assert {"auth.login.success", "auth.login.failed", "grant.replace"} <= actions
    g = next(x for x in logs if x["action"] == "grant.replace")
    assert g["actor_label"] == "admin@gama.com.br" and g["ip"] and g["request_id"]
    assert PASSWORD not in str(logs)


async def test_audit_is_append_only(client, admin):
    async with get_sessionmaker()() as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE audit_logs SET action='x'"))
        await s.rollback()
        with pytest.raises(DBAPIError):
            await s.execute(text("DELETE FROM audit_logs"))
        await s.rollback()


async def test_audit_export_neutralizes_formulas(client, admin):
    await client.post(f"{API}/auth/login", json={"email": "=cmd|' /C calc'!A0", "password": "errada-errada-12"})
    r = await client.get(f"{API}/audit-logs/export", headers=admin)
    assert r.status_code == 200 and "'=cmd" in r.text and ";=cmd" not in r.text


async def test_audit_requires_permission(client):
    await create_user("v@gama.com.br", ["Visualizador"])
    h = await login(client, "v@gama.com.br")
    assert (await client.get(f"{API}/audit-logs", headers=h)).status_code == 403
