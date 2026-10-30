import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.definitions import DASHBOARDS, DATASETS
from app.core.authz.catalog import PERMISSIONS, SYSTEM_ROLES
from app.core.config import get_settings
from app.core.db import get_sessionmaker, utcnow
from app.core.security import hash_password, validate_password_policy
from app.modules.audit.service import ensure_partitions
from app.modules.dashboards.models import Dashboard, Widget
from app.modules.datasets import schemas as dsc
from app.modules.datasets.models import Dataset, IngestionRun, SourceBinding, UploadedFile
from app.modules.devices.models import Playlist, PlaylistItem
from app.modules.iam.models import Permission, Role, RolePermission, Sector, User, UserRole
from app.modules.ingestion.pipeline.extract import sniff_kind
from app.modules.ingestion.runner import execute_run

SECTOR = ("comercial", "Comercial (Vendas e Propostas)")


async def sync_catalog(s: AsyncSession) -> None:
    existing = {p.code: p for p in (await s.scalars(select(Permission))).all()}
    for code, desc in PERMISSIONS.items():
        if code not in existing:
            s.add(Permission(code=code, description=desc))
        else:
            existing[code].description = desc
    await s.flush()
    perm_ids = {p.code: p.id for p in (await s.scalars(select(Permission))).all()}
    roles = {r.name: r for r in (await s.scalars(select(Role))).all()}
    for name, spec in SYSTEM_ROLES.items():
        r = roles.get(name)
        if r is None:
            r = Role(name=name, description=spec["description"], is_system=True)
            s.add(r)
            await s.flush()
        r.is_system, r.description = True, spec["description"]
        current = {rp.permission_id: rp for rp in (await s.scalars(select(RolePermission).where(RolePermission.role_id == r.id))).all()}
        wanted = {perm_ids[c]: sc for c, sc in spec["permissions"].items()}
        for pid, rp in current.items():
            if pid not in wanted:
                await s.delete(rp)
            else:
                rp.scope = wanted[pid]
        for pid, sc in wanted.items():
            if pid not in current:
                s.add(RolePermission(role_id=r.id, permission_id=pid, scope=sc))
    await s.commit()


async def ensure_sector(s: AsyncSession) -> Sector:
    sec = await s.scalar(select(Sector).where(Sector.slug == SECTOR[0]))
    if sec is None:
        sec = Sector(slug=SECTOR[0], name=SECTOR[1])
        s.add(sec)
        await s.commit()
    return sec


async def ensure_admin(s: AsyncSession, email: str, password: str, name: str = "Administrador") -> User:
    validate_password_policy(password, email=email)
    u = await s.scalar(select(User).where(User.email == email.lower()))
    if u is None:
        u = User(email=email.lower(), full_name=name, password_hash=hash_password(password), status="active",
                 must_change_password=False, password_changed_at=utcnow())
        s.add(u)
        await s.flush()
    admin = await s.scalar(select(Role).where(Role.name == "Administrador"))
    if admin and not await s.scalar(select(UserRole).where(UserRole.user_id == u.id, UserRole.role_id == admin.id)):
        s.add(UserRole(user_id=u.id, role_id=admin.id))
    await s.commit()
    return u


async def seed_datasets(s: AsyncSession, sector: Sector, admin: User) -> dict[str, Dataset]:
    from fastapi import Request  # noqa: F401

    from app.modules.datasets import service as dsvc

    out: dict[str, Dataset] = {}
    for d in DATASETS:
        ds = await s.scalar(select(Dataset).where(Dataset.slug == d["slug"]))
        if ds is None:
            ds = Dataset(slug=d["slug"], name=d["name"], description=d["description"], sector_id=sector.id, load_mode=d["load_mode"],
                         time_field=d["time_field"], freshness_sla_seconds=d["freshness_sla_seconds"])
            s.add(ds)
            await s.flush()
            fields = [dsc.FieldIn(**f) for f in d["fields"]]
            await dsvc._apply_fields(s, ds, fields, {"sheet": d["sheet"], "header_row": 1})
        out[d["slug"]] = ds
    await s.commit()
    return out


async def seed_dashboards(s: AsyncSession, sector: Sector, datasets: dict[str, Dataset], admin: User) -> list[Dashboard]:
    out = []
    for d in DASHBOARDS:
        dash = await s.scalar(select(Dashboard).where(Dashboard.slug == d["slug"]))
        if dash is None:
            dash = Dashboard(slug=d["slug"], name=d["name"], description=d["description"], sector_id=sector.id,
                             default_period=d["default_period"], created_by=admin.id, updated_by=admin.id)
            s.add(dash)
            await s.flush()
            for w in d["widgets"]:
                s.add(Widget(dashboard_id=dash.id, type=w["type"], title=w["title"], x=w["x"], y=w["y"], w=w["w"], h=w["h"],
                             dataset_id=datasets[w["dataset"]].id, query_config=w["query_config"], viz_config=w["viz_config"],
                             follows_global_period=w["follows_global_period"]))
        out.append(dash)
    pl = await s.scalar(select(Playlist).where(Playlist.name == "Painel Comercial"))
    if pl is None:
        pl = Playlist(name="Painel Comercial")
        s.add(pl)
        await s.flush()
        for i, dash in enumerate(out):
            s.add(PlaylistItem(playlist_id=pl.id, dashboard_id=dash.id, position=i, duration_seconds=30))
    await s.commit()
    return out


async def import_xlsx(path: Path) -> list[dict]:
    """Carrega as abas do relatorio pelo MESMO pipeline do upload (copia o arquivo, cria run e executa)."""
    cfg = get_settings()
    kind = sniff_kind(path)
    assert kind == "xlsx", "esperado .xlsx"
    results = []
    sm = get_sessionmaker()
    Path(cfg.upload_dir).mkdir(parents=True, exist_ok=True)
    for d in DATASETS:
        stored = f"{uuid.uuid4().hex}.bin"
        shutil.copyfile(path, Path(cfg.upload_dir) / stored)
        async with sm() as s:
            ds = await s.scalar(select(Dataset).where(Dataset.slug == d["slug"]))
            assert ds is not None, "rode `bootstrap` antes"
            binding = await s.scalar(select(SourceBinding).where(SourceBinding.dataset_id == ds.id))
            f = UploadedFile(original_name=path.name, stored_path=stored, size=path.stat().st_size, sha256="import-" + stored[:16])
            s.add(f)
            await s.flush()
            run = IngestionRun(dataset_id=ds.id, data_source_id=binding.data_source_id if binding else None,
                               trigger="manual_upload", status="queued", file_id=f.id)
            s.add(run)
            await s.commit()
            rid = run.id
        await execute_run(rid)
        async with sm() as s:
            r = await s.get(IngestionRun, rid)
            results.append({"dataset": d["slug"], "status": r.status, "read": r.rows_read, "inserted": r.rows_inserted,  # type: ignore[union-attr]
                            "rejected": r.rows_rejected, "summary": r.error_summary})  # type: ignore[union-attr]
    return results


async def bootstrap(admin_email: str, admin_password: str, with_seed: bool = True) -> None:
    async with get_sessionmaker()() as s:
        await ensure_partitions(s)
        await s.commit()
        await sync_catalog(s)
        admin = await ensure_admin(s, admin_email, admin_password)
        if with_seed:
            sector = await ensure_sector(s)
            ds = await seed_datasets(s, sector, admin)
            await seed_dashboards(s, sector, ds, admin)
