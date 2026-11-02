import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.analysis.models import AnalysisView
from app.modules.datasets.models import DatasetField, DatasetRow


async def list_fields(session: AsyncSession, dataset_id: uuid.UUID) -> list[DatasetField]:
    q = select(DatasetField).where(DatasetField.dataset_id == dataset_id).order_by(DatasetField.position, DatasetField.name)
    return list((await session.scalars(q)).all())


async def distinct_values(session: AsyncSession, dataset_id: uuid.UUID, field: str, q: str | None, limit: int) -> list[tuple[str, int]]:
    """Valores distintos de um campo ja validado contra a lista branca (dataset_fields)."""
    expr = DatasetRow.data[field].astext
    stmt = select(expr, func.count()).where(DatasetRow.dataset_id == dataset_id, DatasetRow.deleted_at.is_(None), expr.is_not(None), expr != "")
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(expr.ilike(f"%{esc}%", escape="\\"))
    stmt = stmt.group_by(expr).order_by(func.count().desc(), expr).limit(limit)
    st = int(get_settings().statement_timeout_ms)
    await session.execute(select(func.set_config("statement_timeout", str(st), True)))
    return [(str(v), int(n)) for v, n in (await session.execute(stmt)).all()]


async def list_views(session: AsyncSession, dashboard_id: uuid.UUID, owner: uuid.UUID) -> list[AnalysisView]:
    q = select(AnalysisView).where(AnalysisView.dashboard_id == dashboard_id, AnalysisView.owner_user_id == owner).order_by(AnalysisView.name)
    return list((await session.scalars(q)).all())


async def get_view(session: AsyncSession, view_id: uuid.UUID, dashboard_id: uuid.UUID, owner: uuid.UUID) -> AnalysisView | None:
    v = await session.get(AnalysisView, view_id)
    return v if v is not None and v.dashboard_id == dashboard_id and v.owner_user_id == owner else None


async def view_name_exists(session: AsyncSession, dashboard_id: uuid.UUID, owner: uuid.UUID, name: str) -> bool:
    q = select(AnalysisView.id).where(AnalysisView.dashboard_id == dashboard_id, AnalysisView.owner_user_id == owner, AnalysisView.name == name)
    return (await session.scalar(q)) is not None
