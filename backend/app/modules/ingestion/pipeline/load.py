"""Load: merge idempotente em lote, numa unica transacao."""
import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.modules.datasets.models import DatasetRow

BATCH = 5000
WRITE_CHUNK = 2500


def row_hash(data: dict) -> str:
    return hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


@dataclass
class Counters:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class PreparedRow:
    key: str
    data: dict
    occurred_at: object


async def merge_batch(session: AsyncSession, dataset_id: uuid.UUID, run_id: uuid.UUID, mode: str,
                      rows: list[PreparedRow], c: Counters) -> None:
    if not rows:
        return
    dedup = {r.key: r for r in rows}  # ultima ocorrencia no lote vence
    keys = list(dedup)
    existing = {
        k: (h, d)
        for k, h, d in (
            await session.execute(
                select(DatasetRow.row_key, DatasetRow.row_hash, DatasetRow.deleted_at).where(
                    DatasetRow.dataset_id == dataset_id, DatasetRow.row_key.in_(keys)
                )
            )
        ).all()
    }
    now = utcnow()
    to_write, seen_unchanged = [], []
    for k, r in dedup.items():
        h = row_hash(r.data)
        ex = existing.get(k)
        if ex is None:
            c.inserted += 1
        elif ex[0] == h and ex[1] is None:
            c.unchanged += 1
            seen_unchanged.append(k)
            continue
        else:
            c.updated += 1
        to_write.append({"dataset_id": dataset_id, "row_key": k, "data": r.data, "row_hash": h,
                         "occurred_at": r.occurred_at, "first_run_id": run_id, "last_run_id": run_id,
                         "created_at": now, "updated_at": now, "deleted_at": None})
    for i in range(0, len(to_write), WRITE_CHUNK):  # asyncpg limita 32767 parametros por comando
        stmt = insert(DatasetRow).values(to_write[i : i + WRITE_CHUNK])
        stmt = stmt.on_conflict_do_update(
            index_elements=["dataset_id", "row_key"],
            set_={"data": stmt.excluded.data, "row_hash": stmt.excluded.row_hash, "occurred_at": stmt.excluded.occurred_at,
                  "last_run_id": stmt.excluded.last_run_id, "updated_at": stmt.excluded.updated_at, "deleted_at": None},
        )
        await session.execute(stmt)
    if seen_unchanged and mode == "replace_snapshot":
        await session.execute(
            update(DatasetRow).where(DatasetRow.dataset_id == dataset_id, DatasetRow.row_key.in_(seen_unchanged))
            .values(last_run_id=run_id)
        )


async def finalize_snapshot(session: AsyncSession, dataset_id: uuid.UUID, run_id: uuid.UUID) -> int:
    res = await session.execute(
        text("UPDATE dataset_rows SET deleted_at=now() WHERE dataset_id=:d AND deleted_at IS NULL "
             "AND last_run_id IS DISTINCT FROM :r"),
        {"d": dataset_id, "r": run_id},
    )
    return getattr(res, "rowcount", 0) or 0
