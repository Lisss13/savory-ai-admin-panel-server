"""Тесты rate-limit для `/admin/auth/login`.

После N неудачных попыток на один email — 429, дальнейшие попытки
блокируются до окончания lockout-окна. Успешный логин сбрасывает счётчик.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.config import admin_settings


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


async def test_login_returns_429_after_too_many_failures(client: AsyncClient, seeded_admin):
    """После `login_max_attempts` промахов на один email — 429."""
    for _ in range(admin_settings.login_max_attempts):
        r = await client.post(
            "/api/v1/admin/auth/login",
            json={"email": "boss@savory.ai", "password": "WRONG"},
        )
        assert r.status_code == 401

    # Следующая попытка — даже с правильным паролем — 429.
    r = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == 429


async def test_login_rate_limit_is_per_email(client: AsyncClient, db_session: AsyncSession):
    """Лимит изолирован по email: блокировка одного не блокирует другого."""
    await service.create_admin(db_session, email="a@savory.ai", password="pwd", name="A")
    await service.create_admin(db_session, email="b@savory.ai", password="pwd", name="B")
    await db_session.commit()

    for _ in range(admin_settings.login_max_attempts):
        await client.post(
            "/api/v1/admin/auth/login",
            json={"email": "a@savory.ai", "password": "WRONG"},
        )

    # `a@` — заблокирован, `b@` должен спокойно залогиниться.
    r = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "b@savory.ai", "password": "pwd"},
    )
    assert r.status_code == 200


async def test_successful_login_resets_rate_limit_counter(client: AsyncClient, seeded_admin):
    """После успешного логина счётчик неудач для этого email обнуляется."""
    # На 1 меньше лимита промахов.
    for _ in range(admin_settings.login_max_attempts - 1):
        await client.post(
            "/api/v1/admin/auth/login",
            json={"email": "boss@savory.ai", "password": "WRONG"},
        )

    # Успешный логин сбрасывает счётчик.
    r = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )
    assert r.status_code == 200

    # Снова можно промахнуться `login_max_attempts - 1` раз, не получая 429.
    for _ in range(admin_settings.login_max_attempts - 1):
        r = await client.post(
            "/api/v1/admin/auth/login",
            json={"email": "boss@savory.ai", "password": "WRONG"},
        )
        assert r.status_code == 401  # не 429
