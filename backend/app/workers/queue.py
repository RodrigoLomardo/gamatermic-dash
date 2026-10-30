"""Fila de jobs em Postgres (FOR UPDATE SKIP LOCKED). Interface fina isolada para trocar por Procrastinate/Celery."""
import uuid
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker, utcnow
from app.modules.datasets.models import Job


async def enqueue(session: AsyncSession, task: str, args: dict, *, request_id: str | None = None, delay: int = 0) -> Job:
    """Enfileira na MESMA transacao do chamador (job e run nascem juntos ou nenhum nasce)."""
    job = Job(task=task, args=args, request_id=request_id, run_at=utcnow() + timedelta(seconds=delay))
    session.add(job)
    await session.flush()
    return job


async def claim_next() -> Job | None:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "UPDATE jobs SET status='running', locked_at=now(), attempts=attempts+1 WHERE id = ("
                    " SELECT id FROM jobs WHERE status='queued' AND run_at <= now() ORDER BY run_at, id"
                    " FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id"
                )
            )
        ).first()
        await s.commit()
        if row is None:
            return None
        return await s.get(Job, row[0])


async def finish(job_id: int, error: str | None, *, retry: bool) -> None:
    async with get_sessionmaker()() as s:
        job = await s.get(Job, job_id)
        if job is None:
            return
        if error is None:
            job.status, job.finished_at = "done", utcnow()
        elif retry and job.attempts < job.max_attempts:
            job.status, job.last_error = "queued", error[:2000]
            job.run_at = utcnow() + timedelta(seconds=2 ** job.attempts * 5)
        else:
            job.status, job.last_error, job.finished_at = "failed", error[:2000], utcnow()
        await s.commit()


async def requeue_stale(minutes: int = 30) -> int:
    async with get_sessionmaker()() as s:
        r = await s.execute(
            text("UPDATE jobs SET status='queued' WHERE status='running' AND locked_at < now() - make_interval(mins => :m)"),
            {"m": minutes},
        )
        await s.commit()
        return getattr(r, "rowcount", 0) or 0


def new_key() -> str:
    return uuid.uuid4().hex
