import uuid
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.rate_limit import client_ip
from app.modules.audit.models import AuditLog

SENSITIVE_KEYS = {"password", "password_hash", "token", "secret", "refresh_token", "device_code", "temp_password"}


def scrub(meta: Any) -> Any:
    if isinstance(meta, dict):
        return {k: ("***" if k.lower() in SENSITIVE_KEYS else scrub(v)) for k, v in meta.items()}
    if isinstance(meta, list):
        return [scrub(v) for v in meta]
    return meta


async def record(
    session: AsyncSession,
    action: str,
    *,
    request: Request | None = None,
    principal: Principal | None = None,
    actor_type: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    outcome: str = "success",
    metadata: dict | None = None,
    request_id: str | None = None,
) -> None:
    """Grava na mesma transacao da acao (o chamador faz o commit)."""
    if principal is not None:
        actor_type = actor_type or principal.typ
        actor_id = actor_id or principal.id
        actor_label = actor_label or principal.label
    session.add(
        AuditLog(
            actor_type=actor_type or "system", actor_id=actor_id, actor_label=actor_label, action=action,
            resource_type=resource_type, resource_id=str(resource_id) if resource_id is not None else None,
            outcome=outcome, ip=client_ip(request) if request else None,
            user_agent=(request.headers.get("user-agent", "")[:300] if request else None),
            request_id=request_id or (getattr(request.state, "request_id", None) if request else None),
            meta=scrub(metadata or {}),
        )
    )


async def ensure_partitions(session: AsyncSession, months_ahead: int = 3) -> None:
    for i in range(-1, months_ahead + 1):
        await session.execute(text(f"SELECT ensure_audit_partition((now() + interval '{i} month')::date)"))


async def search(
    session: AsyncSession, *, action: str | None, actor: str | None, resource_type: str | None,
    since: datetime | None, until: datetime | None, outcome: str | None, limit: int, before_id: int | None,
) -> list[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        q = q.where(AuditLog.action.like(action.replace("*", "%")))
    if actor:
        q = q.where(AuditLog.actor_label.ilike(f"%{actor}%"))
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if outcome:
        q = q.where(AuditLog.outcome == outcome)
    if since:
        q = q.where(AuditLog.occurred_at >= since)
    if until:
        q = q.where(AuditLog.occurred_at <= until)
    if before_id:
        q = q.where(AuditLog.id < before_id)
    return list((await session.scalars(q)).all())
