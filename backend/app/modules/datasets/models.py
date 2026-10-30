import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, uuid_pk


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(24), default="file_upload")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    schedule_cron: Mapped[str | None] = mapped_column(String(60))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sectors.id", ondelete="SET NULL"))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sectors.id", ondelete="SET NULL"))
    storage_kind: Mapped[str] = mapped_column(String(16), default="jsonb")
    load_mode: Mapped[str] = mapped_column(String(20), default="upsert")  # upsert|append|replace_snapshot
    key_fields: Mapped[list] = mapped_column(JSONB, default=list)
    time_field: Mapped[str | None] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_sla_seconds: Mapped[int | None] = mapped_column(Integer)
    max_reject_pct: Mapped[int] = mapped_column(Integer, default=20)
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=False)


class DatasetField(Base):
    __tablename__ = "dataset_fields"
    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160))
    data_type: Mapped[str] = mapped_column(String(10))  # string|integer|decimal|date|datetime|boolean
    role: Mapped[str] = mapped_column(String(10), default="dimension")  # dimension|measure|time
    nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_key: Mapped[bool] = mapped_column(Boolean, default=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitivity: Mapped[str] = mapped_column(String(8), default="none")  # none|pii
    parse_options: Mapped[dict] = mapped_column(JSONB, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("uq_dataset_fields_name", "dataset_id", "name", unique=True),)


class SourceBinding(Base):
    __tablename__ = "source_bindings"
    id: Mapped[uuid.UUID] = uuid_pk()
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), unique=True)
    field_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)  # coluna de origem -> campo
    parser_options: Mapped[dict] = mapped_column(JSONB, default=dict)
    transform_config: Mapped[dict] = mapped_column(JSONB, default=dict)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[uuid.UUID] = uuid_pk()
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    detected_mime: Mapped[str | None] = mapped_column(String(100))
    detected_encoding: Mapped[str | None] = mapped_column(String(40))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual_upload")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    dataset_version_before: Mapped[int | None] = mapped_column(BigInteger)
    dataset_version_after: Mapped[int | None] = mapped_column(BigInteger)
    cursor_state: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class IngestionRowError(Base):
    __tablename__ = "ingestion_row_errors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str | None] = mapped_column(String(160))
    error_code: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    raw_excerpt: Mapped[str | None] = mapped_column(String(200))


class DatasetRow(Base):
    __tablename__ = "dataset_rows"
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    row_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)
    row_hash: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_dataset_rows_time", "dataset_id", "occurred_at", postgresql_where=text("deleted_at IS NULL")),
    )


class Job(Base):
    """Fila de jobs em Postgres (SKIP LOCKED); ver docs/adr/0003."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(60))
    args: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
