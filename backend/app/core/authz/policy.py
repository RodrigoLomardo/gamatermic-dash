"""Servico central de politica: RBAC com escopo (all|granted) + concessoes por recurso/setor."""
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.catalog import LEVELS
from app.core.db import utcnow
from app.core.errors import Forbidden
from app.modules.iam.models import (
    GroupRole,
    Permission,
    ResourceGrant,
    Role,
    RolePermission,
    User,
    UserGroup,
    UserRole,
)

CACHE_TTL = 60.0
_cache: dict[uuid.UUID, tuple[float, int, "Principal"]] = {}


def clear_cache() -> None:
    _cache.clear()


@dataclass
class Principal:
    typ: str  # user | device
    id: uuid.UUID
    label: str = ""
    perms: dict[str, str] = field(default_factory=dict)  # permissao -> escopo efetivo (all vence granted)
    role_ids: set[uuid.UUID] = field(default_factory=set)
    role_names: list[str] = field(default_factory=list)
    group_ids: set[uuid.UUID] = field(default_factory=set)
    authz_version: int = 0
    must_change_password: bool = False
    session_id: str | None = None
    playlist_id: uuid.UUID | None = None  # devices

    def scope(self, perm: str) -> str | None:
        return self.perms.get(perm)

    def has(self, perm: str) -> bool:
        return perm in self.perms


async def load_user_principal(session: AsyncSession, user: User, *, use_cache: bool = True) -> Principal:
    hit = _cache.get(user.id)
    if use_cache and hit and time.monotonic() - hit[0] < CACHE_TTL and hit[1] == user.authz_version:
        p = hit[2]
        p.must_change_password = user.must_change_password
        return p
    group_ids = set((await session.scalars(select(UserGroup.group_id).where(UserGroup.user_id == user.id))).all())
    role_ids = set((await session.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id))).all())
    if group_ids:
        role_ids |= set((await session.scalars(select(GroupRole.role_id).where(GroupRole.group_id.in_(group_ids)))).all())
    perms: dict[str, str] = {}
    names: list[str] = []
    if role_ids:
        names = list((await session.scalars(select(Role.name).where(Role.id.in_(role_ids)).order_by(Role.name))).all())
        rows = (
            await session.execute(
                select(Permission.code, RolePermission.scope)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id.in_(role_ids))
            )
        ).all()
        for code, scope in rows:
            if perms.get(code) != "all":
                perms[code] = scope
    p = Principal(
        typ="user", id=user.id, label=user.email, perms=perms, role_ids=role_ids, role_names=names,
        group_ids=group_ids, authz_version=user.authz_version, must_change_password=user.must_change_password,
    )
    _cache[user.id] = (time.monotonic(), user.authz_version, p)
    return p


async def _grant_rows(session: AsyncSession, p: Principal, rtypes: list[str]) -> list[ResourceGrant]:
    subj = [ResourceGrant.subject_type == "user"]
    conds = [(ResourceGrant.subject_type == "user") & (ResourceGrant.subject_id == p.id)]
    if p.group_ids:
        conds.append((ResourceGrant.subject_type == "group") & (ResourceGrant.subject_id.in_(p.group_ids)))
    if p.role_ids:
        conds.append((ResourceGrant.subject_type == "role") & (ResourceGrant.subject_id.in_(p.role_ids)))
    del subj
    q = select(ResourceGrant).where(
        or_(*conds),
        ResourceGrant.resource_type.in_(rtypes),
        or_(ResourceGrant.expires_at.is_(None), ResourceGrant.expires_at > utcnow()),
    )
    return list((await session.scalars(q)).all())


def _best(grants: list[ResourceGrant], rtype: str, rid: uuid.UUID | None, sector_id: uuid.UUID | None) -> int:
    best = 0
    for g in grants:
        direct = g.resource_type == rtype and rid is not None and g.resource_id == rid
        via_sector = g.resource_type == "sector" and sector_id is not None and g.resource_id == sector_id
        if direct or via_sector:
            best = max(best, LEVELS[g.access_level])
    return best


async def can(
    session: AsyncSession, p: Principal, perm: str, rtype: str, rid: uuid.UUID | None,
    sector_id: uuid.UUID | None, level: str = "view",
) -> bool:
    scope = p.scope(perm)
    if scope is None:
        return False
    if scope == "all":
        return True
    grants = await _grant_rows(session, p, [rtype, "sector"])
    return _best(grants, rtype, rid, sector_id) >= LEVELS[level]


async def require_can(
    session: AsyncSession, p: Principal, perm: str, rtype: str, rid: uuid.UUID | None,
    sector_id: uuid.UUID | None, level: str = "view",
) -> None:
    if not await can(session, p, perm, rtype, rid, sector_id, level):
        raise Forbidden("Sem permissão para este recurso.")


async def accessible(
    session: AsyncSession, p: Principal, perm: str, rtype: str, level: str = "view"
) -> tuple[bool, set[uuid.UUID], set[uuid.UUID]]:
    """(todos?, ids diretos, ids de setores). Para filtrar listagens no repositorio."""
    scope = p.scope(perm)
    if scope is None:
        return False, set(), set()
    if scope == "all":
        return True, set(), set()
    grants = await _grant_rows(session, p, [rtype, "sector"])
    need = LEVELS[level]
    direct = {g.resource_id for g in grants if g.resource_type == rtype and LEVELS[g.access_level] >= need}
    sectors = {g.resource_id for g in grants if g.resource_type == "sector" and LEVELS[g.access_level] >= need}
    return False, direct, sectors


def max_assignable_check(actor: Principal, target_perms: dict[str, str]) -> None:
    """Anti-escalonamento: ninguem concede permissao/escopo que nao possui (exceto Administrador)."""
    if "Administrador" in actor.role_names:
        return
    for code, scope in target_perms.items():
        mine = actor.scope(code)
        if mine is None or (mine == "granted" and scope == "all"):
            raise Forbidden(f"Você não pode atribuir a permissão '{code}' com esse escopo.", code="privilege_escalation")
