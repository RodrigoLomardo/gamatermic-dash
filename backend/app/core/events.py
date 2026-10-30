"""Eventos entre processos via Postgres NOTIFY (entregues no COMMIT da transacao)."""
import asyncio
import contextlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger

CHANNEL = "gama_events"
log = get_logger("events")


async def notify(session: AsyncSession, event: dict) -> None:
    await session.execute(text("SELECT pg_notify(:c, :p)"), {"c": CHANNEL, "p": json.dumps(event, default=str)})


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=200))
    device_id: uuid.UUID | None = None


class Broker:
    """Uma conexao dedicada em LISTEN distribui para assinantes locais (SSE)."""

    def __init__(self) -> None:
        self.subs: set[Subscriber] = set()
        self._task: asyncio.Task | None = None
        self._conn: asyncpg.Connection | None = None
        self._stop = asyncio.Event()

    def subscribe(self, device_id: uuid.UUID | None = None) -> Subscriber:
        s = Subscriber(device_id=device_id)
        self.subs.add(s)
        return s

    def unsubscribe(self, s: Subscriber) -> None:
        self.subs.discard(s)

    def publish_local(self, event: dict) -> None:
        target = event.get("device_id")
        for s in list(self.subs):
            if target and s.device_id and str(s.device_id) != str(target):
                continue
            with contextlib.suppress(asyncio.QueueFull):
                s.queue.put_nowait(event)

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        try:
            self.publish_local(json.loads(payload))
        except Exception:  # noqa: BLE001
            log.warning("notify_parse_failed")

    async def _run(self) -> None:
        dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._conn = await asyncpg.connect(dsn)
                await self._conn.add_listener(CHANNEL, self._on_notify)
                backoff = 1.0
                while not self._stop.is_set() and not self._conn.is_closed():
                    await asyncio.sleep(1)
            except Exception as e:  # noqa: BLE001
                log.warning("listener_error", error=str(e))
            finally:
                if self._conn and not self._conn.is_closed():
                    with contextlib.suppress(Exception):
                        await self._conn.close()
            if not self._stop.is_set():
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task


broker = Broker()
HandlerT = Callable[[dict], None]
