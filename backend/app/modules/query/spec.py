"""QuerySpec: contrato declarativo e fechado. Nao existe SQL livre."""
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

Agg = Literal["sum", "avg", "count", "min", "max", "count_distinct"]
Op = Literal["eq", "neq", "in", "gt", "gte", "lt", "lte", "between", "contains"]
Granularity = Literal["day", "week", "month", "quarter", "year"]
Preset = Literal[
    "today", "yesterday", "this_week", "last_7_days", "last_30_days", "last_90_days", "this_month", "last_month",
    "this_quarter", "this_year", "last_year", "last_12_months", "all",
]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")]


class Measure(BaseModel):
    field: Name | None = None
    agg: Agg
    alias: Name


class Filter(BaseModel):
    field: Name
    op: Op
    value: Any = None

    @field_validator("value")
    @classmethod
    def _size(cls, v):
        if isinstance(v, list) and len(v) > 200:
            raise ValueError("Lista de valores grande demais.")
        return v


class TimeSpec(BaseModel):
    field: Name | None = None
    granularity: Granularity = "month"


class SortSpec(BaseModel):
    by: str
    dir: Literal["asc", "desc"] = "desc"


class Period(BaseModel):
    mode: Literal["relative", "absolute"] = "relative"
    preset: Preset = "this_month"
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    model_config = {"populate_by_name": True}


class QuerySpec(BaseModel):
    measures: list[Measure] = []
    dimensions: list[Name] = Field(default=[], max_length=3)
    columns: list[Name] = Field(default=[], max_length=12)  # modo "linhas" (tabela)
    time: TimeSpec | None = None
    filters: list[Filter] = Field(default=[], max_length=20)
    sort: list[SortSpec] = Field(default=[], max_length=3)
    limit: int = Field(default=1000, ge=1, le=5000)
    period: Period | None = None
    compare_previous_period: bool = False
