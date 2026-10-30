from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.csvsafe import to_csv
from app.core.deps import get_session, require_permission
from app.modules.audit import service

router = APIRouter(prefix="/audit-logs", tags=["audit"])
audit_view = require_permission("audit:view")


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: int
    occurred_at: datetime
    actor_type: str
    actor_label: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    ip: str | None
    request_id: str | None
    meta: dict


@router.get("", response_model=list[AuditOut])
async def list_logs(
    action: str | None = None, actor: str | None = None, resource_type: str | None = None, outcome: str | None = None,
    since: datetime | None = None, until: datetime | None = None, limit: int = Query(100, le=500),
    before_id: int | None = None, _: Principal = Depends(audit_view), s: AsyncSession = Depends(get_session),
):
    return await service.search(s, action=action, actor=actor, resource_type=resource_type, since=since, until=until,
                                outcome=outcome, limit=limit, before_id=before_id)


@router.get("/export")
async def export(
    request: Request, action: str | None = None, actor: str | None = None, since: datetime | None = None,
    until: datetime | None = None, p: Principal = Depends(audit_view), s: AsyncSession = Depends(get_session),
):
    rows = await service.search(s, action=action, actor=actor, resource_type=None, since=since, until=until,
                                outcome=None, limit=5000, before_id=None)
    await service.record(s, "audit.export", request=request, principal=p, metadata={"rows": len(rows)})
    await s.commit()
    body = to_csv(
        ["id", "quando", "ator", "acao", "recurso", "id_recurso", "resultado", "ip", "request_id"],
        [[r.id, r.occurred_at.isoformat(), r.actor_label, r.action, r.resource_type, r.resource_id, r.outcome, r.ip,
          r.request_id] for r in rows],
    )
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="auditoria.csv"'})
