import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import clear_cache
from app.modules.iam.models import (
    Group,
    GroupRole,
    Permission,
    ResourceGrant,
    Role,
    RolePermission,
    User,
    UserGroup,
    UserRole,
)


async def bump_authz(session: AsyncSession, user_ids: list[uuid.UUID] | None = None) -> None:
    q = update(User).values(authz_version=User.authz_version + 1)
    if user_ids is not None:
        q = q.where(User.id.in_(user_ids))
    await session.execute(q)
    clear_cache()


async def user_role_ids(session: AsyncSession, uid: uuid.UUID) -> list[uuid.UUID]:
    return list((await session.scalars(select(UserRole.role_id).where(UserRole.user_id == uid))).all())


async def user_group_ids(session: AsyncSession, uid: uuid.UUID) -> list[uuid.UUID]:
    return list((await session.scalars(select(UserGroup.group_id).where(UserGroup.user_id == uid))).all())


async def role_perms(session: AsyncSession, role_id: uuid.UUID) -> dict[str, str]:
    rows = (
        await session.execute(
            select(Permission.code, RolePermission.scope)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
    ).all()
    return {c: s for c, s in rows}


async def perms_of_roles(session: AsyncSession, role_ids: list[uuid.UUID]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rid in role_ids:
        for c, s in (await role_perms(session, rid)).items():
            if out.get(c) != "all":
                out[c] = s
    return out


async def active_admin_ids(session: AsyncSession) -> set[uuid.UUID]:
    admin = await session.scalar(select(Role.id).where(Role.name == "Administrador"))
    if admin is None:
        return set()
    direct = select(UserRole.user_id).where(UserRole.role_id == admin)
    via_group = select(UserGroup.user_id).join(GroupRole, GroupRole.group_id == UserGroup.group_id).where(
        GroupRole.role_id == admin
    )
    ids = set((await session.scalars(direct.union(via_group))).all())
    if not ids:
        return set()
    active = set((await session.scalars(select(User.id).where(User.id.in_(ids), User.status == "active"))).all())
    return active


async def set_user_roles(session: AsyncSession, uid: uuid.UUID, role_ids: list[uuid.UUID]) -> None:
    await session.execute(delete(UserRole).where(UserRole.user_id == uid))
    session.add_all([UserRole(user_id=uid, role_id=r) for r in set(role_ids)])


async def set_user_groups(session: AsyncSession, uid: uuid.UUID, group_ids: list[uuid.UUID]) -> None:
    await session.execute(delete(UserGroup).where(UserGroup.user_id == uid))
    session.add_all([UserGroup(user_id=uid, group_id=g) for g in set(group_ids)])


async def count_users(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


async def grants_for(session: AsyncSession, rtype: str, rid: uuid.UUID) -> list[ResourceGrant]:
    return list((await session.scalars(select(ResourceGrant).where(
        ResourceGrant.resource_type == rtype, ResourceGrant.resource_id == rid))).all())


async def get_group(session: AsyncSession, gid: uuid.UUID) -> Group | None:
    return await session.get(Group, gid)
