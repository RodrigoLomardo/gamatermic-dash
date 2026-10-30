import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, uuid_pk


class Dashboard(Base, TimestampMixin):
    __tablename__ = "dashboards"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sectors.id", ondelete="SET NULL"))
    grid_cols: Mapped[int] = mapped_column(Integer, default=12)
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    theme: Mapped[str] = mapped_column(String(16), default="default")
    status: Mapped[str] = mapped_column(String(12), default="published")
    version: Mapped[int] = mapped_column(Integer, default=1)
    default_period: Mapped[str] = mapped_column(String(24), default="this_month")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Widget(Base, TimestampMixin):
    __tablename__ = "widgets"
    id: Mapped[uuid.UUID] = uuid_pk()
    dashboard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(160))
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    w: Mapped[int] = mapped_column(Integer, default=4)
    h: Mapped[int] = mapped_column(Integer, default=3)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    query_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    viz_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    follows_global_period: Mapped[bool] = mapped_column(Boolean, default=True)
