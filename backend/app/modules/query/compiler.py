"""Compila QuerySpec -> SQLAlchemy Core. Nomes de campo so entram via lista branca (dataset_fields)."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Numeric,
    Select,
    and_,
    cast,
    func,
    literal,
    select,
)
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import Unprocessable
from app.modules.datasets.models import DatasetRow
from app.modules.ingestion.pipeline.transform import CoerceError, FieldSpec, coerce
from app.modules.query.spec import Filter, QuerySpec

NUMERIC = ("integer", "decimal")
TZ = "America/Sao_Paulo"


@dataclass(frozen=True)
class FieldMeta:
    name: str
    data_type: str
    role: str
    sensitivity: str = "none"


def col_expr(f: FieldMeta) -> ColumnElement:
    raw = DatasetRow.data[f.name].astext
    return {
        "string": lambda: raw,
        "integer": lambda: cast(raw, BigInteger),
        "decimal": lambda: cast(raw, Numeric(24, 6)),
        "date": lambda: cast(raw, Date),
        "datetime": lambda: cast(raw, DateTime(timezone=True)),
        "boolean": lambda: cast(raw, Boolean),
    }[f.data_type]()


def _coerce_value(f: FieldMeta, v):
    try:
        out = coerce(v, FieldSpec(f.name, f.data_type, False, False, {}))
    except CoerceError as e:
        raise Unprocessable(f"Valor inválido para o campo '{f.name}': {e.message}", code="invalid_filter") from e
    if f.data_type == "decimal":
        return Decimal(out)
    if f.data_type == "date":
        return datetime.fromisoformat(out).date()
    if f.data_type == "datetime":
        return datetime.fromisoformat(out)
    return out


def _filter_clause(flt: Filter, fields: dict[str, FieldMeta]) -> ColumnElement:
    f = fields.get(flt.field)
    if f is None:
        raise Unprocessable(f"Campo inexistente: '{flt.field}'.", code="unknown_field")
    c = col_expr(f)
    op, v = flt.op, flt.value
    if op in ("in",):
        if not isinstance(v, list) or not v:
            raise Unprocessable("Operador 'in' exige lista.", code="invalid_filter")
        return c.in_([_coerce_value(f, x) for x in v])
    if op == "between":
        if not isinstance(v, list) or len(v) != 2:
            raise Unprocessable("Operador 'between' exige [min, max].", code="invalid_filter")
        return c.between(_coerce_value(f, v[0]), _coerce_value(f, v[1]))
    if op == "contains":
        if f.data_type != "string":
            raise Unprocessable("'contains' só vale para texto.", code="invalid_filter")
        esc = str(v).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return c.ilike(f"%{esc}%", escape="\\")
    if v is None and op in ("eq", "neq"):
        return c.is_(None) if op == "eq" else c.is_not(None)
    val = _coerce_value(f, v)
    return {"eq": c == val, "neq": c != val, "gt": c > val, "gte": c >= val, "lt": c < val, "lte": c <= val}[op]


def validate_spec(spec: QuerySpec, fields: dict[str, FieldMeta], time_field: str | None, *, raw_mode_ok: bool) -> None:
    def need(name: str):
        if name not in fields:
            raise Unprocessable(f"Campo inexistente: '{name}'.", code="unknown_field")
        return fields[name]

    aliases = set()
    if spec.columns:
        if not raw_mode_ok:
            raise Unprocessable("Modo de linhas só é permitido em tabelas.", code="invalid_query")
        if spec.measures or spec.dimensions or spec.time:
            raise Unprocessable("Modo de linhas não combina com medidas/dimensões.", code="invalid_query")
        for c in spec.columns:
            need(c)
    elif not spec.measures:
        raise Unprocessable("Informe ao menos uma medida.", code="invalid_query")
    for m in spec.measures:
        if m.alias in aliases:
            raise Unprocessable(f"Alias duplicado: {m.alias}", code="invalid_query")
        aliases.add(m.alias)
        if m.agg != "count":
            if not m.field:
                raise Unprocessable(f"A agregação '{m.agg}' exige um campo.", code="invalid_query")
            f = need(m.field)
            if m.agg in ("sum", "avg") and f.data_type not in NUMERIC:
                raise Unprocessable(f"'{m.agg}' exige campo numérico ({m.field}).", code="invalid_query")
        elif m.field:
            need(m.field)
    for d in spec.dimensions:
        need(d)
    if spec.time:
        tf = spec.time.field or time_field
        if not tf:
            raise Unprocessable("Dataset sem campo de tempo.", code="invalid_query")
        need(tf)
    for f in spec.filters:
        need(f.field)
    for s in spec.sort:
        if s.by not in aliases and s.by not in spec.dimensions and s.by not in spec.columns and s.by != "time":
            raise Unprocessable(f"Ordenação por campo desconhecido: '{s.by}'.", code="invalid_query")


def compile_query(spec: QuerySpec, dataset_id: uuid.UUID, fields: dict[str, FieldMeta], time_field: str | None,
                  rng: tuple[datetime, datetime] | None, *, mask_pii: bool = False) -> tuple[Select, list[str]]:
    validate_spec(spec, fields, time_field, raw_mode_ok=True)
    where = [DatasetRow.dataset_id == dataset_id, DatasetRow.deleted_at.is_(None)]
    if rng is not None:
        if not time_field:
            raise Unprocessable("Dataset sem campo de tempo para aplicar período.", code="invalid_query")
        where += [DatasetRow.occurred_at >= rng[0], DatasetRow.occurred_at < rng[1]]
    where += [_filter_clause(f, fields) for f in spec.filters]

    cols: list[ColumnElement] = []
    names: list[str] = []
    group: list[ColumnElement] = []
    if spec.columns:
        for c in spec.columns:
            fm = fields[c]
            cols.append(literal("•••").label(c) if (mask_pii and fm.sensitivity == "pii") else col_expr(fm).label(c))
            names.append(c)
        q = select(*cols).where(and_(*where))
        ex = {c: col_expr(fields[c]) for c in spec.columns}
        for s in spec.sort:
            e = ex.get(s.by)
            if e is not None:
                q = q.order_by(e.desc().nulls_last() if s.dir == "desc" else e.asc().nulls_last())
        if not spec.sort and time_field:
            q = q.order_by(DatasetRow.occurred_at.desc().nulls_last())
        return q.limit(spec.limit), names

    if spec.time:
        gran = spec.time.granularity
        t = func.date_trunc(gran, func.timezone(TZ, DatasetRow.occurred_at)).label("time")
        cols.append(t)
        names.append("time")
        group.append(t)
    for d in spec.dimensions:
        e = col_expr(fields[d]).label(d)
        cols.append(e)
        names.append(d)
        group.append(e)
    meas: dict[str, ColumnElement] = {}
    for m in spec.measures:
        if m.agg == "count":
            e = func.count(col_expr(fields[m.field])) if m.field else func.count()
        elif m.agg == "count_distinct":
            e = func.count(col_expr(fields[m.field]).distinct())  # type: ignore[index]
        else:
            fn: Any = {"sum": func.sum, "avg": func.avg, "min": func.min, "max": func.max}[m.agg]
            e = fn(col_expr(fields[m.field]))  # type: ignore[index]
        meas[m.alias] = e
        cols.append(e.label(m.alias))
        names.append(m.alias)
    q = select(*cols).where(and_(*where))
    if group:
        q = q.group_by(*group)
    order = []
    for s in spec.sort:
        if s.by in meas:
            e = meas[s.by]
        elif s.by == "time" and spec.time:
            e = group[0]
        elif s.by in spec.dimensions:
            e = group[(1 if spec.time else 0) + spec.dimensions.index(s.by)]
        else:
            continue
        order.append(e.desc().nulls_last() if s.dir == "desc" else e.asc().nulls_last())
    if not order:
        if spec.time:
            order.append(group[0].asc())
        elif spec.measures and group:
            order.append(meas[spec.measures[0].alias].desc().nulls_last())
    if order:
        q = q.order_by(*order)
    return q.limit(spec.limit), names
