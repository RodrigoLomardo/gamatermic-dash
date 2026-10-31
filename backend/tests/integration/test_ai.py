"""Configuracoes da IA e geracao de propostas (ADR 0010). A Groq e sempre falsa (httpx.MockTransport): nada vai a rede."""
import json

import httpx
import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.modules.ai import groq_client
from app.modules.settings.models import SystemSetting
from tests.conftest import create_user, login

API = "/api/v1"
KEY = "gsk_test_0123456789abcdefWXYZ"


def W(type_, title, measures, dims=(), **kw):
    base = {"type": type_, "title": title, "rationale": "porque sim", "measures": measures, "dimensions": list(dims), "columns": [],
            "time_granularity": None, "period_preset": None, "filters": [], "sort_by": None, "sort_dir": "desc", "limit": None,
            "format": "currency", "horizontal": None, "target": None}
    return base | kw


def M(agg, field, label):
    return {"agg": agg, "field": field, "label": label}


class FakeGroq:
    """Responde em ordem as respostas enfileiradas e guarda o corpo de cada requisicao."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/models"):
            if request.headers["authorization"] != f"Bearer {KEY}":
                return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        r = self.replies.pop(0)
        if isinstance(r, httpx.Response):
            return r
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(r)}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 300}})

    def bodies(self):
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/chat/completions")]


@pytest.fixture
def fake():
    holder = {}

    def install(*replies):
        f = FakeGroq(*replies)
        groq_client.set_transport(httpx.MockTransport(f))
        holder["f"] = f
        return f

    yield install
    groq_client.set_transport(None)


async def _configure(client, admin, enabled=True, model="openai/gpt-oss-120b"):
    r = await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": enabled, "model": model, "api_key": KEY})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- configuracoes ----------------
async def test_settings_require_settings_manage(client, admin):
    await create_user("ed@gama.com.br", ["Editor de Dashboards"])
    h = await login(client, "ed@gama.com.br")
    assert (await client.get(f"{API}/settings/ai", headers=h)).status_code == 403
    assert (await client.put(f"{API}/settings/ai", headers=h, json={"enabled": False, "model": "openai/gpt-oss-20b"})).status_code == 403
    assert (await client.post(f"{API}/settings/ai/test", headers=h)).status_code == 403
    d = (await client.get(f"{API}/settings/ai", headers=admin)).json()
    assert d["enabled"] is False and d["api_key"] == {"configured": False, "last4": None}
    assert {m["id"] for m in d["models"]} == {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}


async def test_api_key_is_write_only_encrypted_and_not_audited(client, admin):
    out = await _configure(client, admin)
    assert out["api_key"] == {"configured": True, "last4": "WXYZ"}
    assert KEY not in json.dumps(out)
    async with get_sessionmaker()() as s:
        row = await s.scalar(select(SystemSetting).where(SystemSetting.key == "ai.groq_api_key"))
        assert row is not None and row.secret_ciphertext and KEY.encode() not in row.secret_ciphertext
        assert KEY not in json.dumps(row.value)
    logs = (await client.get(f"{API}/audit-logs?action=settings.*", headers=admin)).json()
    assert logs and KEY not in json.dumps(logs)
    assert logs[0]["meta"]["api_key_changed"] == "replaced"
    # omitir a chave mantem; "" remove
    keep = (await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": True, "model": "openai/gpt-oss-20b"})).json()
    assert keep["api_key"]["configured"] and keep["model"] == "openai/gpt-oss-20b"
    gone = (await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": False, "model": "openai/gpt-oss-20b", "api_key": ""})).json()
    assert gone["api_key"]["configured"] is False


async def test_settings_validation(client, admin):
    r = await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": True, "model": "openai/gpt-oss-120b"})
    assert r.status_code == 422 and r.json()["code"] == "api_key_required"
    r = await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": False, "model": "llama-qualquer", "api_key": KEY})
    assert r.status_code == 422 and r.json()["code"] == "invalid_model"
    r = await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": False, "model": "openai/gpt-oss-120b", "api_key": "curta"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_api_key"


async def test_connection_test(client, admin, fake):
    fake()
    r = (await client.post(f"{API}/settings/ai/test", headers=admin)).json()
    assert r["ok"] is False and "chave" in r["error"].lower()
    await _configure(client, admin)
    r = (await client.post(f"{API}/settings/ai/test", headers=admin)).json()
    assert r["ok"] is True and r["model_available"] is True and r["latency_ms"] is not None
    # chave recusada pela Groq: resposta 200 com ok=false (nunca 401 para o navegador)
    async with get_sessionmaker()() as s:
        from app.core.crypto import encrypt

        row = await s.get(SystemSetting, "ai.groq_api_key")
        row.secret_ciphertext = encrypt("gsk_errada_0000000000000000")
        await s.commit()
    r = await client.post(f"{API}/settings/ai/test", headers=admin)
    assert r.status_code == 200 and r.json()["ok"] is False and "recusou" in r.json()["error"]


# ---------------- geracao ----------------
async def test_generation_requires_configuration_and_permission(client, admin, seeded, fake):
    f = fake()
    ds = seeded["datasets"]["vendas"]
    st = (await client.get(f"{API}/ai/status", headers=admin)).json()
    assert st == {"available": False, "model": None}
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(ds), "prompt": "faturamento por mês"})
    assert r.status_code == 409 and r.json()["code"] == "ai_not_configured"
    await create_user("v@gama.com.br", ["Visualizador"])
    h = await login(client, "v@gama.com.br")
    assert (await client.post(f"{API}/ai/dashboard-proposals", headers=h, json={"dataset_id": str(ds), "prompt": "x y z"})).status_code == 403
    await _configure(client, admin)
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin,
                          json={"dataset_id": "00000000-0000-0000-0000-000000000000", "prompt": "faturamento"})
    assert r.status_code == 404
    assert f.bodies() == []  # nada saiu para a Groq


async def test_generates_validated_proposals_with_preview(client, admin, seeded, fake):
    await _configure(client, admin)
    ds = seeded["datasets"]["vendas"]
    f = fake({"explanation": "Visão de faturamento.", "widgets": [
        W("kpi", "Faturamento", [M("sum", "valor", "Faturamento")]),
        W("line", "Faturamento por mês", [M("sum", "valor", "Total")], time_granularity="month", period_preset="last_12_months"),
        W("bar", "Top clientes", [M("sum", "valor", "Total")], ["Cliente"], sort_by="measure", limit=99, horizontal=True),
        W("table", "Últimos pedidos", [], columns=["data_pedido", "cliente", "valor"]),
    ]})
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(ds), "prompt": "faturamento por mês e top clientes"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [p["type"] for p in out["proposals"]] == ["kpi", "line", "bar", "table"] and out["discarded"] == []
    kpi, line, bar, table = out["proposals"]
    assert kpi["query_config"]["compare_previous_period"] is True
    assert line["query_config"]["period"]["preset"] == "last_12_months" and line["follows_global_period"] is False
    assert bar["query_config"]["dimensions"] == ["cliente"]  # rotulo resolvido para o nome
    assert bar["query_config"]["limit"] == 15 and bar["viz_config"]["horizontal"] is True
    assert table["query_config"]["columns"] == ["data_pedido", "cliente", "valor"]
    assert all(p["preview"] and p["preview"]["error"] is None for p in out["proposals"])
    assert out["usage"]["prompt_tokens"] == 900
    body = f.bodies()[0]
    assert body["response_format"]["json_schema"]["strict"] is True and body["model"] == "openai/gpt-oss-120b"
    # aceitar = endpoints existentes: as propostas passam na validacao do editor
    d = (await client.post(f"{API}/dashboards", headers=admin, json={"slug": "ia-teste", "name": "IA teste"})).json()
    assert d["status"] == "offline"
    for p in out["proposals"][:2]:
        w = {k: p[k] for k in ("type", "title", "dataset_id", "query_config", "viz_config", "follows_global_period", "w", "h")}
        assert (await client.post(f"{API}/dashboards/{d['id']}/widgets", headers=admin, json=w)).status_code == 201
    logs = (await client.get(f"{API}/audit-logs?action=ai.*", headers=admin)).json()
    assert logs[0]["meta"]["proposals"] == 4 and "faturamento" not in json.dumps(logs)  # texto do pedido nao e gravado


async def test_pii_never_sent_nor_accepted_and_last_revision_enforced(client, admin, seeded, fake):
    await _configure(client, admin)
    ds = seeded["datasets"]["propostas_abertas"]
    bad = W("bar", "Por contato", [M("sum", "valor", "Total")], ["contato"])
    f = fake({"explanation": "", "widgets": [W("kpi", "Pipeline", [M("sum", "valor", "Pipeline")]), bad]},
             {"explanation": "", "widgets": [bad]})  # reparo insiste no campo pii
    out = (await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(ds), "prompt": "pipeline por contato"})).json()
    sent = json.dumps(f.bodies()[0]["messages"], ensure_ascii=False)
    assert '"contato"' not in sent and "Contato" not in sent
    assert [p["title"] for p in out["proposals"]] == ["Pipeline"]
    assert len(out["discarded"]) == 1 and "contato" in out["discarded"][0]["reason"]
    assert {"field": "ultima_revisao", "op": "eq", "value": True} in out["proposals"][0]["query_config"]["filters"]
    assert len(f.bodies()) == 2  # houve 1 rodada de reparo


async def test_repair_round_recovers_invalid_widget(client, admin, seeded, fake):
    await _configure(client, admin)
    ds = seeded["datasets"]["vendas"]
    f = fake({"explanation": "", "widgets": [W("bar", "Por segmento", [M("sum", "segmento", "Total")], ["segmento"])]},
             {"explanation": "", "widgets": [W("bar", "Por segmento", [M("sum", "valor", "Total")], ["segmento"])]})
    out = (await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(ds), "prompt": "por segmento"})).json()
    assert [p["title"] for p in out["proposals"]] == ["Por segmento"] and out["discarded"] == []
    assert "recusados" in f.bodies()[1]["messages"][-1]["content"]


@pytest.mark.parametrize("resp,status,code", [
    (httpx.Response(401, json={}), 502, "ai_invalid_key"),
    (httpx.Response(429, headers={"retry-after": "7"}, json={}), 429, "ai_rate_limited"),
    (httpx.Response(500, json={}), 502, "ai_unavailable"),
])
async def test_upstream_errors_are_mapped(client, admin, seeded, fake, resp, status, code):
    await _configure(client, admin)
    fake(resp)
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(seeded["datasets"]["vendas"]), "prompt": "faturamento"})
    assert r.status_code == status and r.json()["code"] == code
    if status == 429:
        assert r.headers["retry-after"] == "7"
    assert KEY not in r.text


async def test_timeout_is_mapped(client, admin, seeded):
    await _configure(client, admin)

    def boom(request):
        raise httpx.ReadTimeout("lento", request=request)

    groq_client.set_transport(httpx.MockTransport(boom))
    try:
        r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json={"dataset_id": str(seeded["datasets"]["vendas"]), "prompt": "faturamento"})
    finally:
        groq_client.set_transport(None)
    assert r.status_code == 504 and r.json()["code"] == "ai_timeout"


async def test_editor_can_generate(client, admin, seeded, fake):
    await _configure(client, admin)
    await create_user("ed@gama.com.br", ["Editor de Dashboards"])
    h = await login(client, "ed@gama.com.br")
    assert (await client.get(f"{API}/ai/status", headers=h)).json()["available"] is True
    fake({"explanation": "", "widgets": [W("kpi", "Pedidos", [M("count", None, "Pedidos")], format="integer")]})
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=h, json={"dataset_id": str(seeded["datasets"]["vendas"]), "prompt": "quantos pedidos"})
    assert r.status_code == 200 and r.json()["proposals"][0]["query_config"]["measures"] == [{"agg": "count", "alias": "pedidos"}]


async def test_charts_for_existing_dashboard_skip_repeats_and_require_edit(client, admin, seeded, fake):
    await _configure(client, admin)
    ds, did = seeded["datasets"]["vendas"], seeded["dashboards"][0]  # "Vendas - Visão Geral" ja tem KPI de soma de valor
    f = fake({"explanation": "", "widgets": [
        W("kpi", "Faturamento", [M("sum", "valor", "Total")]),  # igual ao KPI do painel
        W("bar", "Por projeto", [M("sum", "valor", "Total")], ["projeto"], sort_by="measure"),
    ]})
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin,
                          json={"dataset_id": str(ds), "dashboard_id": str(did), "prompt": "mais gráficos", "default_period": "this_month"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [p["title"] for p in out["proposals"]] == ["Por projeto"]
    assert out["discarded"] == [{"title": "Faturamento", "reason": "Já existe um gráfico igual no painel."}]
    sent = f.bodies()[0]["messages"][1]["content"]
    assert "graficos_ja_no_painel" in sent and "Faturamento no mês" in sent
    # quem cria dashboards mas nao edita ESTE painel nao gera graficos para ele (e nada sai para a Groq)
    from app.modules.iam.models import Permission, Role, RolePermission

    async with get_sessionmaker()() as s:
        role = Role(name="Criador sem edição", is_system=False)
        s.add(role)
        await s.flush()
        for code in ("dashboard:view", "dashboard:create", "dataset:query", "dataset:view"):
            pid = await s.scalar(select(Permission.id).where(Permission.code == code))
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="all"))
        await s.commit()
    await create_user("criador@gama.com.br", ["Criador sem edição"])
    h = await login(client, "criador@gama.com.br")
    n = len(f.bodies())
    body = {"dataset_id": str(ds), "dashboard_id": str(did), "prompt": "mais gráficos"}
    assert (await client.post(f"{API}/ai/dashboard-proposals", headers=h, json=body)).status_code == 403
    r = await client.post(f"{API}/ai/dashboard-proposals", headers=admin, json=body | {"dashboard_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404 and len(f.bodies()) == n
