import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, uuid_pk


class AnalysisView(Base, TimestampMixin):
    """Visao salva da analise (periodo + filtros + drill). Pessoal: pertence a quem salvou."""

    __tablename__ = "analysis_views"
    id: Mapped[uuid.UUID] = uuid_pk()
    dashboard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (Index("uq_analysis_views_owner_name", "dashboard_id", "owner_user_id", "name", unique=True),)
