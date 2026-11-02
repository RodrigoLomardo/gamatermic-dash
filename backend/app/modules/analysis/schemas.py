import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.dashboards.schemas import WidgetOverride
from app.modules.query.spec import Filter, Name, Period, SortSpec


class AnalysisFilter(Filter):
    """Filtro como o front o guarda: `src` separa o que veio de drill (breadcrumb) do que foi digitado."""
    src: Literal["drill", "manual"] = "manual"
    time: bool = False  # drill de tempo (desce a granularidade)


class AnalysisFieldOut(BaseModel):
    name: str
    label: str
    data_type: str
    role: str
    sensitivity: str


class AnalysisDatasetFieldsOut(BaseModel):
    dataset_id: uuid.UUID
    name: str
    time_field: str | None
    fields: list[AnalysisFieldOut]


class AnalysisFieldsOut(BaseModel):
    datasets: list[AnalysisDatasetFieldsOut]


class AnalysisValueOut(BaseModel):
    value: str
    count: int


class AnalysisValuesOut(BaseModel):
    values: list[AnalysisValueOut]


class AnalysisSearchHit(BaseModel):
    kind: Literal["field", "value"]
    dataset_id: uuid.UUID
    dataset_name: str
    field: str
    label: str
    value: str | None = None
    count: int | None = None


class AnalysisSearchOut(BaseModel):
    hits: list[AnalysisSearchHit]


class AnalysisColumnOut(BaseModel):
    name: str
    label: str
    data_type: str
    sensitivity: str


class AnalysisQueryIn(BaseModel):
    widget_id: uuid.UUID
    period: Period | None = None
    filters: list[Filter] = Field(default=[], max_length=20)
    override: WidgetOverride | None = None


class AnalysisRecordsIn(BaseModel):
    widget_id: uuid.UUID
    period: Period | None = None
    filters: list[Filter] = Field(default=[], max_length=20)
    columns: list[Name] = Field(default=[], max_length=12)
    sort: SortSpec | None = None
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=50, ge=1, le=200)


class AnalysisRecordsOut(BaseModel):
    columns: list[AnalysisColumnOut]
    rows: list[dict[str, Any]]
    total: int
    offset: int
    limit: int
    has_more: bool


class AnalysisExportIn(BaseModel):
    widget_id: uuid.UUID
    period: Period | None = None
    filters: list[Filter] = Field(default=[], max_length=20)
    columns: list[Name] = Field(default=[], max_length=12)
    sort: SortSpec | None = None


class AnalysisViewState(BaseModel):
    period: Period | None = None
    filters: list[AnalysisFilter] = Field(default=[], max_length=20)
    focus_widget_id: uuid.UUID | None = None


class AnalysisViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: AnalysisViewState


class AnalysisViewOut(BaseModel):
    id: uuid.UUID
    name: str
    state: AnalysisViewState
    created_at: datetime

    model_config = {"from_attributes": True}
