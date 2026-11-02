#!/usr/bin/env python3
"""POC do chat de analise (plano GAMA-FEAT-PAINEL-ANALITICO, Etapa 1).

Mede se a Groq traduz as 30 perguntas dos gestores em consultas VALIDAS e CORRETAS sobre o dataset real, usando o mesmo nucleo do
produto (chat.answer). So metadados vao ao modelo; os dados sao lidos localmente. Uso (na pasta backend):
    uv run python ../scripts/poc_chat_analise.py [--rounds 3] [--dataset vendas_ploomes] [--out ../docs/planos/POC-CHAT-ANALISE.json]
"""
import argparse
import asyncio
import json
import statistics
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.authz.policy import Principal
from app.core.db import get_sessionmaker
from app.core.errors import TooManyRequests
from app.modules.analysis import chat
from app.modules.analysis import schemas as sc
from app.modules.datasets.models import Dataset
from app.modules.settings import service as settings

# (pergunta, tipo, verificador)  S = deve virar grafico correto; U = deve recusar; P = grafico aproximado correto OU recusa honesta
V, D, T, C = "valor", "data_do_pedido", "time", "count"


def has(qc, agg, field=None):
    return any(m["agg"] == agg and (field is None or m.get("field") == field) for m in qc.get("measures") or [])


def dims(qc, *names):
    return all(n in (qc.get("dimensions") or []) for n in names)


def gran(qc, *gs):
    return (qc.get("time") or {}).get("granularity") in gs


def cnt(qc):
    return any(m["agg"] in ("count", "count_distinct") for m in qc.get("measures") or [])


def year_period(qc, y):
    p = qc.get("period") or {}
    return p.get("mode") == "absolute" and p["from"].startswith(str(y)) and p["to"][:4] in (str(y), str(y + 1))


Q = [
    ("Qual foi o faturamento total em 2025 e quanto já fechamos em 2026 até agora?", "S", lambda t, qc: has(qc, "sum", V) and (gran(qc, "year") or year_period(qc, 2025) or year_period(qc, 2026))),
    ("Qual o crescimento (ou queda) de 2026 em relação ao mesmo período de 2025?", "S", lambda t, qc: has(qc, "sum", V) and (qc.get("compare_to") == "last_year" or gran(qc, "year"))),
    ("Qual o ticket médio por pedido e como ele evoluiu mês a mês?", "S", lambda t, qc: t == "line" and has(qc, "avg", V) and gran(qc, "month")),
    ("Quantos pedidos fechamos por mês e qual a sazonalidade das vendas?", "S", lambda t, qc: cnt(qc) and gran(qc, "month")),
    ("Em que mês tivemos o melhor e o pior resultado, e por quê?", "P", lambda t, qc: has(qc, "sum", V) and gran(qc, "month")),
    ("Qual empresa do grupo mais fatura e qual o peso de cada uma no total?", "S", lambda t, qc: has(qc, "sum", V) and dims(qc, "empresa_que_ira_faturar") and t in ("pie", "bar", "table")),
    ("Alguma empresa do grupo está perdendo participação ao longo do tempo?", "P", lambda t, qc: has(qc, "sum", V) and dims(qc, "empresa_que_ira_faturar") and qc.get("time")),
    ("O ticket médio varia muito entre as empresas que faturam?", "S", lambda t, qc: has(qc, "avg", V) and dims(qc, "empresa_que_ira_faturar")),
    ("Quem são os 10 maiores clientes e quanto representam do faturamento total?", "P", lambda t, qc: has(qc, "sum", V) and dims(qc, "cliente") and (qc.get("limit") or 99) <= 10),
    ("Há risco de concentração (ex.: top 5 clientes acima de X% da receita)?", "P", lambda t, qc: has(qc, "sum", V) and dims(qc, "cliente") and (qc.get("limit") or 99) <= 10),
    ("Quais clientes compraram em 2025 e não compraram em 2026 (churn)?", "U", None),
    ("Quantos clientes novos foram conquistados em 2026 versus clientes recorrentes?", "U", None),
    ("Qual a frequência média de recompra por cliente?", "P", lambda t, qc: dims(qc, "cliente") and cnt(qc)),
    ("Quais clientes aumentaram ou reduziram mais o volume de compra entre 2025 e 2026?", "P", lambda t, qc: has(qc, "sum", V) and dims(qc, "cliente") and gran(qc, "year")),
    ("Quais segmentos de cliente geram mais receita e quais têm maior ticket médio?", "S", lambda t, qc: has(qc, "sum", V) and dims(qc, "segmento_do_cliente")),
    ("Qual segmento está crescendo mais rápido e qual está desacelerando?", "P", lambda t, qc: has(qc, "sum", V) and dims(qc, "segmento_do_cliente") and qc.get("time")),
    ("Existe algum segmento pouco explorado com potencial de expansão?", "P", lambda t, qc: dims(qc, "segmento_do_cliente")),
    ("Quais produtos mais vendem em valor e em quantidade de pedidos?", "S", lambda t, qc: dims(qc, "produtos") and (has(qc, "sum", V) or cnt(qc))),
    ("Quais produtos têm maior ticket médio e quais são mais vendidos em conjunto (cross-sell)?", "P", lambda t, qc: dims(qc, "produtos") and has(qc, "avg", V)),
    ("Algum produto está em queda de vendas em 2026?", "P", lambda t, qc: dims(qc, "produtos") and (qc.get("time") or year_period(qc, 2026))),
    ("Quais projetos representam as maiores vendas e qual a receita por tipo de projeto?", "S", lambda t, qc: dims(qc, "projeto") and has(qc, "sum", V)),
    ("Qual o ranking de vendedores (responsáveis) por valor vendido e por número de pedidos?", "S", lambda t, qc: dims(qc, "responsavel") and has(qc, "sum", V)),
    ("Quem tem o maior ticket médio e quem tem maior volume de pequenos negócios?", "P", lambda t, qc: dims(qc, "responsavel") and (has(qc, "avg", V) or cnt(qc))),
    ("Quanto das vendas vem de negócios com colaboradores (venda em equipe) versus individuais?", "P", lambda t, qc: dims(qc, "usuarios_colaboradores_do_negocio") or any(f["field"] == "usuarios_colaboradores_do_negocio" for f in qc.get("filters") or [])),
    ("Há dependência excessiva de poucos vendedores para o resultado?", "P", lambda t, qc: dims(qc, "responsavel") and has(qc, "sum", V)),
    ("Qual a distribuição das condições de pagamento (à vista, parcelado, boleto etc.)?", "S", lambda t, qc: dims(qc, "condicao_de_pagamento")),
    ("Qual o prazo médio de pagamento ponderado pelo valor e como evoluiu?", "P", lambda t, qc: has(qc, "avg", "prazo_de_pagamento_no_dias") and qc.get("time")),
    ("Quanto da receita está concentrada em prazos longos (ex.: acima de 60 dias), impactando o fluxo de caixa?", "P", lambda t, qc: has(qc, "sum", V) and (dims(qc, "prazo_de_pagamento_no_dias") or any(f["field"] == "prazo_de_pagamento_no_dias" for f in qc.get("filters") or []))),
    ("Os maiores clientes ou vendedores estão negociando prazos mais longos que a média?", "P", lambda t, qc: has(qc, "avg", "prazo_de_pagamento_no_dias") and (dims(qc, "cliente") or dims(qc, "responsavel"))),
    ("Com base no histórico, qual a projeção de faturamento até o fim de 2026 e quais ações priorizar para bater a meta?", "U", None),
]


def verdict(kind, check, out):
    """(correta, motivo). U: so recusar. S e P: so conta grafico util (recusar o que dava para mostrar e erro; em P o grafico e a parte calculavel)."""
    refused = out.action in ("explain_unsupported", "clarify")
    if kind == "U":
        return refused, "recusou" if refused else "respondeu com grafico algo que o sistema nao calcula"
    if refused:
        return False, "recusou o que era possivel mostrar"
    if out.widget is None:
        return False, f"acao {out.action} sem grafico"
    ok = bool(check(out.widget.type, out.widget.query_config))
    return ok, "ok" if ok else "consulta nao responde a pergunta"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--dataset", default="vendas_ploomes")
    ap.add_argument("--out", default="")
    ap.add_argument("--pace", type=float, default=8.0, help="segundos entre perguntas")
    ap.add_argument("--only", default="", help="indices (1-based) separados por virgula")
    a = ap.parse_args()
    only = {int(x) for x in a.only.split(",") if x}
    results = []
    async with get_sessionmaker()() as s:
        rt = await settings.ai_runtime(s)
        assert rt.available, "IA nao configurada em Configuracoes"
        ds = await s.scalar(select(Dataset).where(Dataset.slug == a.dataset))
        assert ds is not None, f"dataset {a.dataset} nao existe"
        from app.modules.analysis import repository as repo
        from app.modules.query.compiler import FieldMeta
        rows = [f for f in await repo.list_fields(s, ds.id) if f.sensitivity != "pii"]
        x = chat._Ds("d1", ds, {f.name: FieldMeta(f.name, f.data_type, f.role, f.sensitivity) for f in rows}, {f.name: f.label for f in rows})
        view = sc.AnalysisChatView()
        ctx = chat._context([x], [], view, "POC")
        p = Principal(typ="user", id=uuid.uuid4(), label="poc", perms={"dataset:view": "all", "dataset:query": "all"})
        print(f"modelo={rt.model} dataset={a.dataset} campos={len(x.fields)} rodadas={a.rounds}")
        for rnd in range(a.rounds):
            for i, (q, kind, check) in enumerate(Q, 1):
                if only and i not in only:
                    continue
                t0 = time.perf_counter()
                err = "limite de uso da Groq (429) esgotou as tentativas"
                for attempt in range(8):
                    try:
                        out = await chat.answer(s, p, rt, [x], ctx, q, [])
                        break
                    except TooManyRequests as e:
                        wait = int((e.extra or {}).get("retry_after", 20)) + 1
                        print(f"  429: aguardando {wait}s"); await asyncio.sleep(wait)
                    except Exception as e:  # noqa: BLE001
                        out = None; err = f"{type(e).__name__}: {getattr(e, 'detail', e)}"; await asyncio.sleep(3)
                else:
                    out = None
                dt = time.perf_counter() - t0
                await asyncio.sleep(a.pace)  # ritmo: a cota de tokens/min da conta Groq e baixa
                if out is None:
                    results.append({"round": rnd, "i": i, "q": q, "kind": kind, "valid": False, "correct": False, "why": f"erro: {err}", "sec": dt})
                    print(f"[{rnd}.{i:02d}] ERRO {err}")
                    continue
                ok, why = verdict(kind, check, out)
                qc = out.widget.query_config if out.widget else None
                results.append({"round": rnd, "i": i, "q": q, "kind": kind, "action": out.action, "valid": out.valid, "repaired": out.repaired, "correct": ok, "why": why,
                                "type": out.widget.type if out.widget else None, "qc": qc, "message": out.message, "notes": out.notes, "interp": out.interpretation,
                                "rows": len(out.result["data"]) if out.result and out.result.get("data") is not None else None,
                                "err": out.result["error"] if out.result and out.result.get("error") else None,
                                "sec": dt, "tok": (out.usage.prompt_tokens + out.usage.completion_tokens) if out.usage else 0})
                print(f"[{rnd}.{i:02d}] {kind} {out.action:<19} {'OK ' if ok else 'XX '} {dt:4.1f}s {why:<40} {out.widget.title if out.widget else out.message[:60]}")
    n = len(results)
    valid = sum(r["valid"] and not r.get("err") for r in results)
    correct = sum(r["correct"] for r in results)
    secs = sorted(r["sec"] for r in results)
    summ = {"model": rt.model, "n": n, "valid_pct": round(100 * valid / n, 1), "correct_pct": round(100 * correct / n, 1),
            "p50_s": round(statistics.median(secs), 1), "p95_s": round(secs[int(0.95 * (n - 1))], 1), "tokens_avg": round(statistics.mean(r.get("tok", 0) for r in results))}
    byk = {k: round(100 * sum(r["correct"] for r in results if r["kind"] == k) / max(1, sum(1 for r in results if r["kind"] == k)), 1) for k in "SUP"}
    print("\nRESUMO", json.dumps({**summ, "correct_by_kind": byk}, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": {**summ, "correct_by_kind": byk}, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")


asyncio.run(main())
