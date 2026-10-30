import secrets
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.catalog import PERMISSIONS
from app.core.authz.policy import Principal, load_user_principal, max_assignable_check
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.security import hash_password
from app.modules.audit import service as audit
from app.modules.auth.repository import revoke_all_for_user
from app.modules.iam import repository as repo
from app.modules.iam import schemas as sc
from app.modules.iam.models import (
    Group,
    GroupRole,
    Permission,
    ResourceGrant,
    Role,
    RolePermission,
    Sector,
    User,
    UserGroup,
)


def _temp_password() -> str:
    return secrets.token_urlsafe(12) + "aZ9"


# ---------------- usuarios ----------------
async def user_out(session: AsyncSession, u: User, temp: str | None = None) -> sc.UserOut:
    out = sc.UserOut.model_validate(u)
    out.role_ids = await repo.user_role_ids(session, u.id)
    out.group_ids = await repo.user_group_ids(session, u.id)
    out.temp_password = temp
    return out


async def _get_user(session: AsyncSession, uid: uuid.UUID) -> User:
    u = await session.get(User, uid)
    if u is None:
        raise NotFound("Usuário não encontrado.")
    return u


async def list_users(session: AsyncSession, q: str | None, limit: int, offset: int) -> list[sc.UserOut]:
    stmt = select(User).order_by(User.full_name).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    return [await user_out(session, u) for u in (await session.scalars(stmt)).all()]


async def create_user(session: AsyncSession, request: Request, actor: Principal, body: sc.UserCreate) -> sc.UserOut:
    if body.role_ids:
        max_assignable_check(actor, await repo.perms_of_roles(session, body.role_ids))
    temp = _temp_password()
    u = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(temp),
             status="active", must_change_password=True)
    session.add(u)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe um usuário com este e-mail.") from e
    await repo.set_user_roles(session, u.id, body.role_ids)
    await repo.set_user_groups(session, u.id, body.group_ids)
    await audit.record(session, "user.create", request=request, principal=actor, resource_type="user", resource_id=u.id,
                       metadata={"email": u.email, "role_ids": [str(r) for r in body.role_ids]})
    await session.commit()
    return await user_out(session, u, temp)


async def get_user(session: AsyncSession, uid: uuid.UUID) -> sc.UserOut:
    return await user_out(session, await _get_user(session, uid))


async def update_user(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID, body: sc.UserUpdate) -> sc.UserOut:
    u = await _get_user(session, uid)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "disabled":
        await _guard_last_admin(session, u.id)
        await revoke_all_for_user(session, u.id, "disabled", utcnow())
    for k, v in changes.items():
        setattr(u, k, v)
    if "status" in changes:
        await repo.bump_authz(session, [u.id])
    await audit.record(session, "user.update", request=request, principal=actor, resource_type="user", resource_id=u.id, metadata=changes)
    await session.commit()
    return await user_out(session, u)


async def _guard_last_admin(session: AsyncSession, removing: uuid.UUID) -> None:
    admins = await repo.active_admin_ids(session)
    if removing in admins and len(admins - {removing}) == 0:
        raise Conflict("Não é possível remover o último Administrador ativo.", code="last_admin")


async def set_roles(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID, role_ids: list[uuid.UUID]) -> sc.UserOut:
    u = await _get_user(session, uid)
    found = set((await session.scalars(select(Role.id).where(Role.id.in_(role_ids)))).all())
    if found != set(role_ids):
        raise Unprocessable("Perfil inexistente.")
    max_assignable_check(actor, await repo.perms_of_roles(session, role_ids))
    admin_role = await session.scalar(select(Role.id).where(Role.name == "Administrador"))
    if admin_role not in role_ids:
        await _guard_last_admin(session, u.id)
    await repo.set_user_roles(session, u.id, role_ids)
    await repo.bump_authz(session, [u.id])
    await audit.record(session, "user.roles.changed", request=request, principal=actor, resource_type="user",
                       resource_id=u.id, metadata={"role_ids": [str(r) for r in role_ids]})
    await session.commit()
    return await user_out(session, u)


async def set_groups(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID, group_ids: list[uuid.UUID]) -> sc.UserOut:
    u = await _get_user(session, uid)
    found = set((await session.scalars(select(Group.id).where(Group.id.in_(group_ids)))).all())
    if found != set(group_ids):
        raise Unprocessable("Grupo inexistente.")
    await repo.set_user_groups(session, u.id, group_ids)
    await repo.bump_authz(session, [u.id])
    await audit.record(session, "user.groups.changed", request=request, principal=actor, resource_type="user",
                       resource_id=u.id, metadata={"group_ids": [str(r) for r in group_ids]})
    await session.commit()
    return await user_out(session, u)


async def unlock_user(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID) -> sc.UserOut:
    u = await _get_user(session, uid)
    u.failed_login_count = 0
    u.locked_until = None
    await audit.record(session, "user.unlock", request=request, principal=actor, resource_type="user", resource_id=u.id)
    await session.commit()
    return await user_out(session, u)


async def reset_password(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID) -> sc.UserOut:
    u = await _get_user(session, uid)
    temp = _temp_password()
    u.password_hash = hash_password(temp)
    u.must_change_password = True
    u.failed_login_count = 0
    u.locked_until = None
    await revoke_all_for_user(session, u.id, "password_reset", utcnow())
    await audit.record(session, "user.password.reset", request=request, principal=actor, resource_type="user", resource_id=u.id)
    await session.commit()
    return await user_out(session, u, temp)


async def anonymize_user(session: AsyncSession, request: Request, actor: Principal, uid: uuid.UUID) -> sc.UserOut:
    u = await _get_user(session, uid)
    await _guard_last_admin(session, u.id)
    u.email = f"anon-{u.id.hex[:12]}@anonimizado.invalid"
    u.full_name = "Usuário anonimizado"
    u.password_hash = None
    u.status = "disabled"
    u.anonymized_at = utcnow()
    await revoke_all_for_user(session, u.id, "anonymized", utcnow())
    await repo.bump_authz(session, [u.id])
    await audit.record(session, "user.anonymize", request=request, principal=actor, resource_type="user", resource_id=u.id)
    await session.commit()
    return await user_out(session, u)


async def export_me(session: AsyncSession, p: Principal) -> dict:
    u = await _get_user(session, p.id)
    pr = await load_user_principal(session, u)
    return {
        "id": str(u.id), "email": u.email, "full_name": u.full_name, "status": u.status,
        "created_at": u.created_at.isoformat(), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "roles": pr.role_names, "permissions": pr.perms,
    }


async def effective_permissions(session: AsyncSession, uid: uuid.UUID) -> dict:
    u = await _get_user(session, uid)
    p = await load_user_principal(session, u, use_cache=False)
    roles = (await session.scalars(select(Role).where(Role.id.in_(p.role_ids)))).all() if p.role_ids else []
    groups = (await session.scalars(select(Group).where(Group.id.in_(p.group_ids)))).all() if p.group_ids else []
    grants = (await session.scalars(select(ResourceGrant).where(
        ((ResourceGrant.subject_type == "user") & (ResourceGrant.subject_id == u.id))
        | ((ResourceGrant.subject_type == "group") & (ResourceGrant.subject_id.in_(p.group_ids or [uuid.uuid4()])))
        | ((ResourceGrant.subject_type == "role") & (ResourceGrant.subject_id.in_(p.role_ids or [uuid.uuid4()])))
    ))).all()
    return {
        "permissions": p.perms,
        "roles": [{"id": str(r.id), "name": r.name} for r in roles],
        "groups": [{"id": str(g.id), "name": g.name} for g in groups],
        "grants": [{"subject_type": g.subject_type, "resource_type": g.resource_type, "resource_id": str(g.resource_id),
                    "access_level": g.access_level} for g in grants],
        "explanation": "Permissões vêm das roles diretas e das roles dos grupos; escopo 'granted' exige concessão no recurso ou setor.",
    }


# ---------------- roles ----------------
async def role_out(session: AsyncSession, r: Role) -> sc.RoleOut:
    out = sc.RoleOut(id=r.id, name=r.name, description=r.description, is_system=r.is_system)
    out.permissions = [sc.RolePermIn(code=c, scope=s) for c, s in sorted((await repo.role_perms(session, r.id)).items())]  # type: ignore[arg-type]
    return out


async def _set_role_perms(session: AsyncSession, actor: Principal, role: Role, perms: list[sc.RolePermIn]) -> None:
    for p in perms:
        if p.code not in PERMISSIONS:
            raise Unprocessable(f"Permissão desconhecida: {p.code}")
    max_assignable_check(actor, {p.code: p.scope for p in perms})
    cat = {c: i for c, i in (await session.execute(select(Permission.code, Permission.id))).all()}
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    session.add_all([RolePermission(role_id=role.id, permission_id=cat[p.code], scope=p.scope) for p in perms])


async def create_role(session: AsyncSession, request: Request, actor: Principal, body: sc.RoleCreate) -> sc.RoleOut:
    r = Role(name=body.name, description=body.description, is_system=False)
    session.add(r)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe um perfil com este nome.") from e
    await _set_role_perms(session, actor, r, body.permissions)
    await audit.record(session, "role.create", request=request, principal=actor, resource_type="role", resource_id=r.id,
                       metadata={"name": r.name})
    await session.commit()
    return await role_out(session, r)


async def _get_role(session: AsyncSession, rid: uuid.UUID) -> Role:
    r = await session.get(Role, rid)
    if r is None:
        raise NotFound("Perfil não encontrado.")
    return r


async def update_role(session: AsyncSession, request: Request, actor: Principal, rid: uuid.UUID, body: sc.RoleUpdate) -> sc.RoleOut:
    r = await _get_role(session, rid)
    if r.is_system:
        raise Forbidden("Perfis de sistema não podem ser alterados.", code="system_role")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    await audit.record(session, "role.update", request=request, principal=actor, resource_type="role", resource_id=r.id)
    await session.commit()
    return await role_out(session, r)


async def put_role_permissions(session: AsyncSession, request: Request, actor: Principal, rid: uuid.UUID, perms: list[sc.RolePermIn]) -> sc.RoleOut:
    r = await _get_role(session, rid)
    if r.is_system:
        raise Forbidden("Perfis de sistema não podem ser alterados.", code="system_role")
    await _set_role_perms(session, actor, r, perms)
    await repo.bump_authz(session)
    await audit.record(session, "role.permissions.changed", request=request, principal=actor, resource_type="role",
                       resource_id=r.id, metadata={"permissions": [p.model_dump() for p in perms]})
    await session.commit()
    return await role_out(session, r)


async def delete_role(session: AsyncSession, request: Request, actor: Principal, rid: uuid.UUID) -> None:
    r = await _get_role(session, rid)
    if r.is_system:
        raise Forbidden("Perfis de sistema não podem ser removidos.", code="system_role")
    await session.delete(r)
    await repo.bump_authz(session)
    await audit.record(session, "role.delete", request=request, principal=actor, resource_type="role", resource_id=rid)
    await session.commit()


async def list_roles(session: AsyncSession) -> list[sc.RoleOut]:
    return [await role_out(session, r) for r in (await session.scalars(select(Role).order_by(Role.name))).all()]


# ---------------- grupos ----------------
async def group_out(session: AsyncSession, g: Group) -> sc.GroupOut:
    out = sc.GroupOut(id=g.id, name=g.name, description=g.description)
    out.member_ids = list((await session.scalars(select(UserGroup.user_id).where(UserGroup.group_id == g.id))).all())
    out.role_ids = list((await session.scalars(select(GroupRole.role_id).where(GroupRole.group_id == g.id))).all())
    return out


async def _get_group(session: AsyncSession, gid: uuid.UUID) -> Group:
    g = await session.get(Group, gid)
    if g is None:
        raise NotFound("Grupo não encontrado.")
    return g


async def list_groups(session: AsyncSession) -> list[sc.GroupOut]:
    return [await group_out(session, g) for g in (await session.scalars(select(Group).order_by(Group.name))).all()]


async def create_group(session: AsyncSession, request: Request, actor: Principal, body: sc.GroupIn) -> sc.GroupOut:
    g = Group(name=body.name, description=body.description)
    session.add(g)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe um grupo com este nome.") from e
    await audit.record(session, "group.create", request=request, principal=actor, resource_type="group", resource_id=g.id)
    await session.commit()
    return await group_out(session, g)


async def update_group(session: AsyncSession, request: Request, actor: Principal, gid: uuid.UUID, body: sc.GroupIn) -> sc.GroupOut:
    g = await _get_group(session, gid)
    g.name, g.description = body.name, body.description
    await audit.record(session, "group.update", request=request, principal=actor, resource_type="group", resource_id=g.id)
    await session.commit()
    return await group_out(session, g)


async def delete_group(session: AsyncSession, request: Request, actor: Principal, gid: uuid.UUID) -> None:
    g = await _get_group(session, gid)
    await session.delete(g)
    await repo.bump_authz(session)
    await audit.record(session, "group.delete", request=request, principal=actor, resource_type="group", resource_id=gid)
    await session.commit()


async def put_group_members(session: AsyncSession, request: Request, actor: Principal, gid: uuid.UUID, ids: list[uuid.UUID]) -> sc.GroupOut:
    g = await _get_group(session, gid)
    await session.execute(delete(UserGroup).where(UserGroup.group_id == gid))
    session.add_all([UserGroup(user_id=u, group_id=gid) for u in set(ids)])
    await repo.bump_authz(session)
    await audit.record(session, "group.members.changed", request=request, principal=actor, resource_type="group", resource_id=gid)
    await session.commit()
    return await group_out(session, g)


async def put_group_roles(session: AsyncSession, request: Request, actor: Principal, gid: uuid.UUID, ids: list[uuid.UUID]) -> sc.GroupOut:
    g = await _get_group(session, gid)
    max_assignable_check(actor, await repo.perms_of_roles(session, ids))
    admin_role = await session.scalar(select(Role.id).where(Role.name == "Administrador"))
    if admin_role in ids and "Administrador" not in actor.role_names:
        raise Forbidden("Somente Administradores atribuem a role Administrador.", code="privilege_escalation")
    await session.execute(delete(GroupRole).where(GroupRole.group_id == gid))
    session.add_all([GroupRole(group_id=gid, role_id=r) for r in set(ids)])
    await repo.bump_authz(session)
    await audit.record(session, "group.roles.changed", request=request, principal=actor, resource_type="group", resource_id=gid)
    await session.commit()
    return await group_out(session, g)


# ---------------- concessoes ----------------
async def resource_sector(session: AsyncSession, rtype: str, rid: uuid.UUID) -> uuid.UUID | None:
    from app.modules.dashboards.models import Dashboard
    from app.modules.datasets.models import Dataset

    if rtype == "sector":
        if await session.get(Sector, rid) is None:
            raise NotFound("Setor não encontrado.")
        return rid
    model = {"dashboard": Dashboard, "dataset": Dataset}.get(rtype)
    if model is None:
        raise Unprocessable("Tipo de recurso inválido.")
    obj: Any = await session.get(model, rid)
    if obj is None:
        raise NotFound("Recurso não encontrado.")
    return obj.sector_id


async def list_grants(session: AsyncSession, rtype: str, rid: uuid.UUID) -> list[ResourceGrant]:
    await resource_sector(session, rtype, rid)
    return await repo.grants_for(session, rtype, rid)


async def put_grants(session: AsyncSession, request: Request, actor: Principal, rtype: str, rid: uuid.UUID,
                     grants: list[sc.GrantIn]) -> list[ResourceGrant]:
    from app.core.authz.policy import can

    sector_id = await resource_sector(session, rtype, rid)
    if not await can(session, actor, "grant:manage", rtype, rid, sector_id, "manage"):
        raise Forbidden("Você precisa de 'manage' neste recurso.")
    await session.execute(delete(ResourceGrant).where(ResourceGrant.resource_type == rtype, ResourceGrant.resource_id == rid))
    rows = [ResourceGrant(subject_type=g.subject_type, subject_id=g.subject_id, resource_type=rtype, resource_id=rid,
                          access_level=g.access_level, expires_at=g.expires_at, granted_by=actor.id) for g in grants]
    session.add_all(rows)
    await repo.bump_authz(session)
    await audit.record(session, "grant.replace", request=request, principal=actor, resource_type=rtype, resource_id=rid,
                       metadata={"grants": [g.model_dump(mode="json") for g in grants]})
    await session.commit()
    return await repo.grants_for(session, rtype, rid)


# ---------------- setores ----------------
async def list_sectors(session: AsyncSession) -> list[Sector]:
    return list((await session.scalars(select(Sector).order_by(Sector.name))).all())


async def create_sector(session: AsyncSession, request: Request, actor: Principal, body: sc.SectorIn) -> Sector:
    s = Sector(slug=body.slug, name=body.name)
    session.add(s)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise Conflict("Já existe um setor com este slug.") from e
    await audit.record(session, "sector.create", request=request, principal=actor, resource_type="sector", resource_id=s.id)
    await session.commit()
    return s


async def count_by(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0
