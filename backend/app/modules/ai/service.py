"""Agente de sugestao de dashboards: monta o prompt so com metadados, chama a Groq, traduz, valida e pre-visualiza.

Propostas sao efemeras (ADR 0010): nada e gravado alem da auditoria. Aceitar = endpoints de dashboard existentes.
"""
import hashlib
import json
import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, require_can
from app.core.errors import DomainError, NotFound, Unprocessable
from app.core.logging import get_logger
from app.modules.ai import groq_client, prompt, translate
from app.modules.ai import schemas as sc
from app.modules.audit import service as audit
from app.modules.dashboards.models import Widget
from app.modules.dashboards.service import get_dash, widget_result
from app.modules.dashboards.widget_types import COMPACT_MIN, full_min, validate_widget
from app.modules.datasets.models import Dataset, DatasetField
from app.modules.query.compiler import FieldMeta
from app.modules.settings import service as settings

log = get_logger("ai")


class AiNotConfigured(DomainError):
    status = 409
    code = "ai_not_configured"


async def status(session: AsyncSession) -> sc.AiStatusOut:
    rt = await settings.ai_runtime(session)
    return sc.AiStatusOut(available=rt.available, model=rt.model if rt.available else None)


async def _context(session: AsyncSession, ds: Dataset) -> tuple[dict[str, FieldMeta], dict[str, str], list[prompt.FieldInfo]]:
    """Campos visiveis a IA: tudo menos pii (nem no prompt, nem na lista branca da validacao)."""
    rows = (await session.scalars(select(DatasetField).where(DatasetField.dataset_id == ds.id).order_by(DatasetField.position))).all()
    safe = [f for f in rows if f.sensitivity != "pii"]
    fields = {f.name: FieldMeta(f.name, f.data_type, f.role, f.sensitivity) for f in safe}
    labels = {f.name: f.label for f in safe}
    infos = [prompt.FieldInfo(f.name, f.label, f.data_type, f.role) for f in safe]
    return fields, labels, infos


def _rules(fields: dict[str, FieldMeta]) -> list[str]:
    out = []
    if translate.LAST_REVISION_FIELD in fields:
        out.append("Propostas têm revisões: o sistema já filtra ultima_revisao = true em todos os widgets; não repita esse filtro.")
    if "valor" in fields:
        out.append("'valor' é dinheiro em R$: use format currency.")
    return out


def _check(cand: dict, ds: Dataset, fields: dict[str, FieldMeta], labels: dict[str, str]) -> dict:
    w = translate.to_widget(cand, fields, labels, ds.time_field)
    validate_widget(w["type"], w["query_config"], w["viz_config"], fields, ds.time_field)
    return w


# familias: dois graficos da mesma familia com o mesmo conteudo mostram a mesma informacao
# (pizza e barras por categoria sao o mesmo recorte; KPI e medidor da mesma medida, idem)
_FAMILY = {"kpi": "valor", "gauge": "valor", "line": "tendencia", "bar": "recorte", "pie": "recorte"}


def _sig(wtype: str, qc: dict) -> str:
    """Assinatura pelo CONTEUDO: o que se mede, por qual recorte e filtro. Ignora titulo, alias, periodo, ordem e limite."""
    family = "linhas" if wtype == "table" and qc.get("columns") else ("recorte" if wtype == "table" else _FAMILY.get(wtype, wtype))
    core = {
        "f": family,
        "m": sorted((m.get("agg", ""), m.get("field") or "") for m in qc.get("measures") or []),
        "d": list(qc.get("dimensions") or []),
        "c": sorted(qc.get("columns") or []),
        "t": (qc.get("time") or {}).get("granularity") if family == "tendencia" else None,
        "x": sorted(json.dumps(f, sort_keys=True, ensure_ascii=False) for f in qc.get("filters") or []),
    }
    return json.dumps(core, sort_keys=True, ensure_ascii=False)


_AGG = {"sum": "soma", "avg": "média", "count": "contagem", "min": "mínimo", "max": "máximo", "count_distinct": "distintos"}


def _content(qc: dict) -> str:
    """Resumo do que o grafico mostra, para a IA nao repetir informacao com outro titulo."""
    ms = ", ".join(f"{_AGG.get(m.get('agg', ''), m.get('agg'))} de {m.get('field') or 'linhas'}" for m in qc.get("measures") or [])
    out = ms or ("colunas " + ", ".join(qc.get("columns") or []))
    if qc.get("dimensions"):
        out += " por " + ", ".join(qc["dimensions"])
    if qc.get("time"):
        out += f" ao longo do tempo ({(qc['time'] or {}).get('granularity', 'month')})"
    if qc.get("filters"):
        out += " com filtro " + ", ".join(f"{f.get('field')} {f.get('op')} {f.get('value')}" for f in qc["filters"])
    return out


async def _existing(session: AsyncSession, p: Principal, dashboard_id: uuid.UUID, dataset_id: uuid.UUID) -> tuple[list[Widget], dict[str, str]]:
    """Graficos ja no painel (layout para o prompt) e assinatura de conteudo -> titulo (para descartar repetidos)."""
    d = await get_dash(session, dashboard_id)
    await require_can(session, p, "dashboard:edit", "dashboard", d.id, d.sector_id, "edit")
    ws = list((await session.scalars(select(Widget).where(Widget.dashboard_id == d.id).order_by(Widget.y, Widget.x))).all())
    seen: dict[str, str] = {}
    for w in ws:  # se varios mostram o mesmo, cita o primeiro (de cima para baixo)
        if w.dataset_id == dataset_id:
            seen.setdefault(_sig(w.type, w.query_config), w.title)
    return ws, seen


def _layout(ws: list[Widget]) -> list[dict]:
    # ref curta em vez do UUID: menos tokens e o modelo nao inventa ids
    return [{"ref": f"w{i + 1}", "titulo": w.title, "tipo": w.type, "mostra": _content(w.query_config),
             "x": w.x, "y": w.y, "w": w.w, "h": w.h} for i, w in enumerate(ws)]


def _pick(v: object, default: int) -> int:
    i = translate._int(v)
    return default if i is None else i


def _layout_changes(raw: list, ws: list[Widget]) -> list[sc.LayoutChange]:
    """Saneia as mudancas sugeridas: ref existente, dentro da grade, nunca abaixo do minimo absoluto, sem no-op."""
    by_ref = {f"w{i + 1}": w for i, w in enumerate(ws)}
    out: dict[uuid.UUID, sc.LayoutChange] = {}
    for c in raw[:12]:
        if not isinstance(c, dict) or (w := by_ref.get(str(c.get("ref")))) is None:
            continue
        nw = min(max(_pick(c.get("w"), w.w), COMPACT_MIN[0]), translate.GRID_COLS)
        nh = min(max(_pick(c.get("h"), w.h), COMPACT_MIN[1]), translate.MAX_H)
        nx = min(max(_pick(c.get("x"), w.x), 0), translate.GRID_COLS - nw)
        ny = min(max(_pick(c.get("y"), w.y), 0), translate.MAX_Y)
        if (nx, ny, nw, nh) == (w.x, w.y, w.w, w.h):
            continue
        mw, mh = full_min(w.type)
        out[w.id] = sc.LayoutChange(widget_id=w.id, title=w.title, type=w.type, before=sc.Box(x=w.x, y=w.y, w=w.w, h=w.h),
                                    after=sc.Box(x=nx, y=ny, w=nw, h=nh), reason=str(c.get("reason") or "")[:200],
                                    compact=nw < mw or nh < mh)
    return list(out.values())


def _split(cands: list[dict], ds: Dataset, fields: dict[str, FieldMeta], labels: dict[str, str]) -> tuple[list[dict], list[tuple[str, str]]]:
    ok, bad = [], []
    for c in cands:
        title = str(c.get("title") or "sem título")[:160]
        try:
            ok.append(_check(c, ds, fields, labels))
        except DomainError as e:
            bad.append((title, e.detail))
        except Exception:  # noqa: BLE001 - saida do modelo nunca derruba a geracao
            bad.append((title, "Formato inesperado."))
    return ok, bad


async def generate(session: AsyncSession, request: Request, p: Principal, body: sc.ProposalsIn) -> sc.ProposalsOut:
    ds = await session.get(Dataset, body.dataset_id)
    if ds is None:
        raise NotFound("Dataset não encontrado.")
    # autoriza ANTES de qualquer chamada externa
    await require_can(session, p, "dataset:query", "dataset", ds.id, ds.sector_id, "view")
    rt = await settings.ai_runtime(session)
    if not rt.available or not rt.api_key:
        raise AiNotConfigured("A IA não está configurada. Peça a um administrador para ativá-la em Configurações.")
    api_key: str = rt.api_key
    current, seen = await _existing(session, p, body.dashboard_id, ds.id) if body.dashboard_id else ([], {})
    fields, labels, infos = await _context(session, ds)
    if not fields:
        raise Unprocessable("Este dataset não tem campos que a IA possa usar.", code="ai_no_fields")

    messages = prompt.build_messages(ds.name, ds.description, ds.time_field, infos, body.prompt.strip(), body.max_proposals, _rules(fields), _layout(current))
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    async def call(msgs: list[dict]) -> dict:
        try:
            out, u = await groq_client.chat_json(api_key, rt.model, msgs, prompt.RESPONSE_SCHEMA, name="dashboard_proposals")
        except groq_client.AiBadOutput:
            out, u = await groq_client.chat_json(api_key, rt.model, msgs, prompt.RESPONSE_SCHEMA, name="dashboard_proposals")
        usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        return out

    first = await call(messages)
    cands = [c for c in (first.get("widgets") or []) if isinstance(c, dict)][: body.max_proposals]
    ok, bad = _split(cands, ds, fields, labels)
    if bad:
        # 1 rodada de reparo com os erros da validacao; o que continuar invalido e descartado
        try:
            fixed = await call([*messages, {"role": "assistant", "content": json.dumps(first, ensure_ascii=False)}, prompt.repair_message(bad)])
            ok2, bad2 = _split([c for c in (fixed.get("widgets") or []) if isinstance(c, dict)][: len(bad)], ds, fields, labels)
            ok += ok2
            # cada correcao valida resolve um recusado; o restante segue descartado (motivo mais recente primeiro)
            bad = (bad2 + bad)[: max(0, len(bad) - len(ok2))]
        except DomainError as e:
            log.info("ai_repair_failed", code=e.code)

    proposals: list[sc.Proposal] = []
    repeated: list[tuple[str, str]] = []  # (titulo sugerido, titulo do grafico igual)
    for w in ok[: body.max_proposals]:
        sig = _sig(w["type"], w["query_config"])
        if sig in seen:
            repeated.append((w["title"], seen[sig]))  # mesma informacao ja no painel (ou sugerida duas vezes)
            continue
        seen[sig] = w["title"]
        tmp = Widget(id=uuid.uuid4(), type=w["type"], title=w["title"], dataset_id=ds.id, query_config=w["query_config"],
                     viz_config=w["viz_config"], follows_global_period=w["follows_global_period"])
        preview = await widget_result(session, p, tmp, None, [], body.default_period)
        proposals.append(sc.Proposal(id=uuid.uuid4().hex[:12], dataset_id=ds.id, preview=preview, **w))

    digest = hashlib.sha256(body.prompt.encode()).hexdigest()[:16]
    await audit.record(session, "ai.generate", request=request, principal=p, resource_type="dataset", resource_id=ds.id,
                       metadata={"model": rt.model, "prompt_chars": len(body.prompt), "prompt_sha256": digest,
                                 "proposals": len(proposals), "discarded": len(bad), "repeated": len(repeated),
                                 **({"dashboard_id": str(body.dashboard_id)} if body.dashboard_id else {}), **usage})
    await session.commit()
    return sc.ProposalsOut(explanation=str(first.get("explanation") or "")[:600], proposals=proposals,
                           discarded=[sc.Discarded(title=t, reason=r) for t, r in bad]
                           + [sc.Discarded(title=t, reason=f"Mostra a mesma informação de “{same}”.") for t, same in repeated],
                           # ajustes servem para encaixar os novos: sem nenhum novo valido, nao sobram
                           layout_changes=_layout_changes(first.get("layout_changes") or [], current) if current and proposals else [],
                           usage=sc.Usage(model=rt.model, **usage))
