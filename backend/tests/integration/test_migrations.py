import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import TEST_DB

BACKEND = Path(__file__).resolve().parents[2]


def _alembic(*args):
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, capture_output=True, text=True,
                          env={**os.environ, "ALEMBIC_DATABASE_URL": TEST_DB})


def test_no_schema_drift_between_models_and_migrations():
    r = _alembic("check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_downgrade_and_upgrade_roundtrip_on_scratch_db():
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    scratch = TEST_DB.rsplit("/", 1)[0] + "/gamatermic_scratch"

    async def recreate():
        e = create_async_engine(TEST_DB.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
        async with e.connect() as c:
            await c.execute(text("DROP DATABASE IF EXISTS gamatermic_scratch"))
            await c.execute(text("CREATE DATABASE gamatermic_scratch"))
        await e.dispose()

    asyncio.run(recreate())
    env = {**os.environ, "ALEMBIC_DATABASE_URL": scratch}
    for args in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
