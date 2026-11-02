"""Executa QuerySpec com guardas (timeout, somente leitura), cache por versao e single-flight."""
import asyncio
import hashlib
import json
import uuid
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker, utcnow
from app.core.errors import Unprocessable
from app.core.logging import get_logger
from app.modules.datasets.models import Dataset, DatasetField
from app.modules.query.compiler import FieldMeta, compile_query
from app.modules.query.periods import previous, previous_year, resolve
from app.modules.query.spec import QuerySpec

log = get_logger("query")
_CACHE: OrderedDict[str, dict] = OrderedDict()
_LOCKS: dict[str, asyncio.Lock] = {}
CACHE_MAX = 2000
STATS = {"hits": 0, "misses": 0}


def clear_cache() -> None:
    _CACHE.clear()


def _json_val(v):
    if isinstance(v, Decimal):
        return format(v.normalize(), "f") if v != v.to_integral_value() else str(int(v))
    if isinstance(v, datetime):
        return v.date().isoformat() if v.hour == 0 and v.minute == 0 and v.second == 0 else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


async def load_fields(session: AsyncSession, dataset_id: uuid.UUID) -> dict[str, FieldMeta]:
    rows = (await session.scalars(select(DatasetField).where(DatasetField.dataset_id == dataset_id))).all()
    return {f.name: FieldMeta(f.name, f.data_type, f.role, f.sensitivity) for f in rows}


async def _run(ds_id: uuid.UUID, time_field: str | None, fields: dict[str, FieldMeta], spec: QuerySpec, rng, mask_pii: bool, offset: int = 0) -> list[dict]:
    """Sessao propria, somente leitura, com statement_timeout (no deploy usar role SELECT-only)."""
    q, names = compile_query(spec, ds_id, fields, time_field, rng, mask_pii=mask_pii)
    if offset:
        q = q.offset(offset)
    st = get_settings()
    async with get_sessionmaker()() as qs:
        try:
            await qs.execute(text("SET TRANSACTION READ ONLY"))
            await qs.execute(text(f"SET LOCAL statement_timeout = {int(st.statement_timeout_ms)}"))
            res = await qs.execute(q)
            return [{n: _json_val(v) for n, v in zip(names, r, strict=True)} for r in res.all()]
        except DBAPIError as e:
            if "statement timeout" in str(e).lower() or "canceling statement" in str(e).lower():
                raise Unprocessable("Consulta excedeu o tempo limite.", code="query_timeout") from e
            raise


async def fetch_rows(session: AsyncSession, ds_id: uuid.UUID, spec: QuerySpec, *, mask_pii: bool = False, offset: int = 0) -> dict:
    """Linhas de origem paginadas (drill-through/exportacao). Sem cache: o resultado depende da pagina."""
    ds = await session.get(Dataset, ds_id)
    if ds is None:
        raise Unprocessable("Dataset inexistente.", code="unknown_dataset")
    time_field, version = ds.time_field, ds.version
    fields = await load_fields(session, ds_id)
    if spec.period is not None and not time_field:
        raise Unprocessable("Dataset sem campo de tempo; remova o período.", code="invalid_query")
    rows = await _run(ds_id, time_field, fields, spec, resolve(spec.period), mask_pii, offset)
    return {"rows": rows, "dataset_version": version}


async def execute(session: AsyncSession, ds_id: uuid.UUID, spec: QuerySpec, *, mask_pii: bool = False) -> dict:
    ds = await session.get(Dataset, ds_id)
    if ds is None:
        raise Unprocessable("Dataset inexistente.", code="unknown_dataset")
    time_field, version, loaded = ds.time_field, ds.version, ds.last_loaded_at
    fields = await load_fields(session, ds_id)
    if spec.period is not None and not time_field:
        raise Unprocessable("Dataset sem campo de tempo; remova o período.", code="invalid_query")
    rng = resolve(spec.period)
    prev_rng = (previous_year(spec.period) if spec.compare_to == "last_year" else previous(spec.period)) if spec.compare_previous_period else None
    compile_query(spec, ds_id, fields, time_field, rng, mask_pii=mask_pii)  # valida (422) antes do cache
    key_src = json.dumps({"spec": spec.model_dump(mode="json", by_alias=True), "rng": [str(x) for x in (rng or [])],
                          "prev": [str(x) for x in (prev_rng or [])], "pii": mask_pii}, sort_keys=True)
    key = f"{ds_id}:{version}:{hashlib.sha1(key_src.encode()).hexdigest()}"
    if key in _CACHE:
        _CACHE.move_to_end(key)
        STATS["hits"] += 1
        return _CACHE[key]
    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:  # single-flight: a primeira calcula, as demais reutilizam
        if key in _CACHE:
            STATS["hits"] += 1
            return _CACHE[key]
        STATS["misses"] += 1
        rows = await _run(ds_id, time_field, fields, spec, rng, mask_pii)
        prev_rows = None
        if prev_rng is not None:
            pspec = spec.model_copy(update={"period": None, "compare_previous_period": False})
            prev_rows = await _run(ds_id, time_field, fields, pspec, prev_rng, mask_pii)
        out = {
            "rows": rows, "previous_rows": prev_rows, "dataset_version": version,
            "data_as_of": loaded.isoformat() if loaded else None, "generated_at": utcnow().isoformat(),
            "period": {"from": rng[0].isoformat(), "to": rng[1].isoformat()} if rng else None,
        }
        _CACHE[key] = out
        while len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)
    _LOCKS.pop(key, None)
    return out
