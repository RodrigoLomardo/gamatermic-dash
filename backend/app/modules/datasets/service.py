import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, accessible, require_can
from app.core.db import utcnow
from app.core.errors import Conflict, NotFound, Unprocessable
from app.modules.audit import service as audit
from app.modules.datasets import schemas as sc
from app.modules.datasets.models import Dataset, DatasetField, DatasetRow, DataSource, SourceBinding

DEFAULT_PARSER = {"delimiter": None, "encoding": None, "sheet": None, "header_row": 1}


async def _fields(session: AsyncSession, did: uuid.UUID) -> list[DatasetField]:
    return list((await session.scalars(select(DatasetField).where(DatasetField.dataset_id == did).order_by(DatasetField.position))).all())


async def binding_of(session: AsyncSession, did: uuid.UUID) -> SourceBinding | None:
    return await session.scalar(select(SourceBinding).where(SourceBinding.dataset_id == did))


async def to_out(session: AsyncSession, ds: Dataset) -> sc.DatasetOut:
    out = sc.DatasetOut.model_validate(ds)
    b = await binding_of(session, ds.id)
    mapping = {v: k for k, v in (b.field_mapping if b else {}).items()}  # campo -> coluna
    out.parser_options = (b.parser_options if b else {}) or {}
    out.fields = []
    for f in await _fields(session, ds.id):
        fo = sc.FieldOut.model_validate(f)
        fo.source_column = mapping.get(f.name)
        out.fields.append(fo)
    if ds.freshness_sla_seconds and ds.last_loaded_at:
        out.stale = (utcnow() - ds.last_loaded_at) > timedelta(seconds=ds.freshness_sla_seconds)
    return out


async def get(session: AsyncSession, did: uuid.UUID) -> Dataset:
    ds = await session.get(Dataset, did)
    if ds is None:
        raise NotFound("Dataset não encontrado.")
    return ds


async def list_datasets(session: AsyncSession, p: Principal) -> list[sc.DatasetOut]:
    all_, direct, sectors = await accessible(session, p, "dataset:view", "dataset")
    q = select(Dataset).order_by(Dataset.name)
    if not all_:
        if not direct and not sectors:
            return []
        q = q.where(Dataset.id.in_(direct) | Dataset.sector_id.in_(sectors))
    return [await to_out(session, d) for d in (await session.scalars(q)).all()]


async def get_out(session: AsyncSession, p: Principal, did: uuid.UUID) -> sc.DatasetOut:
    ds = await get(session, did)
    await require_can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id)
    return await to_out(session, ds)


def _validate_fields(fields: list[sc.FieldIn], time_field: str | None) -> None:
    names = [f.name for f in fields]
    if len(set(names)) != len(names):
        raise Unprocessable("Nomes de campo duplicados.")
    if time_field and time_field not in names:
        raise Unprocessable("time_field deve ser um campo do dataset.")
    for f in fields:
        if f.role == "measure" and f.data_type not in ("integer", "decimal"):
            raise Unprocessable(f"Campo '{f.name}': medida deve ser numérica.")
        if f.role == "time" and f.data_type not in ("date", "datetime"):
            raise Unprocessable(f"Campo '{f.name}': campo de tempo deve ser date/datetime.")


async def _apply_fields(session: AsyncSession, ds: Dataset, fields: list[sc.FieldIn], parser: dict | None) -> None:
    _validate_fields(fields, ds.time_field)
    await session.execute(delete(DatasetField).where(DatasetField.dataset_id == ds.id))
    for i, f in enumerate(fields):
        session.add(DatasetField(dataset_id=ds.id, name=f.name, label=f.label, data_type=f.data_type, role=f.role,
                                 nullable=f.nullable and not f.is_key, is_key=f.is_key, is_indexed=f.is_indexed,
                                 sensitivity=f.sensitivity, parse_options=f.parse_options, position=i))
    ds.key_fields = [f.name for f in fields if f.is_key]
    # fonte + binding
    src = await session.scalar(select(DataSource).where(DataSource.name == f"upload:{ds.slug}"))
    if src is None:
        src = DataSource(name=f"upload:{ds.slug}", kind="file_upload", sector_id=ds.sector_id)
        session.add(src)
        await session.flush()
    b = await binding_of(session, ds.id)
    mapping = {(f.source_column or f.label): f.name for f in fields}
    if b is None:
        session.add(SourceBinding(data_source_id=src.id, dataset_id=ds.id, field_mapping=mapping,
                                  parser_options={**DEFAULT_PARSER, **(parser or {})}))
    else:
        b.field_mapping = mapping
        if parser is not None:
            b.parser_options = {**DEFAULT_PARSER, **parser}


async def create(session: AsyncSession, request: Request, p: Principal, body: sc.DatasetIn) -> sc.DatasetOut:
    ds = Dataset(slug=body.slug, name=body.name, description=body.description, sector_id=body.sector_id,
                 load_mode=body.load_mode, time_field=body.time_field, freshness_sla_seconds=body.freshness_sla_seconds,
                 max_reject_pct=body.max_reject_pct, strict_mode=body.strict_mode)
    session.add(ds)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe um dataset com este slug.") from e
    await _apply_fields(session, ds, body.fields, body.parser_options)
    if ds.load_mode != "append" and not ds.key_fields and body.fields:
        raise Unprocessable("Modos upsert/replace_snapshot exigem ao menos um campo-chave.")
    await audit.record(session, "dataset.create", request=request, principal=p, resource_type="dataset", resource_id=ds.id,
                       metadata={"slug": ds.slug})
    await session.commit()
    return await to_out(session, ds)


async def patch(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.DatasetPatch) -> sc.DatasetOut:
    ds = await get(session, did)
    await require_can(session, p, "dataset:manage", "dataset", ds.id, ds.sector_id, "edit")
    ch = body.model_dump(exclude_unset=True)
    parser = ch.pop("parser_options", None)
    for k, v in ch.items():
        setattr(ds, k, v)
    if parser is not None:
        b = await binding_of(session, ds.id)
        if b:
            b.parser_options = {**DEFAULT_PARSER, **parser}
    await audit.record(session, "dataset.update", request=request, principal=p, resource_type="dataset", resource_id=ds.id,
                       metadata=ch)
    await session.commit()
    return await to_out(session, ds)


async def put_fields(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, fields: list[sc.FieldIn]) -> sc.DatasetOut:
    ds = await get(session, did)
    await require_can(session, p, "dataset:manage", "dataset", ds.id, ds.sector_id, "edit")
    await _apply_fields(session, ds, fields, None)
    await audit.record(session, "dataset.fields.changed", request=request, principal=p, resource_type="dataset", resource_id=ds.id)
    await session.commit()
    return await to_out(session, ds)


async def delete_dataset(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID) -> None:
    ds = await get(session, did)
    await require_can(session, p, "dataset:manage", "dataset", ds.id, ds.sector_id, "manage")
    await session.delete(ds)
    await audit.record(session, "dataset.delete", request=request, principal=p, resource_type="dataset", resource_id=did)
    await session.commit()


async def preview(session: AsyncSession, p: Principal, did: uuid.UUID, limit: int = 50) -> sc.PreviewOut:
    ds = await get(session, did)
    await require_can(session, p, "dataset:view", "dataset", ds.id, ds.sector_id)
    fields = await _fields(session, ds.id)
    rows = (await session.scalars(
        select(DatasetRow).where(DatasetRow.dataset_id == did, DatasetRow.deleted_at.is_(None))
        .order_by(DatasetRow.occurred_at.desc().nulls_last()).limit(min(limit, 200))
    )).all()
    pii = {f.name for f in fields if f.sensitivity == "pii"}
    out = [{c.name: ("•••" if c.name in pii and r.data.get(c.name) is not None else r.data.get(c.name)) for c in fields} for r in rows]
    return sc.PreviewOut(columns=[f.name for f in fields], rows=out)


async def refresh_row_count(session: AsyncSession, did: uuid.UUID) -> int:
    n = await session.scalar(text("SELECT count(*) FROM dataset_rows WHERE dataset_id=:d AND deleted_at IS NULL"), {"d": did})
    return int(n or 0)
