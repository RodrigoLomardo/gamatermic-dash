import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.authz.policy import Principal, can
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, TooManyRequests, Unauthorized, Unprocessable
from app.core.events import notify
from app.core.rate_limit import client_ip, hit
from app.core.security import hash_token, issue_jwt, new_opaque_token, user_code
from app.modules.audit import service as audit
from app.modules.dashboards.models import Dashboard
from app.modules.devices import schemas as sc
from app.modules.devices.models import Device, DeviceCredential, DevicePairingRequest, Playlist, PlaylistItem

ONLINE_SECONDS = 90
MAX_CODE_ATTEMPTS = 10


# ---------------- pareamento ----------------
async def start_pairing(session: AsyncSession, request: Request) -> sc.PairStartOut:
    s = get_settings()
    hit(f"pair:start:{client_ip(request)}", 10, 60)
    device_code = new_opaque_token()
    for _ in range(10):
        code = user_code()
        clash = await session.scalar(select(DevicePairingRequest.id).where(
            DevicePairingRequest.user_code == code, DevicePairingRequest.status == "pending", DevicePairingRequest.expires_at > utcnow()))
        if not clash:
            break
    session.add(DevicePairingRequest(
        device_code_hash=hash_token(device_code), user_code=code, status="pending",
        expires_at=utcnow() + timedelta(seconds=s.pairing_ttl_seconds), requested_ip=client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:300]))
    await audit.record(session, "device.pair.requested", request=request, actor_type="system", metadata={"user_code": code})
    await session.commit()
    return sc.PairStartOut(device_code=device_code, user_code=code, expires_in=s.pairing_ttl_seconds,
                           interval=s.pairing_interval_seconds, verification_path=f"/admin/devices?code={code}")


async def _req_by_device_code(session: AsyncSession, code: str) -> DevicePairingRequest | None:
    return await session.scalar(select(DevicePairingRequest).where(DevicePairingRequest.device_code_hash == hash_token(code)).with_for_update())


async def poll(session: AsyncSession, request: Request, device_code: str) -> tuple[sc.PollOut, str | None]:
    s = get_settings()
    r = await _req_by_device_code(session, device_code)
    if r is None:
        raise NotFound("Código de dispositivo inválido.")
    now = utcnow()
    if r.status == "pending" and r.expires_at <= now:
        r.status = "expired"
    if r.last_poll_at and (now - r.last_poll_at).total_seconds() < s.pairing_interval_seconds - 1 and r.status == "pending":
        r.last_poll_at = now
        await session.commit()
        return sc.PollOut(status="slow_down", interval=s.pairing_interval_seconds + 2), None
    r.last_poll_at = now
    cred = None
    if r.status == "approved" and r.pending_credential:
        cred = crypto.decrypt(r.pending_credential.encode())
        r.pending_credential = None  # entregue uma unica vez
        r.status = "consumed"
        out = sc.PollOut(status="approved", device_id=r.device_id)
    elif r.status == "pending":
        out = sc.PollOut(status="authorization_pending", interval=s.pairing_interval_seconds)
    elif r.status in ("expired", "consumed"):
        out = sc.PollOut(status="expired")
    else:
        out = sc.PollOut(status="denied")
    await session.commit()
    return out, cred


async def _pending_by_user_code(session: AsyncSession, code: str, count_attempt: bool = True) -> DevicePairingRequest:
    code = code.strip().upper().replace(" ", "")
    if len(code) == 8:
        code = f"{code[:4]}-{code[4:]}"
    r = await session.scalar(select(DevicePairingRequest).where(
        DevicePairingRequest.user_code == code, DevicePairingRequest.status == "pending").with_for_update())
    if r is None or r.expires_at <= utcnow():
        raise NotFound("Código inválido ou expirado.", code="invalid_code")
    if count_attempt:
        r.attempts += 1
        if r.attempts > MAX_CODE_ATTEMPTS:
            r.status = "denied"
            await session.commit()
            raise TooManyRequests("Código bloqueado por excesso de tentativas.", code="code_locked")
    return r


async def lookup(session: AsyncSession, p: Principal, code: str) -> sc.LookupOut:
    hit(f"pair:lookup:{p.id}", 10, 60)
    r = await _pending_by_user_code(session, code)
    await session.commit()
    return sc.LookupOut(user_code=r.user_code, requested_ip=r.requested_ip, user_agent=r.user_agent, created_at=r.created_at,
                        expires_in=int((r.expires_at - utcnow()).total_seconds()))


async def _can_see_playlist(session: AsyncSession, p: Principal, playlist_id: uuid.UUID) -> bool:
    rows = (await session.execute(select(Dashboard).join(PlaylistItem, PlaylistItem.dashboard_id == Dashboard.id)
                                  .where(PlaylistItem.playlist_id == playlist_id))).scalars().all()
    for d in rows:
        if not await can(session, p, "dashboard:view", "dashboard", d.id, d.sector_id, "view"):
            return False
    return True


async def approve(session: AsyncSession, request: Request, p: Principal, body: sc.ApproveIn) -> sc.DeviceOut:
    hit(f"pair:approve:{p.id}", 10, 60)
    r = await _pending_by_user_code(session, body.user_code)
    if body.playlist_id:
        if await session.get(Playlist, body.playlist_id) is None:
            raise Unprocessable("Playlist inexistente.")
        if not await _can_see_playlist(session, p, body.playlist_id):
            raise Forbidden("Você só pode atribuir playlists cujas dashboards você pode ver.", code="privilege_escalation")
    now = utcnow()
    dev = Device(name=body.name, location=body.location, status="active", playlist_id=body.playlist_id, paired_by=p.id, paired_at=now,
                 last_ip=r.requested_ip, user_agent=r.user_agent)
    session.add(dev)
    await session.flush()
    raw = new_opaque_token()
    session.add(DeviceCredential(device_id=dev.id, token_hash=hash_token(raw),
                                 expires_at=now + timedelta(days=get_settings().device_cred_days)))
    r.status, r.approved_by, r.device_id = "approved", p.id, dev.id
    r.pending_credential = crypto.encrypt(raw).decode()
    await audit.record(session, "device.pair.approved", request=request, principal=p, resource_type="device", resource_id=dev.id,
                       metadata={"name": dev.name, "ip": r.requested_ip})
    await session.commit()
    return device_out(dev)


async def deny(session: AsyncSession, request: Request, p: Principal, code: str) -> None:
    r = await _pending_by_user_code(session, code, count_attempt=False)
    r.status = "denied"
    await audit.record(session, "device.pair.denied", request=request, principal=p, metadata={"user_code": r.user_code})
    await session.commit()


# ---------------- credencial -> token ----------------
async def exchange_token(session: AsyncSession, request: Request, cred: str | None) -> sc.DeviceTokenOut:
    if not cred:
        raise Unauthorized("Dispositivo não pareado.", code="device_not_paired")
    hit(f"devtoken:{client_ip(request)}", 60, 60)
    row = await session.scalar(select(DeviceCredential).where(DeviceCredential.token_hash == hash_token(cred)))
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise Unauthorized("Credencial inválida ou revogada.", code="device_revoked")
    dev = await session.get(Device, row.device_id)
    if dev is None or dev.status != "active":
        raise Unauthorized("Dispositivo revogado.", code="device_revoked")
    row.last_used_at = now
    if row.expires_at - now < timedelta(days=get_settings().device_cred_days / 2):  # renovacao deslizante
        row.expires_at = now + timedelta(days=get_settings().device_cred_days)
    dev.last_seen_at, dev.last_ip = now, client_ip(request)
    ttl = get_settings().device_access_ttl_seconds
    tok, _ = issue_jwt(sub=str(dev.id), typ="device", ttl_seconds=ttl, extra={"scope": "display:read"})
    await session.commit()
    return sc.DeviceTokenOut(access_token=tok, expires_in=ttl)


async def device_principal_from_payload(session: AsyncSession, payload: dict) -> Principal:
    dev = await session.get(Device, uuid.UUID(payload["sub"]))
    if dev is None or dev.status != "active":
        raise Unauthorized("Dispositivo revogado.", code="device_revoked")
    return Principal(typ="device", id=dev.id, label=f"device:{dev.name}", perms={"display:read": "all"}, playlist_id=dev.playlist_id)


# ---------------- gestao ----------------
def device_out(d: Device) -> sc.DeviceOut:
    out = sc.DeviceOut.model_validate(d)
    out.online = bool(d.status == "active" and d.last_seen_at and (utcnow() - d.last_seen_at).total_seconds() < ONLINE_SECONDS)
    return out


async def list_devices(session: AsyncSession) -> list[sc.DeviceOut]:
    return [device_out(d) for d in (await session.scalars(select(Device).order_by(Device.name))).all()]


async def _dev(session: AsyncSession, did: uuid.UUID) -> Device:
    d = await session.get(Device, did)
    if d is None:
        raise NotFound("Dispositivo não encontrado.")
    return d


async def get_device(session: AsyncSession, did: uuid.UUID) -> sc.DeviceOut:
    return device_out(await _dev(session, did))


async def patch_device(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, body: sc.DevicePatch) -> sc.DeviceOut:
    d = await _dev(session, did)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    await audit.record(session, "device.update", request=request, principal=p, resource_type="device", resource_id=d.id)
    await session.commit()
    return device_out(d)


async def revoke(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID) -> sc.DeviceOut:
    d = await _dev(session, did)
    now = utcnow()
    d.status, d.revoked_at, d.revoked_by = "revoked", now, p.id
    await session.execute(update(DeviceCredential).where(DeviceCredential.device_id == d.id, DeviceCredential.revoked_at.is_(None)).values(revoked_at=now))
    await audit.record(session, "device.revoked", request=request, principal=p, resource_type="device", resource_id=d.id)
    await notify(session, {"type": "revoked", "device_id": str(d.id)})
    await session.commit()
    return device_out(d)


async def set_device_playlist(session: AsyncSession, request: Request, p: Principal, did: uuid.UUID, playlist_id: uuid.UUID | None) -> sc.DeviceOut:
    d = await _dev(session, did)
    if playlist_id:
        if await session.get(Playlist, playlist_id) is None:
            raise Unprocessable("Playlist inexistente.")
        if not await _can_see_playlist(session, p, playlist_id):
            raise Forbidden("Você só pode atribuir playlists cujas dashboards você pode ver.", code="privilege_escalation")
    d.playlist_id = playlist_id
    await audit.record(session, "device.playlist.assigned", request=request, principal=p, resource_type="device", resource_id=d.id,
                       metadata={"playlist_id": str(playlist_id) if playlist_id else None})
    await notify(session, {"type": "config_changed", "device_id": str(d.id)})
    await session.commit()
    return device_out(d)


async def touch_heartbeat(session: AsyncSession, p: Principal, request: Request, app_version: str | None, stale: str | None) -> None:
    d = await session.get(Device, p.id)
    if d is None:
        return
    d.last_seen_at, d.last_ip = utcnow(), client_ip(request)
    d.app_version, d.stale_state = app_version, stale
    await session.commit()


# ---------------- playlists ----------------
async def playlist_out(session: AsyncSession, pl: Playlist) -> sc.PlaylistOut:
    out = sc.PlaylistOut(id=pl.id, name=pl.name, version=pl.version)
    rows = (await session.execute(select(PlaylistItem, Dashboard.name).join(Dashboard, Dashboard.id == PlaylistItem.dashboard_id)
                                  .where(PlaylistItem.playlist_id == pl.id).order_by(PlaylistItem.position))).all()
    out.items = [sc.PlaylistItemOut(id=i.id, dashboard_id=i.dashboard_id, duration_seconds=i.duration_seconds,
                                    transition=i.transition, position=i.position, dashboard_name=n) for i, n in rows]  # type: ignore[arg-type]
    out.device_count = await session.scalar(select(func.count()).select_from(Device).where(Device.playlist_id == pl.id)) or 0
    return out


async def list_playlists(session: AsyncSession) -> list[sc.PlaylistOut]:
    return [await playlist_out(session, pl) for pl in (await session.scalars(select(Playlist).order_by(Playlist.name))).all()]


async def create_playlist(session: AsyncSession, request: Request, p: Principal, body: sc.PlaylistIn) -> sc.PlaylistOut:
    pl = Playlist(name=body.name)
    session.add(pl)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe uma playlist com este nome.") from e
    await audit.record(session, "playlist.updated", request=request, principal=p, resource_type="playlist", resource_id=pl.id)
    await session.commit()
    return await playlist_out(session, pl)


async def _pl(session: AsyncSession, pid: uuid.UUID) -> Playlist:
    pl = await session.get(Playlist, pid)
    if pl is None:
        raise NotFound("Playlist não encontrada.")
    return pl


async def rename_playlist(session: AsyncSession, request: Request, p: Principal, pid: uuid.UUID, body: sc.PlaylistIn) -> sc.PlaylistOut:
    pl = await _pl(session, pid)
    pl.name = body.name
    await audit.record(session, "playlist.updated", request=request, principal=p, resource_type="playlist", resource_id=pl.id)
    await session.commit()
    return await playlist_out(session, pl)


async def delete_playlist(session: AsyncSession, request: Request, p: Principal, pid: uuid.UUID) -> None:
    pl = await _pl(session, pid)
    await session.delete(pl)
    await audit.record(session, "playlist.deleted", request=request, principal=p, resource_type="playlist", resource_id=pid)
    await notify(session, {"type": "config_changed"})
    await session.commit()


async def put_items(session: AsyncSession, request: Request, p: Principal, pid: uuid.UUID, items: list[sc.PlaylistItemIn]) -> sc.PlaylistOut:
    pl = await _pl(session, pid)
    for it in items:
        d = await session.get(Dashboard, it.dashboard_id)
        if d is None:
            raise Unprocessable("Dashboard inexistente na playlist.")
        if not await can(session, p, "dashboard:view", "dashboard", d.id, d.sector_id, "view"):
            raise Forbidden("Você precisa ver as dashboards que inclui na playlist.")
    await session.execute(delete(PlaylistItem).where(PlaylistItem.playlist_id == pid))
    session.add_all([PlaylistItem(playlist_id=pid, dashboard_id=i.dashboard_id, position=n, duration_seconds=i.duration_seconds,
                                  transition=i.transition) for n, i in enumerate(items)])
    pl.version += 1
    await audit.record(session, "playlist.updated", request=request, principal=p, resource_type="playlist", resource_id=pid,
                       metadata={"items": [str(i.dashboard_id) for i in items]})
    await notify(session, {"type": "config_changed"})
    await session.commit()
    return await playlist_out(session, pl)


