import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataType = Literal["string", "integer", "decimal", "date", "datetime", "boolean"]
Role = Literal["dimension", "measure", "time"]


class FieldIn(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")
    label: str
    data_type: DataType
    role: Role = "dimension"
    nullable: bool = True
    is_key: bool = False
    is_indexed: bool = False
    sensitivity: Literal["none", "pii"] = "none"
    parse_options: dict = {}
    source_column: str | None = None  # coluna do arquivo mapeada para este campo


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    label: str
    data_type: str
    role: str
    nullable: bool
    is_key: bool
    is_indexed: bool
    sensitivity: str
    parse_options: dict
    position: int
    source_column: str | None = None


class DatasetIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,78}$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    sector_id: uuid.UUID | None = None
    load_mode: Literal["upsert", "append", "replace_snapshot"] = "upsert"
    time_field: str | None = None
    freshness_sla_seconds: int | None = None
    max_reject_pct: int = Field(default=20, ge=0, le=100)
    strict_mode: bool = False
    parser_options: dict = {}
    fields: list[FieldIn] = []


class DatasetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    load_mode: Literal["upsert", "append", "replace_snapshot"] | None = None
    time_field: str | None = None
    freshness_sla_seconds: int | None = None
    max_reject_pct: int | None = Field(default=None, ge=0, le=100)
    strict_mode: bool | None = None
    parser_options: dict | None = None


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    sector_id: uuid.UUID | None
    load_mode: str
    key_fields: list
    time_field: str | None
    version: int
    row_count: int
    last_loaded_at: datetime | None
    freshness_sla_seconds: int | None
    max_reject_pct: int
    strict_mode: bool
    parser_options: dict = {}
    fields: list[FieldOut] = []
    stale: bool = False


class PreviewOut(BaseModel):
    columns: list[str]
    rows: list[dict]
