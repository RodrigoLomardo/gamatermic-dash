import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dataset_id: uuid.UUID
    trigger: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_rejected: int
    error_summary: str | None
    attempt: int
    dataset_version_before: int | None
    dataset_version_after: int | None
    file_name: str | None = None
    dataset_slug: str | None = None
    duplicate: bool = False


class RowErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_number: int
    column_name: str | None
    error_code: str
    message: str
    raw_excerpt: str | None


class InferredField(BaseModel):
    name: str
    label: str
    data_type: str
    role: str
    source_column: str
    is_key: bool = False
    nullable: bool = True
    sample: list[str] = []


class InferOut(BaseModel):
    kind: str
    sheets: list[str]
    sheet: str | None
    columns: list[InferredField]
