import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.config import get_settings
from app.core.deps import get_session, public, require_permission
from app.modules.devices import schemas as sc
from app.modules.devices import service

router = APIRouter(tags=["devices"])
DEVICE_COOKIE = "gd_device"
DEVICE_COOKIE_PATH = "/api/v1/device"
dev_mgr = require_permission("device:manage")
pl_mgr = require_permission("playlist:manage")


@router.post("/device-pairing/start", response_model=sc.PairStartOut, dependencies=[Depends(public)])
async def start(request: Request, s: AsyncSession = Depends(get_session)):
    return await service.start_pairing(s, request)


@router.post("/device-pairing/poll", response_model=sc.PollOut, dependencies=[Depends(public)])
async def poll(body: sc.PollIn, request: Request, response: Response, s: AsyncSession = Depends(get_session)):
    out, cred = await service.poll(s, request, body.device_code)
    if cred:
        cfg = get_settings()
        response.set_cookie(DEVICE_COOKIE, cred, max_age=cfg.device_cred_days * 86400, httponly=True, secure=cfg.cookie_secure,
                            samesite="strict", path=DEVICE_COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return out


@router.get("/device-pairing/lookup", response_model=sc.LookupOut)
async def lookup(user_code: str, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.lookup(s, p, user_code)


@router.post("/device-pairing/approve", response_model=sc.DeviceOut)
async def approve(body: sc.ApproveIn, request: Request, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.approve(s, request, p, body)


@router.post("/device-pairing/deny", status_code=204)
async def deny(body: sc.DenyIn, request: Request, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    await service.deny(s, request, p, body.user_code)
    return Response(status_code=204)


@router.post("/device/token", response_model=sc.DeviceTokenOut, dependencies=[Depends(public)])
async def device_token(request: Request, response: Response, s: AsyncSession = Depends(get_session)):
    from app.core.errors import Unauthorized

    try:
        out = await service.exchange_token(s, request, request.cookies.get(DEVICE_COOKIE))
    except Unauthorized:
        response.delete_cookie(DEVICE_COOKIE, path=DEVICE_COOKIE_PATH)
        raise
    response.headers["Cache-Control"] = "no-store"
    return out


@router.get("/devices", response_model=list[sc.DeviceOut])
async def devices(_: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.list_devices(s)


@router.get("/devices/{did}", response_model=sc.DeviceOut)
async def device(did: uuid.UUID, _: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.get_device(s, did)


@router.patch("/devices/{did}", response_model=sc.DeviceOut)
async def patch_device(did: uuid.UUID, body: sc.DevicePatch, request: Request, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.patch_device(s, request, p, did, body)


@router.post("/devices/{did}/revoke", response_model=sc.DeviceOut)
async def revoke(did: uuid.UUID, request: Request, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.revoke(s, request, p, did)


@router.put("/devices/{did}/playlist", response_model=sc.DeviceOut)
async def device_playlist(did: uuid.UUID, body: sc.DevicePlaylistIn, request: Request, p: Principal = Depends(dev_mgr), s: AsyncSession = Depends(get_session)):
    return await service.set_device_playlist(s, request, p, did, body.playlist_id)


@router.get("/playlists", response_model=list[sc.PlaylistOut])
async def playlists(_: Principal = Depends(require_permission("playlist:manage", "device:manage", any_of=True)), s: AsyncSession = Depends(get_session)):
    return await service.list_playlists(s)


@router.post("/playlists", response_model=sc.PlaylistOut, status_code=201)
async def create_playlist(body: sc.PlaylistIn, request: Request, p: Principal = Depends(pl_mgr), s: AsyncSession = Depends(get_session)):
    return await service.create_playlist(s, request, p, body)


@router.patch("/playlists/{pid}", response_model=sc.PlaylistOut)
async def rename_playlist(pid: uuid.UUID, body: sc.PlaylistIn, request: Request, p: Principal = Depends(pl_mgr), s: AsyncSession = Depends(get_session)):
    return await service.rename_playlist(s, request, p, pid, body)


@router.delete("/playlists/{pid}", status_code=204)
async def delete_playlist(pid: uuid.UUID, request: Request, p: Principal = Depends(pl_mgr), s: AsyncSession = Depends(get_session)):
    await service.delete_playlist(s, request, p, pid)
    return Response(status_code=204)


@router.put("/playlists/{pid}/items", response_model=sc.PlaylistOut)
async def put_items(pid: uuid.UUID, body: list[sc.PlaylistItemIn], request: Request, p: Principal = Depends(pl_mgr), s: AsyncSession = Depends(get_session)):
    return await service.put_items(s, request, p, pid, body)
