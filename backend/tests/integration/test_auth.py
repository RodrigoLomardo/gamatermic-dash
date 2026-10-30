import httpx
import pytest

from tests.conftest import PASSWORD, create_user, login

A = "/api/v1/auth"


async def test_login_ok_and_me(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    r = await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["permissions"] == {"dashboard:view": "granted"}
    assert "gd_refresh" in r.cookies
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie and "path=/api/v1/auth" in set_cookie
    me = await client.get(f"{A}/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "ana@gama.com.br"


async def test_wrong_password_is_generic_and_unknown_user_same_response(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    a = await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": "errada-errada-1"})
    b = await client.post(f"{A}/login", json={"email": "ninguem@gama.com.br", "password": "errada-errada-1"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


async def test_lockout_after_five_failures(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    for _ in range(5):
        r = await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": "errada-errada-1"})
        assert r.status_code == 401
    r = await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": PASSWORD})  # certa, mas bloqueada
    assert r.status_code == 429 and r.json()["code"] == "account_locked"


async def test_refresh_rotation_and_reuse_detection(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": PASSWORD})
    old = client.cookies.get("gd_refresh")
    r1 = await client.post(f"{A}/refresh")
    assert r1.status_code == 200
    new = client.cookies.get("gd_refresh")
    assert new != old
    # reuso do token antigo dentro da janela de 10 s: tolerado (abas concorrentes)
    client.cookies.set("gd_refresh", old, path="/api/v1/auth")
    assert (await client.post(f"{A}/refresh")).status_code == 200
    # reuso fora da janela: revoga a familia inteira
    from datetime import timedelta

    from sqlalchemy import update

    from app.core.db import get_sessionmaker, utcnow
    from app.modules.iam.models import RefreshToken

    async with get_sessionmaker()() as s:
        await s.execute(update(RefreshToken).values(used_at=utcnow() - timedelta(minutes=5)))
        await s.commit()
    client.cookies.set("gd_refresh", old, path="/api/v1/auth")
    r2 = await client.post(f"{A}/refresh")
    assert r2.status_code == 401 and r2.json()["code"] == "reuse_detected"
    client.cookies.set("gd_refresh", new, path="/api/v1/auth")  # a familia toda foi revogada
    assert (await client.post(f"{A}/refresh")).status_code == 401


async def test_refresh_requires_csrf_header(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": PASSWORD})
    bare = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    bare.cookies.set("gd_refresh", client.cookies.get("gd_refresh"), path="/api/v1/auth")
    assert (await bare.post(f"{A}/refresh")).status_code == 403


async def test_password_policy_and_change_revokes_sessions(client):
    await create_user("ana@gama.com.br", ["Visualizador"])
    h = await login(client, "ana@gama.com.br")
    for weak in ("curta-1", "aaaaaaaaaaaaaaaa", "gamatermic2026", "ana-ana-ana-ana"):
        r = await client.post(f"{A}/change-password", headers=h, json={"current_password": PASSWORD, "new_password": weak})
        assert r.status_code == 422, weak
    ok = await client.post(f"{A}/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "Nova-Senha-Segura-5531"})
    assert ok.status_code == 204
    assert (await client.post(f"{A}/refresh")).status_code == 401  # sessoes revogadas
    await login(client, "ana@gama.com.br", "Nova-Senha-Segura-5531")


async def test_must_change_password_blocks_other_routes(client):
    await create_user("novo@gama.com.br", ["Gestor"], must_change=True)
    h = await login(client, "novo@gama.com.br")
    assert (await client.get(f"{A}/me", headers=h)).status_code == 200
    r = await client.get("/api/v1/dashboards", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "password_change_required"


@pytest.mark.parametrize("token", ["", "Bearer abc", "Bearer a.b.c"])
async def test_invalid_tokens_are_401(client, token):
    r = await client.get("/api/v1/dashboards", headers={"Authorization": token} if token else {})
    assert r.status_code == 401


async def test_expired_access_token_401(client, monkeypatch):
    from app.core.config import get_settings

    await create_user("ana@gama.com.br", ["Visualizador"])
    monkeypatch.setattr(get_settings(), "access_ttl_seconds", -10)
    h = await login(client, "ana@gama.com.br")
    assert (await client.get("/api/v1/dashboards", headers=h)).status_code == 401


async def test_logs_never_contain_secrets(client, capsys):
    await create_user("ana@gama.com.br", ["Visualizador"])
    await client.post(f"{A}/login", json={"email": "ana@gama.com.br", "password": PASSWORD})
    out = capsys.readouterr().out
    assert PASSWORD not in out
