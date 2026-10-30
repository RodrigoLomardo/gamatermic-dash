import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

TEST_DB = os.environ.get("GAMA_TEST_DATABASE_URL", "postgresql+asyncpg://gama@localhost:5433/gamatermic_test")
os.environ.update({
    "GAMA_ENV": "test", "GAMA_DATABASE_URL": TEST_DB, "GAMA_RUN_WORKER_INPROCESS": "false",
    "GAMA_UPLOAD_DIR": tempfile.mkdtemp(prefix="gama-uploads-"), "GAMA_RATE_LIMIT_ENABLED": "false",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.bootstrap import seed  # noqa: E402
from app.core.authz.policy import clear_cache  # noqa: E402
from app.core.db import dispose_engine, get_engine, get_sessionmaker  # noqa: E402
from app.core.rate_limit import reset_rate_limits  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.query import executor  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = "Forno-Caldeira-8842-Azul"


@pytest.fixture(scope="session", autouse=True)
def migrated():
    env = {**os.environ, "ALEMBIC_DATABASE_URL": TEST_DB}
    # recria o schema para garantir migracoes limpas
    import asyncio

    async def reset():
        from sqlalchemy.ext.asyncio import create_async_engine

        e = create_async_engine(TEST_DB)
        async with e.begin() as c:
            await c.execute(text("DROP SCHEMA public CASCADE"))
            await c.execute(text("CREATE SCHEMA public"))
        await e.dispose()

    asyncio.run(reset())
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(migrated) -> AsyncIterator[None]:
    eng = get_engine()
    async with eng.begin() as c:
        rows = (await c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'audit_logs%' AND tablename <> 'alembic_version'"))).all()
        names = ", ".join(f'"{r[0]}"' for r in rows)
        await c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        await c.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER USER"))
        await c.execute(text("DELETE FROM audit_logs"))
        await c.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER USER"))
    clear_cache()
    executor.clear_cache()
    reset_rate_limits()
    async with get_sessionmaker()() as s:
        await seed.sync_catalog(s)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Requested-With": "gamatermic"}) as c:
        yield c


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_at_end():
    yield
    await dispose_engine()


async def create_user(email: str, roles: list[str], password: str = PASSWORD, must_change: bool = False):
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.modules.iam.models import Role, User, UserRole

    async with get_sessionmaker()() as s:
        u = User(email=email, full_name=email.split("@")[0].title(), password_hash=hash_password(password), status="active",
                 must_change_password=must_change)
        s.add(u)
        await s.flush()
        for r in roles:
            rid = await s.scalar(select(Role.id).where(Role.name == r))
            s.add(UserRole(user_id=u.id, role_id=rid))
        await s.commit()
        return u.id


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin(client) -> dict:
    await create_user("admin@gama.com.br", ["Administrador"])
    return await login(client, "admin@gama.com.br")


@pytest_asyncio.fixture
async def seeded(admin):
    """Setor, datasets e dashboards de partida (sem dados)."""
    async with get_sessionmaker()() as s:
        from sqlalchemy import select

        from app.modules.iam.models import User

        adm = await s.scalar(select(User).where(User.email == "admin@gama.com.br"))
        sector = await seed.ensure_sector(s)
        ds = await seed.seed_datasets(s, sector, adm)
        dashes = await seed.seed_dashboards(s, sector, ds, adm)
        return {"sector": sector.id, "datasets": {k: v.id for k, v in ds.items()}, "dashboards": [d.id for d in dashes]}


def uid() -> str:
    return uuid.uuid4().hex[:8]
