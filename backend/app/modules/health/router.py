from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_session, public

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", dependencies=[Depends(public)])
async def live():
    return {"status": "ok"}


@router.get("/ready", dependencies=[Depends(public)])
async def ready(s: AsyncSession = Depends(get_session)):
    try:
        await s.execute(text("SELECT 1"))
        pending = await s.scalar(text("SELECT count(*) FROM jobs WHERE status='queued' AND run_at < now() - interval '5 minutes'"))
    except Exception:
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)
    return {"status": "ok", "db": True, "stuck_jobs": pending}
