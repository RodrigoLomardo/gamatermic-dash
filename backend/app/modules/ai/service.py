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
from app.modules.dashboards.widget_types import validate_widget
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


def _sig(wtype: str, qc: dict) -> str:
    return wtype + json.dumps(qc, sort_keys=True, ensure_ascii=False)


async def _existing(session: AsyncSession, p: Principal, dashboard_id: uuid.UUID, dataset_id: uuid.UUID) -> tuple[list[str], set[str]]:
    """Titulos (para o prompt) e assinaturas (para descartar repetidos) dos graficos ja no painel."""
    d = await get_dash(session, dashboard_id)
    await require_can(session, p, "dashboard:edit", "dashboard", d.id, d.sector_id, "edit")
    ws = (await session.scalars(select(Widget).where(Widget.dashboard_id == d.id))).all()
    return [w.title for w in ws], {_sig(w.type, w.query_config) for w in ws if w.dataset_id == dataset_id}


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
    titles, seen = await _existing(session, p, body.dashboard_id, ds.id) if body.dashboard_id else ([], set())
    fields, labels, infos = await _context(session, ds)
    if not fields:
        raise Unprocessable("Este dataset não tem campos que a IA possa usar.", code="ai_no_fields")

    messages = prompt.build_messages(ds.name, ds.description, ds.time_field, infos, body.prompt.strip(), body.max_proposals, _rules(fields), titles)
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
    repeated: list[str] = []
    for w in ok[: body.max_proposals]:
        sig = _sig(w["type"], w["query_config"])
        if sig in seen:
            repeated.append(w["title"])  # mesmo grafico duas vezes ou ja presente no painel
            continue
        seen.add(sig)
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
                           + [sc.Discarded(title=t, reason="Já existe um gráfico igual no painel.") for t in repeated],
                           usage=sc.Usage(model=rt.model, **usage))
