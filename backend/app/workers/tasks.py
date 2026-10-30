import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import get_sessionmaker, utcnow
from app.core.logging import get_logger
from app.modules.audit.service import ensure_partitions
from app.modules.datasets.models import UploadedFile
from app.modules.devices.models import DevicePairingRequest
from app.modules.iam.models import RefreshToken
from app.modules.ingestion.runner import execute_run, mark_stuck_runs

log = get_logger("tasks")


async def run_ingestion(args: dict) -> None:
    await execute_run(uuid.UUID(args["run_id"]))


TASKS = {"run_ingestion": run_ingestion}


async def purge_expired() -> dict:
    """Retencao: refresh tokens expirados, pareamentos vencidos e arquivos brutos antigos."""
    s = get_settings()
    out = {}
    async with get_sessionmaker()() as session:
        r = await session.execute(delete(RefreshToken).where(RefreshToken.absolute_expires_at < utcnow() - timedelta(days=7)))
        out["refresh_tokens"] = getattr(r, "rowcount", 0)
        r = await session.execute(delete(DevicePairingRequest).where(DevicePairingRequest.expires_at < utcnow() - timedelta(days=1)))
        out["pairing"] = getattr(r, "rowcount", 0)
        old = (await session.scalars(select(UploadedFile).where(
            UploadedFile.purged_at.is_(None), UploadedFile.created_at < utcnow() - timedelta(days=s.upload_retention_days)))).all()
        for f in old:
            (Path(s.upload_dir) / f.stored_path).unlink(missing_ok=True)
            f.purged_at = utcnow()
        out["files"] = len(old)
        await ensure_partitions(session)
        await session.commit()
    return out


async def housekeeping() -> None:
    stuck = await mark_stuck_runs()
    if stuck:
        log.warning("stuck_runs_marked", count=stuck)

