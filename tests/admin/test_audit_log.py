"""Тесты записи попыток входа в `admin_login_log`."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.models import AdminLoginLog


@pytest.fixture
async def seeded_admin(db_session: AsyncSession):
    admin = await service.create_admin(
        db_session,
        email="boss@savory.ai",
        password="topsecret",
        name="Boss",
    )
    await db_session.commit()
    return admin


async def test_successful_login_is_logged(
    client: AsyncClient, seeded_admin, db_session: AsyncSession
):
    """Успешный логин создаёт запись `success=true` с admin_id и IP."""
    r = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )
    assert r.status_code == 200

    res = await db_session.execute(select(AdminLoginLog))
    logs = res.scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.success is True
    assert log.email == "boss@savory.ai"
    assert log.admin_id == seeded_admin.id
    assert log.failure_reason is None


async def test_failed_login_is_logged_with_reason(
    client: AsyncClient, seeded_admin, db_session: AsyncSession
):
    """Неудачный логин записывается с `success=false` и причиной."""
    await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "WRONG"},
    )

    res = await db_session.execute(select(AdminLoginLog))
    logs = res.scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.success is False
    assert log.email == "boss@savory.ai"
    assert log.failure_reason == "invalid_credentials"


async def test_login_for_unknown_email_is_logged(client: AsyncClient, db_session: AsyncSession):
    """Попытка с неизвестным email тоже попадает в журнал — без `admin_id`."""
    await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ghost@savory.ai", "password": "irrelevant"},
    )

    res = await db_session.execute(select(AdminLoginLog))
    logs = res.scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.success is False
    assert log.admin_id is None
    assert log.email == "ghost@savory.ai"
    assert log.failure_reason == "invalid_credentials"
