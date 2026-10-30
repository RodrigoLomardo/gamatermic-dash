"""Loop do worker: consome jobs e roda rotinas periodicas. Usado in-process (dev) ou como processo (prod)."""
import asyncio
import contextlib
import time

from app.core.logging import get_logger
from app.workers import queue
from app.workers.tasks import TASKS, housekeeping, purge_expired

log = get_logger("worker")


async def process_one() -> bool:
    job = await queue.claim_next()
    if job is None:
        return False
    fn = TASKS.get(job.task)
    if fn is None:
        await queue.finish(job.id, f"tarefa desconhecida: {job.task}", retry=False)
        return True
    try:
        await fn(job.args)
        await queue.finish(job.id, None, retry=False)
    except Exception as e:  # noqa: BLE001
        log.warning("job_failed", job=job.id, task=job.task, error=str(e))
        await queue.finish(job.id, f"{type(e).__name__}: {e}", retry=True)
    return True


async def run_forever(stop: asyncio.Event, poll: float = 1.0) -> None:
    last_house = last_purge = 0.0
    while not stop.is_set():
        try:
            busy = await process_one()
            now = time.monotonic()
            if now - last_house > 60:
                last_house = now
                await queue.requeue_stale()
                await housekeeping()
            if now - last_purge > 6 * 3600:
                last_purge = now
                log.info("purge", **await purge_expired())
        except Exception:  # noqa: BLE001
            log.exception("worker_loop_error")
            busy = False
        if not busy:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll)


async def main() -> None:
    from app.core.logging import configure_logging

    configure_logging()
    stop = asyncio.Event()
    await run_forever(stop)


if __name__ == "__main__":
    asyncio.run(main())
