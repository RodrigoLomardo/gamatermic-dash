import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission, require_user
from app.modules.iam import schemas as sc
from app.modules.iam import service
from app.modules.iam.models import Permission

router = APIRouter(tags=["iam"])
user_mgr = require_permission("user:manage")
role_mgr = require_permission("role:manage")
group_mgr = require_permission("group:manage")
grant_mgr = require_permission("grant:manage")


@router.get("/users", response_model=list[sc.UserOut])
async def list_users(q: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
                     _: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.list_users(s, q, limit, offset)


@router.post("/users", response_model=sc.UserOut, status_code=201)
async def create_user(body: sc.UserCreate, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.create_user(s, request, p, body)


@router.get("/users/{uid}", response_model=sc.UserOut)
async def get_user(uid: uuid.UUID, _: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.get_user(s, uid)


@router.patch("/users/{uid}", response_model=sc.UserOut)
async def patch_user(uid: uuid.UUID, body: sc.UserUpdate, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.update_user(s, request, p, uid, body)


@router.delete("/users/{uid}", response_model=sc.UserOut)
async def disable_user(uid: uuid.UUID, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.update_user(s, request, p, uid, sc.UserUpdate(status="disabled"))


@router.post("/users/{uid}/unlock", response_model=sc.UserOut)
async def unlock(uid: uuid.UUID, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.unlock_user(s, request, p, uid)


@router.post("/users/{uid}/reset-password", response_model=sc.UserOut)
async def reset_pw(uid: uuid.UUID, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.reset_password(s, request, p, uid)


@router.put("/users/{uid}/roles", response_model=sc.UserOut)
async def put_user_roles(uid: uuid.UUID, body: sc.IdList, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.set_roles(s, request, p, uid, body.ids)


@router.put("/users/{uid}/groups", response_model=sc.UserOut)
async def put_user_groups(uid: uuid.UUID, body: sc.IdList, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.set_groups(s, request, p, uid, body.ids)


@router.get("/users/{uid}/effective-permissions")
async def effective(uid: uuid.UUID, _: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.effective_permissions(s, uid)


@router.post("/users/{uid}/anonymize", response_model=sc.UserOut)
async def anonymize(uid: uuid.UUID, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.anonymize_user(s, request, p, uid)


@router.get("/me/export")
async def export_me(p: Principal = Depends(require_user), s: AsyncSession = Depends(get_session)):
    return await service.export_me(s, p)


@router.get("/permissions", response_model=list[sc.PermissionOut])
async def permissions(_: Principal = Depends(role_mgr), s: AsyncSession = Depends(get_session)):
    return (await s.scalars(select(Permission).order_by(Permission.code))).all()


@router.get("/roles", response_model=list[sc.RoleOut])
async def roles(_: Principal = Depends(require_permission("role:manage", "user:manage", "group:manage", any_of=True)), s: AsyncSession = Depends(get_session)):
    return await service.list_roles(s)


@router.post("/roles", response_model=sc.RoleOut, status_code=201)
async def create_role(body: sc.RoleCreate, request: Request, p: Principal = Depends(role_mgr), s: AsyncSession = Depends(get_session)):
    return await service.create_role(s, request, p, body)


@router.patch("/roles/{rid}", response_model=sc.RoleOut)
async def patch_role(rid: uuid.UUID, body: sc.RoleUpdate, request: Request, p: Principal = Depends(role_mgr), s: AsyncSession = Depends(get_session)):
    return await service.update_role(s, request, p, rid, body)


@router.put("/roles/{rid}/permissions", response_model=sc.RoleOut)
async def put_role_perms(rid: uuid.UUID, body: list[sc.RolePermIn], request: Request, p: Principal = Depends(role_mgr), s: AsyncSession = Depends(get_session)):
    return await service.put_role_permissions(s, request, p, rid, body)


@router.delete("/roles/{rid}", status_code=204)
async def del_role(rid: uuid.UUID, request: Request, p: Principal = Depends(role_mgr), s: AsyncSession = Depends(get_session)):
    await service.delete_role(s, request, p, rid)
    return Response(status_code=204)


@router.get("/groups", response_model=list[sc.GroupOut])
async def groups(_: Principal = Depends(require_permission("group:manage", "user:manage", "grant:manage", any_of=True)), s: AsyncSession = Depends(get_session)):
    return await service.list_groups(s)


@router.post("/groups", response_model=sc.GroupOut, status_code=201)
async def create_group(body: sc.GroupIn, request: Request, p: Principal = Depends(group_mgr), s: AsyncSession = Depends(get_session)):
    return await service.create_group(s, request, p, body)


@router.patch("/groups/{gid}", response_model=sc.GroupOut)
async def patch_group(gid: uuid.UUID, body: sc.GroupIn, request: Request, p: Principal = Depends(group_mgr), s: AsyncSession = Depends(get_session)):
    return await service.update_group(s, request, p, gid, body)


@router.delete("/groups/{gid}", status_code=204)
async def del_group(gid: uuid.UUID, request: Request, p: Principal = Depends(group_mgr), s: AsyncSession = Depends(get_session)):
    await service.delete_group(s, request, p, gid)
    return Response(status_code=204)


@router.put("/groups/{gid}/members", response_model=sc.GroupOut)
async def group_members(gid: uuid.UUID, body: sc.IdList, request: Request, p: Principal = Depends(group_mgr), s: AsyncSession = Depends(get_session)):
    return await service.put_group_members(s, request, p, gid, body.ids)


@router.put("/groups/{gid}/roles", response_model=sc.GroupOut)
async def group_roles(gid: uuid.UUID, body: sc.IdList, request: Request, p: Principal = Depends(group_mgr), s: AsyncSession = Depends(get_session)):
    return await service.put_group_roles(s, request, p, gid, body.ids)


@router.get("/resources/{rtype}/{rid}/grants", response_model=list[sc.GrantOut])
async def get_grants(rtype: Literal["dashboard", "dataset", "sector"], rid: uuid.UUID, _: Principal = Depends(grant_mgr), s: AsyncSession = Depends(get_session)):
    return await service.list_grants(s, rtype, rid)


@router.put("/resources/{rtype}/{rid}/grants", response_model=list[sc.GrantOut])
async def put_grants(rtype: Literal["dashboard", "dataset", "sector"], rid: uuid.UUID, body: sc.GrantsPut, request: Request,
                     p: Principal = Depends(grant_mgr), s: AsyncSession = Depends(get_session)):
    return await service.put_grants(s, request, p, rtype, rid, body.grants)


@router.get("/sectors", response_model=list[sc.SectorOut])
async def sectors(_: Principal = Depends(require_user), s: AsyncSession = Depends(get_session)):
    return await service.list_sectors(s)


@router.post("/sectors", response_model=sc.SectorOut, status_code=201)
async def create_sector(body: sc.SectorIn, request: Request, p: Principal = Depends(user_mgr), s: AsyncSession = Depends(get_session)):
    return await service.create_sector(s, request, p, body)
