import uuid

from fastapi import Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, can, require_can
from app.core.csvsafe import to_csv
from app.core.errors import Conflict, NotFound, Unprocessable
from app.modules.analysis import repository as repo
from app.modules.analysis import schemas as sc
from app.modules.audit import service as audit
from app.modules.dashboards import service as dash
from app.modules.dashboards.models import Dashboard, Widget
from app.modules.datasets.models import Dataset
from app.modules.query import executor
from app.modules.query.spec import Filter, Measure, Period, QuerySpec, SortSpec

EXPORT_MAX_ROWS = 50_000
EXPORT_PAGE = 5_000
MAX_VIEWS = 50
SEARCH_FIELDS = 8  # campos de texto varridos por busca (por dataset)


async def _dashboard(session: AsyncSession, p: Principal, did: uuid.UUID) -> Dashboard:
    d = await dash.get_dash(session, did)
    await dash.check_view(session, p, d)
    return d


async def _widget(session: AsyncSession, d: Dashboard, wid: uuid.UUID) -> Widget:
    w = await session.get(Widget, wid)
    if w is None or w.dashboard_id != d.id:
        raise NotFound("Widget não encontrado.")
    return w


async def _dataset(session: AsyncSession, p: Principal, ds_id: uuid.UUID | None) -> Dataset:
    ds = await session.get(Dataset, ds_id) if ds_id else None
    if ds is None:
        raise NotFound("Dataset não encontrado.")
    await require_can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id, "view")
    return ds


async def _dashboard_datasets(session: AsyncSession, d: Dashboard) -> list[Dataset]:
    seen: dict[uuid.UUID, Dataset] = {}
    for w in await dash._widgets(session, d.id):
        if w.dataset_id and w.dataset_id not in seen:
            ds = await session.get(Dataset, w.dataset_id)
            if ds is not None:
                seen[ds.id] = ds
    return list(seen.values())


# ---------------- campos, valores e busca ----------------
async def fields(session: AsyncSession, p: Principal, did: uuid.UUID) -> sc.AnalysisFieldsOut:
    d = await _dashboard(session, p, did)
    out = []
    for ds in await _dashboard_datasets(session, d):
        await require_can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id, "view")
        fs = await repo.list_fields(session, ds.id)
        pii_ok = p.has("dataset:manage")
        out.append(sc.AnalysisDatasetFieldsOut(dataset_id=ds.id, name=ds.name, time_field=ds.time_field, fields=[
            sc.AnalysisFieldOut(name=f.name, label=f.label, data_type=f.data_type, role=f.role, sensitivity=f.sensitivity)
            for f in fs if pii_ok or f.sensitivity != "pii"]))
    return sc.AnalysisFieldsOut(datasets=out)


async def _filterable(session: AsyncSession, p: Principal, ds: Dataset, field: str):
    fs = {f.name: f for f in await repo.list_fields(session, ds.id)}
    f = fs.get(field)
    if f is None:
        raise Unprocessable(f"Campo inexistente: '{field}'.", code="unknown_field")
    if f.sensitivity == "pii" and not p.has("dataset:manage"):
        raise Unprocessable(f"Não é possível listar valores do campo pessoal '{field}'.", code="pii_filter")
    return f


async def values(session: AsyncSession, p: Principal, did: uuid.UUID, dataset_id: uuid.UUID, field: str, q: str | None, limit: int) -> sc.AnalysisValuesOut:
    d = await _dashboard(session, p, did)
    ds = await _dataset(session, p, dataset_id)
    if ds.id not in {x.id for x in await _dashboard_datasets(session, d)}:
        raise NotFound("Dataset não pertence a este painel.")
    await _filterable(session, p, ds, field)
    return sc.AnalysisValuesOut(values=[sc.AnalysisValueOut(value=v, count=n) for v, n in await repo.distinct_values(session, ds.id, field, q, limit)])


async def search(session: AsyncSession, p: Principal, did: uuid.UUID, q: str) -> sc.AnalysisSearchOut:
    d = await _dashboard(session, p, did)
    needle = q.strip().lower()
    hits: list[sc.AnalysisSearchHit] = []
    if len(needle) < 2:
        return sc.AnalysisSearchOut(hits=hits)
    for ds in await _dashboard_datasets(session, d):
        if not await can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id, "view"):
            continue
        fs = [f for f in await repo.list_fields(session, ds.id) if f.sensitivity != "pii" or p.has("dataset:manage")]
        for f in fs:
            if needle in f.label.lower() or needle in f.name:
                hits.append(sc.AnalysisSearchHit(kind="field", dataset_id=ds.id, dataset_name=ds.name, field=f.name, label=f.label))
        texts = [f for f in fs if f.data_type == "string" and f.role == "dimension" and f.sensitivity != "pii"][:SEARCH_FIELDS]
        for f in texts:
            for v, n in await repo.distinct_values(session, ds.id, f.name, q.strip(), 3):
                hits.append(sc.AnalysisSearchHit(kind="value", dataset_id=ds.id, dataset_name=ds.name, field=f.name, label=f.label, value=v, count=n))
    return sc.AnalysisSearchOut(hits=hits[:40])


# ---------------- consulta de um widget (tela cheia) ----------------
async def query(session: AsyncSession, p: Principal, did: uuid.UUID, body: sc.AnalysisQueryIn) -> dict:
    d = await _dashboard(session, p, did)
    w = await _widget(session, d, body.widget_id)
    return await dash.widget_result(session, p, w, body.period, body.filters, d.default_period, body.override)


# ---------------- registros (drill-through) e exportacao ----------------
async def _records_spec(session: AsyncSession, p: Principal, d: Dashboard, w: Widget, period: Period | None, filters: list[Filter],
                        columns: list[str], sort: SortSpec | None) -> tuple[Dataset, QuerySpec, list[sc.AnalysisColumnOut]]:
    ds, spec, _ = await dash.effective_spec(session, p, w, period, filters, d.default_period)  # mesmos numeros do grafico
    await require_can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id, "view")
    fs = await repo.list_fields(session, ds.id)
    by_name = {f.name: f for f in fs}
    cols = columns or [f.name for f in fs][:12]
    for c in cols:
        if c not in by_name:
            raise Unprocessable(f"Campo inexistente: '{c}'.", code="unknown_field")
    if sort is not None and sort.by not in cols:
        raise Unprocessable(f"Ordenação por coluna não exibida: '{sort.by}'.", code="invalid_query")
    rspec = spec.model_copy(update={"measures": [], "dimensions": [], "time": None, "columns": cols, "sort": [sort] if sort else [],
                                    "compare_previous_period": False, "limit": 1})
    meta = [sc.AnalysisColumnOut(name=c, label=by_name[c].label, data_type=by_name[c].data_type, sensitivity=by_name[c].sensitivity) for c in cols]
    return ds, rspec, meta


async def records(session: AsyncSession, p: Principal, did: uuid.UUID, body: sc.AnalysisRecordsIn) -> sc.AnalysisRecordsOut:
    d = await _dashboard(session, p, did)
    w = await _widget(session, d, body.widget_id)
    ds, spec, meta = await _records_spec(session, p, d, w, body.period, body.filters, body.columns, body.sort)
    mask = not p.has("dataset:manage")
    page = await executor.fetch_rows(session, ds.id, spec.model_copy(update={"limit": body.limit + 1}), mask_pii=mask, offset=body.offset)
    count = await executor.execute(session, ds.id, spec.model_copy(update={"columns": [], "measures": [Measure(agg="count", alias="n")], "sort": []}), mask_pii=mask)
    rows = page["rows"]
    return sc.AnalysisRecordsOut(columns=meta, rows=rows[: body.limit], total=int(count["rows"][0]["n"]) if count["rows"] else 0,
                         offset=body.offset, limit=body.limit, has_more=len(rows) > body.limit)


async def export_csv(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.AnalysisExportIn) -> Response:
    d = await _dashboard(session, p, did)
    w = await _widget(session, d, body.widget_id)
    ds, spec, meta = await _records_spec(session, p, d, w, body.period, body.filters, body.columns, body.sort)
    mask = not p.has("dataset:manage")
    out: list[list] = []
    while len(out) < EXPORT_MAX_ROWS:
        page = await executor.fetch_rows(session, ds.id, spec.model_copy(update={"limit": min(EXPORT_PAGE, EXPORT_MAX_ROWS - len(out))}), mask_pii=mask, offset=len(out))
        out += [[r[c.name] for c in meta] for r in page["rows"]]
        if len(page["rows"]) < EXPORT_PAGE:
            break
    await audit.record(session, "analysis.export", request=request, principal=p, resource_type="dashboard", resource_id=d.id,
                       metadata={"widget_id": str(w.id), "dataset_id": str(ds.id), "rows": len(out)})
    await session.commit()
    return Response(to_csv([c.label for c in meta], out), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="analise-{d.slug}.csv"', "X-Row-Count": str(len(out))})


# ---------------- visoes salvas ----------------
async def list_views(session: AsyncSession, p: Principal, did: uuid.UUID) -> list[sc.AnalysisViewOut]:
    d = await _dashboard(session, p, did)
    return [sc.AnalysisViewOut.model_validate(v) for v in await repo.list_views(session, d.id, p.id)]


async def create_view(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.AnalysisViewIn) -> sc.AnalysisViewOut:
    from app.modules.analysis.models import AnalysisView

    d = await _dashboard(session, p, did)
    name = body.name.strip()
    if not name:
        raise Unprocessable("Dê um nome à visão.", code="invalid_view")
    if len(await repo.list_views(session, d.id, p.id)) >= MAX_VIEWS:
        raise Unprocessable(f"Limite de {MAX_VIEWS} visões por painel.", code="view_limit")
    if await repo.view_name_exists(session, d.id, p.id, name):
        raise Conflict("Já existe uma visão com este nome.", code="view_name_taken")
    v = AnalysisView(dashboard_id=d.id, owner_user_id=p.id, name=name, state=body.state.model_dump(mode="json", by_alias=True))
    session.add(v)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe uma visão com este nome.", code="view_name_taken") from e
    await audit.record(session, "analysis.view.create", request=request, principal=p, resource_type="dashboard", resource_id=d.id, metadata={"view_id": str(v.id)})
    await session.commit()
    return sc.AnalysisViewOut.model_validate(v)


async def delete_view(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, vid: uuid.UUID) -> None:
    d = await _dashboard(session, p, did)
    v = await repo.get_view(session, vid, d.id, p.id)
    if v is None:
        raise NotFound("Visão não encontrada.")
    await session.delete(v)
    await audit.record(session, "analysis.view.delete", request=request, principal=p, resource_type="dashboard", resource_id=d.id, metadata={"view_id": str(vid)})
    await session.commit()
