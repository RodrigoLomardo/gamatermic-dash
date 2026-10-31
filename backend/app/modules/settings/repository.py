import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import SystemSetting


async def get(session: AsyncSession, key: str) -> SystemSetting | None:
    return await session.get(SystemSetting, key)


async def upsert(session: AsyncSession, key: str, value: dict, updated_by: uuid.UUID | None) -> SystemSetting:
    row = await session.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value, updated_by=updated_by)
        session.add(row)
    else:
        row.value = value
        row.updated_by = updated_by
    return row


async def set_secret(session: AsyncSession, key: str, ciphertext: bytes | None, updated_by: uuid.UUID | None) -> SystemSetting:
    row = await session.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value={}, updated_by=updated_by)
        session.add(row)
    row.secret_ciphertext = ciphertext
    row.updated_by = updated_by
    return row
