import asyncio
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.config import get_settings
from app.core.db import get_sessionmaker, utcnow
from app.core.deps import get_session, require_display
from app.core.errors import Forbidden
from app.core.events import broker
from app.modules.dashboards import service as dash_service
from app.modules.dashboards.models import Dashboard, Widget
from app.modules.dashboards.schemas import DashboardOut
from app.modules.datasets.models import Dataset
from app.modules.devices import service as dev_service
from app.modules.devices.models import Device, Playlist, PlaylistItem
from app.modules.query.periods import now_sp

router = APIRouter(prefix="/display", tags=["display"])
HEARTBEAT_SECONDS = 25


async def _playlist_items(session: AsyncSession, playlist_id: uuid.UUID | None):
    if playlist_id is None:
        return []
    return (await session.execute(
        select(PlaylistItem, Dashboard.name).join(Dashboard, Dashboard.id == PlaylistItem.dashboard_id)
        .where(PlaylistItem.playlist_id == playlist_id, Dashboard.status == "published")  # fora do ar: a TV pula
        .order_by(PlaylistItem.position))).all()


async def _device_playlist_id(session: AsyncSession, p: Principal) -> uuid.UUID | None:
    d = await session.get(Device, p.id)  # sempre fresco: playlist pode mudar
    return d.playlist_id if d else None


@router.get("/config")
async def config(p: Principal = Depends(require_display), s: AsyncSession = Depends(get_session)):
    cfg = get_settings()
    if p.typ == "device":
        d = await s.get(Device, p.id)
        pl = await s.get(Playlist, d.playlist_id) if d and d.playlist_id else None
        items = [{"dashboard_id": str(i.dashboard_id), "name": n, "duration_seconds": i.duration_seconds, "transition": i.transition}
                 for i, n in await _playlist_items(s, d.playlist_id if d else None)]
        device = {"id": str(p.id), "name": d.name if d else None, "location": d.location if d else None}
        version = pl.version if pl else 0
    else:
        dashes = await dash_service.list_dashboards(s, p)
        items = [{"dashboard_id": str(x.id), "name": x.name, "duration_seconds": 30, "transition": "fade"} for x in dashes]
        device, version = None, 0
    return {"device": device, "mode": p.typ, "playlist": items, "playlist_version": version, "heartbeat_seconds": 30,
            "poll_seconds": 60, "frontend_version": cfg.frontend_version, "server_time": now_sp().isoformat()}


async def _authorize(session: AsyncSession, p: Principal, did: uuid.UUID) -> Dashboard:
    d = await dash_service.get_dash(session, did)
    if p.typ == "device":
        pid = await _device_playlist_id(session, p)
        ids = {i.dashboard_id for i, _ in await _playlist_items(session, pid)}
        if did not in ids:
            raise Forbidden("Dashboard fora da playlist do dispositivo.")
    else:
        await dash_service.check_view(session, p, d)
    return d


@router.get("/dashboards/{did}", response_model=DashboardOut)
async def dashboard(did: uuid.UUID, p: Principal = Depends(require_display), s: AsyncSession = Depends(get_session)):
    d = await _authorize(s, p, did)
    out = await dash_service.dashboard_out(s, p, d)
    out.can_edit = False
    return out


@router.get("/dashboards/{did}/data")
async def data(did: uuid.UUID, request: Request, response: Response, p: Principal = Depends(require_display),
               s: AsyncSession = Depends(get_session)):
    d = await _authorize(s, p, did)
    ds_ids = (await s.scalars(select(Widget.dataset_id).where(Widget.dashboard_id == d.id, Widget.dataset_id.is_not(None)))).all()
    rows = (await s.execute(select(Dataset.id, Dataset.name, Dataset.version, Dataset.last_loaded_at, Dataset.freshness_sla_seconds)
                            .where(Dataset.id.in_(set(ds_ids))))).all() if ds_ids else []
    now = utcnow()
    sources = [{"dataset_id": str(i), "name": n, "last_loaded_at": ll.isoformat() if ll else None,
                "stale": bool(sla and (ll is None or (now - ll).total_seconds() > sla))} for i, n, _v, ll, sla in rows]
    versions = sorted((str(i), v) for i, _n, v, _ll, _s in rows)
    stale_flags = sorted((x["dataset_id"], x["stale"]) for x in sources)
    etag = '"' + hashlib.sha1(json.dumps([str(d.id), d.version, d.default_period, versions, stale_flags, str(now_sp().date())]).encode()).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    out = await dash_service.dashboard_data(s, p, d, None, [])
    out["sources"] = sources
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"
    return out


class Heartbeat(BaseModel):
    app_version: str | None = None
    stale_state: str | None = None


@router.post("/heartbeat", status_code=204)
async def heartbeat(body: Heartbeat, request: Request, p: Principal = Depends(require_display), s: AsyncSession = Depends(get_session)):
    if p.typ == "device":
        await dev_service.touch_heartbeat(s, p, request, body.app_version, body.stale_state)
    return Response(status_code=204)


def _sse(event: dict) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


@router.get("/stream")
async def stream(request: Request, p: Principal = Depends(require_display)):
    sub = broker.subscribe(p.id if p.typ == "device" else None)

    async def gen():
        try:
            yield b"retry: 3000\n\n"
            yield _sse({"type": "hello", "mode": p.typ})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    if p.typ == "device":  # rede de seguranca: revalida o dispositivo a cada heartbeat
                        async with get_sessionmaker()() as s:
                            d = await s.get(Device, p.id)
                            if d is None or d.status != "active":
                                yield _sse({"type": "revoked"})
                                break
                    yield b": hb\n\n"
                    continue
                yield _sse(ev)
                if ev["type"] == "revoked" and p.typ == "device":
                    break
        finally:
            broker.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


