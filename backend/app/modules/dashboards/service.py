import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, accessible, can, require_can
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.events import notify
from app.modules.audit import service as audit
from app.modules.dashboards import schemas as sc
from app.modules.dashboards.models import Dashboard, Widget
from app.modules.dashboards.widget_types import validate_widget
from app.modules.datasets.models import Dataset
from app.modules.query import executor
from app.modules.query.compiler import FieldMeta
from app.modules.query.spec import Filter, Period, QuerySpec


async def get_dash(session: AsyncSession, did: uuid.UUID) -> Dashboard:
    d = await session.get(Dashboard, did)
    if d is None:
        raise NotFound("Dashboard não encontrada.")
    return d


async def _widgets(session: AsyncSession, did: uuid.UUID) -> list[Widget]:
    return list((await session.scalars(select(Widget).where(Widget.dashboard_id == did).order_by(Widget.y, Widget.x))).all())


async def check_view(session: AsyncSession, p: Principal, d: Dashboard) -> None:
    await require_can(session, p, "dashboard:view", "dashboard", d.id, d.sector_id, "view")


async def list_dashboards(session: AsyncSession, p: Principal) -> list[sc.DashboardSummary]:
    all_, direct, sectors = await accessible(session, p, "dashboard:view", "dashboard")
    q = select(Dashboard).order_by(Dashboard.name)
    if not all_:
        if not direct and not sectors:
            return []
        q = q.where(Dashboard.id.in_(direct) | Dashboard.sector_id.in_(sectors))
    counts = dict((await session.execute(select(Widget.dashboard_id, func.count()).group_by(Widget.dashboard_id))).all())
    out = []
    for d in (await session.scalars(q)).all():
        s = sc.DashboardSummary.model_validate(d)
        s.widget_count = counts.get(d.id, 0)
        out.append(s)
    return out


async def dashboard_out(session: AsyncSession, p: Principal, d: Dashboard) -> sc.DashboardOut:
    out = sc.DashboardOut.model_validate(d)
    out.widgets = [sc.WidgetOut.model_validate(w) for w in await _widgets(session, d.id)]
    out.can_edit = await can(session, p, "dashboard:edit", "dashboard", d.id, d.sector_id, "edit")
    return out


async def get(session: AsyncSession, p: Principal, did: uuid.UUID) -> sc.DashboardOut:
    d = await get_dash(session, did)
    await check_view(session, p, d)
    return await dashboard_out(session, p, d)


async def create(session: AsyncSession, request: Request, p: Principal, body: sc.DashboardIn) -> sc.DashboardOut:
    if body.sector_id is not None:
        await require_can(session, p, "dashboard:create", "sector", body.sector_id, body.sector_id, "edit")
    elif p.scope("dashboard:create") != "all":
        raise Forbidden("Informe um setor em que você pode criar dashboards.")
    d = Dashboard(**body.model_dump(), created_by=p.id, updated_by=p.id)
    session.add(d)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe uma dashboard com este slug.") from e
    await audit.record(session, "dashboard.create", request=request, principal=p, resource_type="dashboard", resource_id=d.id)
    await session.commit()
    return await dashboard_out(session, p, d)


def _check_version(d: Dashboard, if_match: int | None) -> None:
    if if_match is not None and if_match != d.version:
        raise Conflict("A dashboard foi alterada por outra pessoa. Recarregue para continuar.", code="version_conflict",
                       extra={"current_version": d.version})


async def _edit_target(session: AsyncSession, p: Principal, did: uuid.UUID, level: str = "edit") -> Dashboard:
    d = await get_dash(session, did)
    await require_can(session, p, "dashboard:edit", "dashboard", d.id, d.sector_id, level)
    return d


async def _touch(session: AsyncSession, d: Dashboard, p: Principal) -> None:
    d.version += 1
    d.updated_by = p.id
    await notify(session, {"type": "config_changed", "dashboard_id": str(d.id)})


async def patch(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.DashboardPatch, if_match: int | None) -> sc.DashboardOut:
    d = await _edit_target(session, p, did)
    _check_version(d, if_match)
    ch = body.model_dump(exclude_unset=True)
    for k, v in ch.items():
        setattr(d, k, v)
    await _touch(session, d, p)
    await audit.record(session, "dashboard.update", request=request, principal=p, resource_type="dashboard", resource_id=d.id, metadata=ch)
    await session.commit()
    return await dashboard_out(session, p, d)


async def delete(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID) -> None:
    d = await get_dash(session, did)
    await require_can(session, p, "dashboard:delete", "dashboard", d.id, d.sector_id, "manage")
    await session.delete(d)
    await audit.record(session, "dashboard.delete", request=request, principal=p, resource_type="dashboard", resource_id=did)
    await notify(session, {"type": "config_changed"})
    await session.commit()


async def duplicate(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID) -> sc.DashboardOut:
    src = await get_dash(session, did)
    await check_view(session, p, src)
    if src.sector_id is not None:
        await require_can(session, p, "dashboard:create", "sector", src.sector_id, src.sector_id, "edit")
    elif p.scope("dashboard:create") != "all":
        raise Forbidden("Sem permissão para criar dashboards.")
    n = 2
    while await session.scalar(select(Dashboard.id).where(Dashboard.slug == f"{src.slug}-copia-{n}")):
        n += 1
    d = Dashboard(slug=f"{src.slug}-copia-{n}", name=f"{src.name} (cópia)", description=src.description, sector_id=src.sector_id,
                  refresh_interval_seconds=src.refresh_interval_seconds, default_period=src.default_period,
                  created_by=p.id, updated_by=p.id)
    session.add(d)
    await session.flush()
    for w in await _widgets(session, src.id):
        session.add(Widget(dashboard_id=d.id, type=w.type, title=w.title, x=w.x, y=w.y, w=w.w, h=w.h, dataset_id=w.dataset_id,
                           query_config=w.query_config, viz_config=w.viz_config, follows_global_period=w.follows_global_period))
    await audit.record(session, "dashboard.create", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"duplicated_from": str(did)})
    await session.commit()
    return await dashboard_out(session, p, d)


async def _validate_widget_cfg(session: AsyncSession, p: Principal, wtype: str, dataset_id: uuid.UUID, qc: dict, vc: dict) -> None:
    ds = await session.get(Dataset, dataset_id)
    if ds is None:
        raise Unprocessable("Dataset inexistente.", code="unknown_dataset")
    # quem monta o widget precisa poder consultar o dataset
    await require_can(session, p, "dataset:query", "dataset", ds.id, ds.sector_id, "view")
    fields: dict[str, FieldMeta] = await executor.load_fields(session, ds.id)
    validate_widget(wtype, qc, vc, fields, ds.time_field)


async def add_widget(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.WidgetIn, if_match: int | None) -> sc.DashboardOut:
    d = await _edit_target(session, p, did)
    _check_version(d, if_match)
    await _validate_widget_cfg(session, p, body.type, body.dataset_id, body.query_config, body.viz_config)
    if body.x + body.w > d.grid_cols:
        raise Unprocessable("O widget ultrapassa a grade de 12 colunas.", code="invalid_layout")
    w = Widget(dashboard_id=d.id, **body.model_dump())
    session.add(w)
    await session.flush()
    await _touch(session, d, p)
    await audit.record(session, "dashboard.widget.add", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"widget_id": str(w.id), "type": w.type})
    await session.commit()
    return await dashboard_out(session, p, d)


async def patch_widget(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, wid: uuid.UUID, body: sc.WidgetPatch, if_match: int | None) -> sc.DashboardOut:
    d = await _edit_target(session, p, did)
    _check_version(d, if_match)
    w = await session.get(Widget, wid)
    if w is None or w.dashboard_id != d.id:
        raise NotFound("Widget não encontrado.")
    ch = body.model_dump(exclude_unset=True)
    merged: dict[str, Any] = {"type": w.type, "dataset_id": w.dataset_id, "query_config": w.query_config, "viz_config": w.viz_config, **ch}
    await _validate_widget_cfg(session, p, merged["type"], merged["dataset_id"], merged["query_config"], merged["viz_config"])
    for k, v in ch.items():
        setattr(w, k, v)
    await _touch(session, d, p)
    await audit.record(session, "dashboard.widget.update", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"widget_id": str(w.id)})
    await session.commit()
    return await dashboard_out(session, p, d)


async def delete_widget(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, wid: uuid.UUID, if_match: int | None) -> sc.DashboardOut:
    d = await _edit_target(session, p, did)
    _check_version(d, if_match)
    w = await session.get(Widget, wid)
    if w is None or w.dashboard_id != d.id:
        raise NotFound("Widget não encontrado.")
    await session.delete(w)
    await _touch(session, d, p)
    await audit.record(session, "dashboard.widget.delete", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"widget_id": str(wid)})
    await session.commit()
    return await dashboard_out(session, p, d)


async def put_layout(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, items: list[sc.LayoutItem], if_match: int | None) -> sc.DashboardOut:
    d = await _edit_target(session, p, did)
    _check_version(d, if_match)
    ws = {w.id: w for w in await _widgets(session, d.id)}
    for it in items:
        w = ws.get(it.id)
        if w is None:
            raise NotFound("Widget do layout não pertence à dashboard.")
        if it.x + it.w > d.grid_cols:
            raise Unprocessable("O widget ultrapassa a grade de 12 colunas.", code="invalid_layout")
        w.x, w.y, w.w, w.h = it.x, it.y, it.w, it.h
    await _touch(session, d, p)
    await audit.record(session, "dashboard.layout.changed", request=request, principal=p, resource_type="dashboard", resource_id=d.id)
    await session.commit()
    return await dashboard_out(session, p, d)


# ---------------- dados ----------------
def _apply_overrides(w: Widget, spec: QuerySpec, period: Period | None, filters: list[Filter], fields: dict[str, FieldMeta], time_field: str | None) -> QuerySpec:
    upd: dict[str, Any] = {}
    if period is not None and w.follows_global_period and time_field:
        upd["period"] = period
    compatible = [f for f in filters if f.field in fields]  # filtros globais so valem em widgets que tem o campo
    if compatible:
        upd["filters"] = [*spec.filters, *compatible]
    return spec.model_copy(update=upd) if upd else spec


async def widget_result(session: AsyncSession, p: Principal, w: Widget, period: Period | None, filters: list[Filter], default_period: str | None) -> dict:
    base = {"widget_id": str(w.id), "type": w.type}
    try:
        if w.dataset_id is None:
            raise Unprocessable("Widget sem dataset.", code="invalid_widget")
        ds = await session.get(Dataset, w.dataset_id)
        if ds is None:
            raise Unprocessable("Dataset removido.", code="unknown_dataset")
        fields = await executor.load_fields(session, ds.id)
        spec = QuerySpec.model_validate(w.query_config)
        if spec.period is None and ds.time_field and default_period and not (period and w.follows_global_period):
            spec = spec.model_copy(update={"period": Period(mode="relative", preset=default_period)})  # type: ignore[arg-type]
        spec = _apply_overrides(w, spec, period, filters, fields, ds.time_field)
        mask = not p.has("dataset:manage")
        res = await executor.execute(session, ds.id, spec, mask_pii=mask)
        return {**base, "data": res["rows"], "previous": res["previous_rows"], "dataset_version": res["dataset_version"],
                "data_as_of": res["data_as_of"], "generated_at": res["generated_at"], "period": res["period"], "error": None}
    except Exception as e:  # noqa: BLE001 - erro isolado por widget
        code = getattr(e, "code", "error")
        msg = getattr(e, "detail", None) or "Falha ao consultar os dados."
        return {**base, "data": None, "previous": None, "dataset_version": None, "data_as_of": None, "generated_at": None,
                "period": None, "error": {"code": code, "message": msg}}


async def dashboard_data(session: AsyncSession, p: Principal, d: Dashboard, period: Period | None, filters: list[Filter]) -> dict:
    widgets = await _widgets(session, d.id)
    results = []
    for w in widgets:  # sequencial: a sessao do request e compartilhada; cache evita custo repetido
        results.append(await widget_result(session, p, w, period, filters, d.default_period))
    return {"dashboard_id": str(d.id), "version": d.version, "widgets": results}


async def data(session: AsyncSession, p: Principal, did: uuid.UUID, req: sc.DataRequest) -> dict:
    d = await get_dash(session, did)
    await check_view(session, p, d)
    return await dashboard_data(session, p, d, req.period, req.filters)


async def preview_query(session: AsyncSession, p: Principal, req: sc.PreviewRequest) -> dict:
    ds = await session.get(Dataset, req.dataset_id)
    if ds is None:
        raise NotFound("Dataset não encontrado.")
    await require_can(session, p, "dataset:query", "dataset", ds.id, ds.sector_id, "view")
    fields = await executor.load_fields(session, ds.id)
    spec = validate_widget(req.type, req.query_config, {}, fields, ds.time_field)
    spec = spec.model_copy(update={"limit": min(spec.limit, 500)})
    res = await executor.execute(session, ds.id, spec, mask_pii=not p.has("dataset:manage"))
    return {"data": res["rows"], "previous": res["previous_rows"], "dataset_version": res["dataset_version"],
            "data_as_of": res["data_as_of"], "period": res["period"]}


