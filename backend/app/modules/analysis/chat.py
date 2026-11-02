"""Chat de analise: pergunta em linguagem natural -> acao validada -> consulta executada pelo backend (ADR 0012).

O modelo escolhe a consulta; os numeros vem SEMPRE do banco. Valores de filtro (nomes de cliente etc.) sao conferidos aqui, contra os
dados, e nunca enviados ao modelo.
"""
import hashlib
import json
import time
import uuid
from collections import OrderedDict
from datetime import date
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, can
from app.core.errors import DomainError, Forbidden, Unprocessable
from app.core.logging import get_logger
from app.modules.ai import groq_client, translate
from app.modules.ai.service import AiNotConfigured, _content, _rules
from app.modules.analysis import chat_prompt as prompt
from app.modules.analysis import repository as repo
from app.modules.analysis import schemas as sc
from app.modules.analysis import service as base
from app.modules.audit import service as audit
from app.modules.dashboards import service as dash
from app.modules.dashboards.models import Widget
from app.modules.dashboards.widget_types import validate_widget
from app.modules.datasets.models import Dataset
from app.modules.query.compiler import FieldMeta
from app.modules.query.periods import now_sp
from app.modules.settings import service as settings

log = get_logger("analysis.chat")
MAX_DATASETS = 4
MAX_OUT_TOKENS = 900  # a Groq reserva max_completion_tokens na cota por minuto: pedir 3000 para gastar ~300 bloqueia a pergunta seguinte
CACHE_TTL, CACHE_MAX = 1800.0, 400
_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()  # resposta BRUTA do modelo (nao o resultado): os numeros sao recalculados a cada vez
OP_TXT = {"eq": "=", "neq": "≠", "in": "em", "gte": "≥", "lte": "≤", "between": "entre", "contains": "contém"}
AGG_TXT = {"sum": "Soma de", "avg": "Média de", "count": "Contagem", "min": "Mínimo de", "max": "Máximo de", "count_distinct": "Distintos de"}


def clear_cache() -> None:
    _CACHE.clear()


class _Ds:
    def __init__(self, key: str, ds: Dataset, fields: dict[str, FieldMeta], labels: dict[str, str]):
        self.key, self.ds, self.fields, self.labels = key, ds, fields, labels


def _iso(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


async def _datasets(session: AsyncSession, p: Principal, d) -> list[_Ds]:
    out: list[_Ds] = []
    for ds in await base._dashboard_datasets(session, d):
        if len(out) >= MAX_DATASETS or not await can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id, "view"):
            continue
        rows = [f for f in await repo.list_fields(session, ds.id) if f.sensitivity != "pii"]  # pii nunca entra (nem na lista branca)
        out.append(_Ds(f"d{len(out) + 1}", ds, {f.name: FieldMeta(f.name, f.data_type, f.role, f.sensitivity) for f in rows}, {f.name: f.label for f in rows}))
    return out


def _context(dss: list[_Ds], widgets: list[Widget], view: sc.AnalysisChatView, dash_name: str) -> dict:
    labels = {n: lb for x in dss for n, lb in x.labels.items()}
    by_ds = {x.ds.id: x.key for x in dss}
    return {
        "hoje": now_sp().date().isoformat(), "painel": dash_name,
        "datasets": [{
            "chave": x.key, "nome": x.ds.name, "descricao": x.ds.description or "", "campo_de_tempo": x.ds.time_field,
            "regras": _rules(x.fields),
            "campos": [{"name": f.name, "label": x.labels[f.name], "type": f.data_type, "role": f.role} for f in x.fields.values()],
        } for x in dss],
        "graficos_do_painel": [{"titulo": w.title, "dataset": by_ds.get(w.dataset_id), "mostra": _content(w.query_config)} for w in widgets if w.dataset_id in by_ds][:20],
        "tela_atual": {
            "periodo": (view.period.preset if view.period and view.period.mode == "relative" else
                        f"{view.period.from_} a {view.period.to}" if view.period else None),
            "filtros": [f"{labels.get(f.field, f.field)} {OP_TXT.get(f.op, f.op)} {f.value}" for f in view.filters],
        },
    }


def _raw_filters(items: list[dict]) -> list[dict]:
    out = []
    for f in items or []:
        if not isinstance(f, dict) or not f.get("field"):
            continue
        op = f.get("op")
        vals = [v for v in (f.get("values") or []) if v not in (None, "")]
        value = vals if op in ("in", "between") else f.get("value", None)
        if op == "in" and not vals and f.get("value") not in (None, ""):
            value = [f["value"]]
        out.append({"field": f["field"], "op": op, "value": value})
    return out


async def _resolve_values(session: AsyncSession, x: _Ds, filters: list[dict], notes: list[str]) -> list[dict]:
    """Ajusta o texto citado ao valor real do cadastro (ex.: 'parker' -> 'PARKER HANNIFIN'). Dados nunca vao ao modelo."""
    out = []
    for f in filters:
        meta = x.fields.get(f["field"])
        if meta is None or meta.data_type != "string" or f["op"] not in ("eq", "neq", "in"):
            out.append(f)
            continue
        vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
        fixed = []
        for v in vals:
            hits = await repo.distinct_values(session, x.ds.id, f["field"], str(v), 5)
            exact = next((h for h, _ in hits if h.casefold() == str(v).casefold()), None)
            pick = exact or (hits[0][0] if hits else None)
            if pick is None:
                notes.append(f"Não encontrei “{v}” em {x.labels.get(f['field'], f['field'])}; o filtro foi mantido como digitado.")
                fixed.append(v)
            else:
                if not exact:
                    notes.append(f"Interpretei “{v}” como “{pick}” ({x.labels.get(f['field'], f['field'])}).")
                fixed.append(pick)
        out.append({**f, "value": fixed if isinstance(f["value"], list) else fixed[0]})
    return out


def _period(raw: dict, fr: str, to: str, preset: str) -> dict | None:
    a, b = _iso(raw.get(fr)), _iso(raw.get(to))
    if a and b and a <= b:
        return {"mode": "absolute", "from": a.isoformat(), "to": b.isoformat()}
    if raw.get(preset):
        return {"mode": "relative", "preset": raw[preset]}
    return None


async def _build_chart(session: AsyncSession, x: _Ds, raw: dict, notes: list[str]) -> dict:
    sort = raw.get("sort")
    tw = {**raw, "filters": await _resolve_values(session, x, _raw_filters(raw.get("filters") or []), notes), "period_preset": None,
          "sort_by": "time" if sort == "time" else "measure" if sort in ("asc", "desc") else None, "sort_dir": "asc" if sort in ("asc", "time") else "desc",
          "format": _format(x, raw), "horizontal": raw.get("type") == "bar"}
    w = translate.to_widget(tw, x.fields, x.labels, x.ds.time_field)  # o periodo e aplicado abaixo (aceita datas absolutas)
    qc = w["query_config"]
    period = _period(raw, "period_from", "period_to", "period_preset")
    if period and x.ds.time_field:
        qc["period"] = period
        w["follows_global_period"] = False
    if w["type"] == "kpi" and x.ds.time_field and raw.get("compare") == "same_period_last_year":
        qc["compare_to"] = "last_year"
    validate_widget(w["type"], qc, w["viz_config"], x.fields, x.ds.time_field)
    return w


def _format(x: _Ds, raw: dict) -> str:
    """Formato do valor deduzido da primeira medida (o schema nao pede ao modelo: economiza tokens)."""
    m = next(iter(raw.get("measures") or []), None) or {}
    if m.get("agg") in ("count", "count_distinct"):
        return "integer"
    meta = x.fields.get(str(m.get("field") or ""))
    return "currency" if meta is not None and meta.data_type == "decimal" else "number"


def _describe(w: dict, x: _Ds) -> list[str]:
    qc, lab = w["query_config"], x.labels
    out = []
    for m in qc.get("measures") or []:
        out.append(f"{AGG_TXT.get(m['agg'], m['agg'])} {lab.get(m.get('field') or '', m.get('field') or 'registros')}".strip() if m["agg"] != "count" else "Contagem de registros")
    if qc.get("dimensions"):
        out.append("Por " + ", ".join(lab.get(d, d) for d in qc["dimensions"]))
    if qc.get("time"):
        out.append("Por " + {"day": "dia", "week": "semana", "month": "mês", "quarter": "trimestre", "year": "ano"}[qc["time"]["granularity"]])
    for f in qc.get("filters") or []:
        if f["field"] == translate.LAST_REVISION_FIELD:
            continue
        v = f["value"]
        out.append(f"{lab.get(f['field'], f['field'])} {OP_TXT.get(f['op'], f['op'])} " + (" – ".join(map(str, v)) if f["op"] == "between" else ", ".join(map(str, v)) if isinstance(v, list) else str(v)))
    pr = qc.get("period")
    if pr:
        out.append("Período: " + (f"{_br(pr['from'])} a {_br(pr['to'])}" if pr["mode"] == "absolute" else pr["preset"]))
    if qc.get("compare_previous_period"):
        out.append("Comparado com o mesmo período do ano anterior" if qc.get("compare_to") == "last_year" else "Comparado com o período anterior")
    if qc.get("limit") and w["type"] in ("bar", "pie", "table"):
        out.append(f"Até {qc['limit']} itens")
    return out


def _br(iso: str) -> str:
    return "/".join(reversed(iso[:10].split("-")))


def _apply(w: dict | None, raw_filters: list[dict], period: dict | None) -> sc.AnalysisChatApply | None:
    flt = [f for f in (w["query_config"].get("filters") if w else raw_filters) or [] if f["field"] != translate.LAST_REVISION_FIELD]
    per = (w["query_config"].get("period") if w else period)
    if not flt and not per:
        return None
    return sc.AnalysisChatApply(period=per, filters=[sc.AnalysisChatFilter(field=f["field"], op=f["op"], value=f["value"]) for f in flt])


def _summary(w: dict | None, desc: list[str]) -> str:
    return (f"{w['title']} ({w['type']}): " if w else "") + "; ".join(desc)


async def status(session: AsyncSession) -> sc.AnalysisChatStatus:
    rt = await settings.ai_runtime(session)
    return sc.AnalysisChatStatus(available=rt.available and await settings.chat_enabled(session), model=rt.model if rt.available else None)


async def answer(session: AsyncSession, p: Principal, rt: settings.AiRuntime, dss: list[_Ds], ctx: dict, message: str, history: list[dict]) -> sc.AnalysisChatOut:
    """Nucleo do chat (sem HTTP): prompt -> Groq -> acao validada -> consulta executada. Usado pelo endpoint e pela POC."""
    messages = prompt.build_messages(ctx, message, history)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    ckey = None
    if not history:  # pergunta isolada: mesma pergunta + mesmos campos + mesma tela + mesmo dia = mesma consulta; so os numeros sao recalculados
        ckey = hashlib.sha1(json.dumps([prompt.PROMPT_VERSION, rt.model, ctx["hoje"], prompt._fields_block(ctx), ctx["tela_atual"], " ".join(message.casefold().split())], ensure_ascii=False).encode()).hexdigest()
        if (hit := _CACHE.get(ckey)) and time.monotonic() - hit[0] < CACHE_TTL:
            hit_notes: list[str] = []
            if (cached := await _finish(session, p, dss, hit[1], hit_notes)) is not None:
                _CACHE.move_to_end(ckey)
                cached.notes = hit_notes + cached.notes
                cached.cached = True
                cached.usage = sc.AnalysisChatUsage(model=rt.model)
                return cached

    async def call(msgs: list[dict]) -> dict:
        try:
            out, u = await groq_client.chat_json(rt.api_key or "", rt.model, msgs, prompt.RESPONSE_SCHEMA, name="analysis_chat", max_tokens=MAX_OUT_TOKENS)
        except groq_client.AiBadOutput:
            out, u = await groq_client.chat_json(rt.api_key or "", rt.model, msgs, prompt.RESPONSE_SCHEMA, name="analysis_chat", max_tokens=MAX_OUT_TOKENS)
        usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        return out

    first = await call(messages)
    raw: dict = first
    notes: list[str] = []
    out = await _finish(session, p, dss, raw, notes)
    repaired = False
    if out is None:  # acao inconsistente: 1 rodada de reparo com o erro da validacao
        err = notes.pop() if notes else "Consulta inválida."
        try:
            raw = await call([*messages, {"role": "assistant", "content": json.dumps(first, ensure_ascii=False)},
                              {"role": "user", "content": f"A validação recusou a consulta: {err}\nDevolva a ação corrigida (mesmo schema). Se não houver como responder com os campos disponíveis, use explain_unsupported."}])
            out = await _finish(session, p, dss, raw, notes)
            repaired = out is not None
        except DomainError as e:
            log.info("chat_repair_failed", code=e.code)
    if out is None:
        out = sc.AnalysisChatOut(action="explain_unsupported", message="Não consegui montar essa consulta com os campos disponíveis. Tente reformular ou escolha uma das sugestões.",
                                 suggestions=[str(s)[:160] for s in (raw.get("suggestions") or [])[:3]], summary="(sem resposta)", valid=False)
    out.repaired = repaired
    if ckey and out.valid:
        _CACHE[ckey] = (time.monotonic(), raw)
        while len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)
    out.notes = notes + out.notes
    out.usage = sc.AnalysisChatUsage(model=rt.model, **usage)
    return out


async def ask(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.AnalysisChatIn) -> sc.AnalysisChatOut:
    d = await base._dashboard(session, p, did)
    rt = await settings.ai_runtime(session)
    if not rt.available or not rt.api_key or not await settings.chat_enabled(session):
        raise AiNotConfigured("O chat de análise não está ativo. Peça a um administrador para ativá-lo em Configurações.")
    dss = await _datasets(session, p, d)
    if not dss:
        raise Forbidden("Sem permissão para consultar os dados deste painel.")
    widgets = await dash._widgets(session, d.id)
    out = await answer(session, p, rt, dss, _context(dss, widgets, body.view, d.name), body.message.strip(),
                       [{"role": h.role, "content": h.text} for h in body.history[-8:]])
    await audit.record(session, "ai.analysis_chat", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"model": rt.model, "action": out.action, "prompt_chars": len(body.message), "prompt_sha256": hashlib.sha256(body.message.encode()).hexdigest()[:16],
                                 **(out.usage.model_dump(exclude={"model"}) if out.usage else {})})
    await session.commit()
    return out


async def _finish(session: AsyncSession, p: Principal, dss: list[_Ds], raw: dict, notes: list[str]) -> sc.AnalysisChatOut | None:
    action = raw.get("action")
    msg = str(raw.get("message") or "")[:700]
    sugg = [str(s)[:160] for s in (raw.get("suggestions") or [])[:3]]
    if action in ("explain_unsupported", "clarify") or action not in ("show_chart", "apply_view"):
        return sc.AnalysisChatOut(action="clarify" if action == "clarify" else "explain_unsupported", message=msg or "Não consegui responder a isso.", suggestions=sugg, summary=msg[:300])
    x = next((d for d in dss if d.key == raw.get("dataset")), dss[0] if len(dss) == 1 else None)
    if action == "apply_view":
        x = x or dss[0]
        try:
            flt = await _resolve_values(session, x, _raw_filters(raw.get("view_filters") or []), notes)
            for f in flt:
                if f["field"] not in x.fields:
                    raise Unprocessable(f"Campo inexistente: '{f['field']}'.", code="unknown_field")
        except DomainError as e:
            notes.append(e.detail)
            return None
        per = _period(raw, "view_from", "view_to", "_")
        ap = _apply(None, flt, per)
        if ap is None:
            return None
        return sc.AnalysisChatOut(action="apply_view", message=msg, apply=ap, suggestions=sugg, summary=f"Aplicou à tela: {msg[:200]}")
    if x is None or not isinstance(raw.get("chart"), dict):
        notes.append("Escolha o dataset e o gráfico.")
        return None
    try:
        w = await _build_chart(session, x, raw["chart"], notes)
    except DomainError as e:
        notes.append(e.detail)
        return None
    tmp = Widget(id=uuid.uuid4(), type=w["type"], title=w["title"], dataset_id=x.ds.id, query_config=w["query_config"], viz_config=w["viz_config"], follows_global_period=False)
    result = await dash.widget_result(session, p, tmp, None, [], None)
    desc = _describe(w, x)
    return sc.AnalysisChatOut(
        action="show_chart", message=msg, interpretation=desc, suggestions=sugg, summary=_summary(w, desc), apply=_apply(w, [], None),
        widget=sc.AnalysisChatWidget(type=w["type"], title=w["title"], dataset_id=x.ds.id, query_config=w["query_config"], viz_config=w["viz_config"],
                                     follows_global_period=False, w=w["w"], h=w["h"], id=str(tmp.id)),
        result=result)
