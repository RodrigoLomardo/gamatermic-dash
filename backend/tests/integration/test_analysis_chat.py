"""Chat de analise (ADR 0012). A Groq e sempre falsa; o que se verifica e o contrato: o modelo escolhe, o backend valida e calcula."""
import json

import pytest
from sqlalchemy import text

from app.core.db import get_sessionmaker
from app.modules.analysis import chat as chat_mod
from tests.conftest import create_user, login
from tests.integration.helpers import API
from tests.integration.test_ai import KEY, _configure, fake  # noqa: F401 - fixture
from tests.integration.test_analysis import _setup


@pytest.fixture(autouse=True)
def _fresh_cache():
    chat_mod.clear_cache()


def chart(type_="bar", title="Por cliente", measures=None, dims=("cliente",), **kw):
    base = {"type": type_, "title": title, "measures": measures or [{"field": "valor", "agg": "sum", "label": "Faturamento"}], "dimensions": list(dims),
            "time_granularity": None, "period_preset": None, "period_from": None, "period_to": None, "compare": None, "filters": [],
            "sort": "desc", "limit": None}
    return base | kw


def reply(action="show_chart", message="Mostrei o faturamento por cliente.", dataset="d1", ch=None, **kw):
    base = {"action": action, "message": message, "dataset": dataset, "chart": ch, "view_filters": [], "view_from": None, "view_to": None, "suggestions": ["E por marca?"]}
    return base | kw


async def _ask(client, h, did, msg="faturamento por cliente", **kw):
    return await client.post(f"{API}/dashboards/{did}/analysis/chat", headers=h, json={"message": msg, **kw})


async def test_chart_is_computed_by_backend_and_prompt_has_no_data(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    f = fake(reply(ch=chart(period_from="2026-01-01", period_to="2026-12-31", limit=5)))
    r = await _ask(client, admin, did)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "show_chart" and out["widget"]["type"] == "bar" and out["valid"] and not out["repaired"]
    assert out["result"]["data"] == [{"cliente": "Gama", "faturamento": "1000"}, {"cliente": "Beta", "faturamento": "300.5"}, {"cliente": "ACME", "faturamento": "150"}]
    assert "Soma de Valor" in out["interpretation"] and "Por Cliente" in out["interpretation"]
    assert out["apply"]["period"] == {"mode": "absolute", "from": "2026-01-01", "to": "2026-12-31"}
    sent = json.dumps(f.bodies()[0], ensure_ascii=False)
    assert "ACME" not in sent and "Gama" not in sent and "1000" not in sent  # nenhum valor de dado vai ao modelo
    assert '"strict": true' in json.dumps(f.bodies()[0]).replace('"strict":true', '"strict": true')


async def test_filter_values_are_matched_against_real_data(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    flt = [{"field": "cliente", "op": "in", "value": None, "values": ["acme", "beta"]}, {"field": "marca", "op": "eq", "value": "parke", "values": []}]
    fake(reply(ch=chart(type_="kpi", dims=(), filters=flt)))
    out = (await _ask(client, admin, did)).json()
    assert out["action"] == "show_chart", out
    fs = {x["field"]: x["value"] for x in out["widget"]["query_config"]["filters"]}
    assert fs == {"cliente": ["ACME", "Beta"], "marca": "Parker"}
    assert out["notes"] == ["Interpretei “parke” como “Parker” (Marca)."]  # so avisa quando precisou adivinhar (acme -> ACME e so caixa)
    assert out["result"]["data"][0]["faturamento"] == "400"  # ACME(100 Parker) + Beta(300 Parker); o resto fica de fora


async def test_invalid_field_gets_one_repair_round_then_falls_back(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    bad = reply(ch=chart(dims=("nao_existe",)))
    f = fake(bad, reply(ch=chart()))
    out = (await _ask(client, admin, did)).json()
    assert out["valid"] and out["repaired"] and out["action"] == "show_chart" and len(f.bodies()) == 2
    assert "Campo inexistente" in json.dumps(f.bodies()[1], ensure_ascii=False)
    fake(bad, bad)
    out = (await _ask(client, admin, did, "outra pergunta que o modelo erra")).json()
    assert out["valid"] is False and out["action"] == "explain_unsupported" and out["widget"] is None


async def test_unsupported_and_clarify_pass_through_without_query(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    fake(reply("explain_unsupported", "Projeção não é calculada.", dataset=None, suggestions=["Faturamento por mês?"]))
    out = (await _ask(client, admin, did, "projeção até o fim do ano")).json()
    assert out["action"] == "explain_unsupported" and out["widget"] is None and out["suggestions"] == ["Faturamento por mês?"]


async def test_apply_view_returns_filters_and_period_only(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    fake(reply("apply_view", "Filtrei pela Parker em 2026.", view_filters=[{"field": "marca", "op": "eq", "value": "parker", "values": []}],
               view_from="2026-01-01", view_to="2026-12-31"))
    out = (await _ask(client, admin, did, "só da parker em 2026")).json()
    assert out["action"] == "apply_view" and out["widget"] is None
    assert out["apply"]["filters"] == [{"field": "marca", "op": "eq", "value": "Parker"}] and out["apply"]["period"]["from"] == "2026-01-01"


async def test_kpi_compares_with_same_period_last_year(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    fake(reply(ch=chart(type_="kpi", dims=(), compare="same_period_last_year", period_from="2026-01-01", period_to="2026-03-31")))
    out = (await _ask(client, admin, did)).json()
    qc = out["widget"]["query_config"]
    assert qc["compare_previous_period"] is True and qc["compare_to"] == "last_year"
    assert out["result"]["data"] == [{"faturamento": "1450.5"}] and out["result"]["previous"] is not None


async def test_pii_fields_never_reach_the_prompt(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    async with get_sessionmaker()() as s:
        await s.execute(text("UPDATE dataset_fields SET sensitivity='pii' WHERE name='marca'"))
        await s.commit()
    f = fake(reply(ch=chart(dims=("marca",))), reply(ch=chart()))
    out = (await _ask(client, admin, did)).json()
    assert '"name": "marca"' not in json.dumps(f.bodies()[0], ensure_ascii=False)
    assert out["repaired"] and out["widget"]["query_config"]["dimensions"] == ["cliente"]  # primeiro pedido (marca) recusado pela lista branca


async def test_chat_can_be_disabled_without_touching_other_ai(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    assert (await client.get(f"{API}/dashboards/{did}/analysis/chat/status", headers=admin)).json()["available"] is True
    r = await client.put(f"{API}/settings/ai", headers=admin, json={"enabled": True, "model": "openai/gpt-oss-120b", "analysis_chat": False})
    assert r.json()["analysis_chat"] is False
    assert (await client.get(f"{API}/dashboards/{did}/analysis/chat/status", headers=admin)).json()["available"] is False
    r = await _ask(client, admin, did)
    assert r.status_code == 409 and r.json()["code"] == "ai_not_configured"
    assert (await client.get(f"{API}/ai/status", headers=admin)).json()["available"] is True  # geracao de dashboards segue


async def test_requires_dataset_access_and_audits_without_prompt_text(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    fake(reply(ch=chart()))
    assert (await _ask(client, admin, did, "pergunta secreta do gestor")).status_code == 200
    logs = json.dumps((await client.get(f"{API}/audit-logs?action=ai.*", headers=admin)).json())
    assert "ai.analysis_chat" in logs and "pergunta secreta" not in logs and KEY not in logs
    await create_user("v@gama.com.br", ["Visualizador"])
    uid = next(u["id"] for u in (await client.get(f"{API}/users", headers=admin)).json() if u["email"] == "v@gama.com.br")
    await client.put(f"{API}/resources/dashboard/{did}/grants", headers=admin, json={"grants": [{"subject_type": "user", "subject_id": uid, "access_level": "view"}]})
    h = await login(client, "v@gama.com.br")
    fake(reply(ch=chart()))
    r = await _ask(client, h, did)
    assert r.status_code == 403  # Visualizador nao tem dataset:view: o chat nao e um atalho para os dados


async def test_prompt_is_compact_and_output_budget_is_small(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    f = fake(reply(ch=chart()))
    await _ask(client, admin, did)
    body = f.bodies()[0]
    sent = json.dumps(body, ensure_ascii=False)
    assert body["max_completion_tokens"] <= 1000  # a Groq reserva isto na cota por minuto
    assert len(sent) < 9000  # ~2,7 mil tokens com sistema + schema + campos; era ~11 mil caracteres
    assert "tela_atual" not in sent and "HOJE:" in body["messages"][-1]["content"]  # o que varia fica por ultimo (cache de prefixo)


async def test_identical_question_is_served_from_cache_without_calling_the_model(client, admin, fake):  # noqa: F811
    ds, did, wid = await _setup(client, admin)
    await _configure(client, admin)
    f = fake(reply(ch=chart(period_from="2026-01-01", period_to="2026-12-31")))
    first = (await _ask(client, admin, did, "Faturamento por cliente")).json()
    again = (await _ask(client, admin, did, "  faturamento   por CLIENTE ")).json()
    assert first["cached"] is False and again["cached"] is True and len(f.bodies()) == 1
    assert again["result"]["data"] == first["result"]["data"] and again["usage"]["prompt_tokens"] == 0
    # com historico (continuacao) nao usa cache: depende do contexto da conversa
    fake(reply(ch=chart()))
    h = [{"role": "user", "text": "x"}, {"role": "assistant", "text": "y"}]
    assert (await _ask(client, admin, did, "Faturamento por cliente", history=h)).json()["cached"] is False
