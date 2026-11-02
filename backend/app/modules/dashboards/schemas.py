import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.dashboards.widget_types import WidgetType
from app.modules.query.spec import Filter, Granularity, Name, Period, QuerySpec


class WidgetIn(BaseModel):
    type: WidgetType
    title: str = Field(min_length=1, max_length=160)
    x: int = Field(default=0, ge=0, le=11)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=4, ge=1, le=12)
    h: int = Field(default=3, ge=1, le=20)
    dataset_id: uuid.UUID
    query_config: dict[str, Any]
    viz_config: dict[str, Any] = {}
    follows_global_period: bool = True


class WidgetPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    type: WidgetType | None = None
    dataset_id: uuid.UUID | None = None
    query_config: dict[str, Any] | None = None
    viz_config: dict[str, Any] | None = None
    follows_global_period: bool | None = None


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    title: str
    x: int
    y: int
    w: int
    h: int
    dataset_id: uuid.UUID | None
    query_config: dict
    viz_config: dict
    follows_global_period: bool


class DashboardIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    sector_id: uuid.UUID | None = None
    refresh_interval_seconds: int = Field(default=60, ge=15, le=3600)
    default_period: str = "this_month"


class DashboardPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    sector_id: uuid.UUID | None = None  # enviado como null remove o setor; omitido não altera
    refresh_interval_seconds: int | None = Field(default=None, ge=15, le=3600)
    default_period: str | None = None


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    sector_id: uuid.UUID | None
    grid_cols: int
    refresh_interval_seconds: int
    default_period: str
    status: str
    version: int
    updated_at: datetime
    widgets: list[WidgetOut] = []
    can_edit: bool = False


class DashboardSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    sector_id: uuid.UUID | None
    status: str
    version: int
    updated_at: datetime
    widget_count: int = 0


class PublicationIn(BaseModel):
    online: bool


class LayoutItem(BaseModel):
    id: uuid.UUID
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1, le=20)


class LayoutPut(BaseModel):
    items: list[LayoutItem]


class WidgetOverride(BaseModel):
    """Ajuste transitorio de um widget na analise (drill/tela cheia). Nunca grava no painel."""
    group_by: Name | None = None
    granularity: Granularity | None = None
    limit: int | None = Field(default=None, ge=1, le=200)


class DataRequest(BaseModel):
    period: Period | None = None
    filters: list[Filter] = []
    overrides: dict[uuid.UUID, WidgetOverride] = Field(default={}, max_length=40)
    force_period: bool = False  # analise: o periodo escolhido vale ate para widgets com periodo proprio


class PreviewRequest(BaseModel):
    dataset_id: uuid.UUID
    type: WidgetType = "table"
    query_config: dict[str, Any]


__all__ = ["QuerySpec"]
