"""E2E-тесты HTTP-эндпоинтов `/admin/auth/login` и `/admin/auth/me`."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.config import admin_settings


@pytest.fixture
async def seeded_admin(db_session: AsyncSession):
    """Готовый админ в БД: `boss@savory.ai` / `topsecret`."""
    admin = await service.create_admin(
        db_session,
        email="boss@savory.ai",
        password="topsecret",
        name="Boss",
    )
    await db_session.commit()
    return admin


async def test_login_returns_token_envelope(client: AsyncClient, seeded_admin):
    """Корректные креды → 200 + JWT в envelope."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []

    data = body["data"]
    assert data["tokenType"] == "bearer"
    assert isinstance(data["accessToken"], str) and data["accessToken"]
    assert data["expiresIn"] > 0
    assert data["admin"]["email"] == "boss@savory.ai"
    assert data["admin"]["name"] == "Boss"
    assert "passwordHash" not in data["admin"]


async def test_login_rejects_wrong_password(client: AsyncClient, seeded_admin):
    """Неверный пароль → 401 в envelope-формате."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "WRONG"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 401
    assert body["data"] is None
    assert body["messages"]


async def test_login_rejects_unknown_email(client: AsyncClient):
    """Неизвестный email → 401, не 404 (не раскрываем, есть ли учётка)."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ghost@x.y", "password": "irrelevant"},
    )

    assert resp.status_code == 401


async def test_login_validates_email_format(client: AsyncClient):
    """Невалидный email → 400 от валидатора."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "not-an-email", "password": "x"},
    )

    assert resp.status_code == 400


async def test_me_returns_admin_with_valid_token(client: AsyncClient, seeded_admin):
    """`/me` с валидным Bearer-токеном → текущий админ."""
    login = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )
    token = login.json()["data"]["accessToken"]

    resp = await client.get(
        "/api/v1/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["email"] == "boss@savory.ai"
    assert body["data"]["id"] == seeded_admin.id


async def test_me_rejects_request_without_token(client: AsyncClient):
    """`/me` без заголовка `Authorization` → 401."""
    resp = await client.get("/api/v1/admin/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_invalid_token(client: AsyncClient):
    """`/me` с мусорным токеном → 401."""
    resp = await client.get(
        "/api/v1/admin/auth/me",
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert resp.status_code == 401


async def test_me_rejects_token_for_missing_admin(client: AsyncClient):
    """Подписанный нашим секретом токен, но `sub` ссылается на несуществующего админа → 401."""
    token = jwt.encode(
        {
            "sub": "999999",
            "exp": int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp()),
        },
        admin_settings.jwt_secret,
        algorithm=admin_settings.jwt_algorithm,
    )
    resp = await client.get(
        "/api/v1/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


async def test_me_rejects_token_for_inactive_admin(
    client: AsyncClient, seeded_admin, db_session: AsyncSession
):
    """Деактивированный админ не должен проходить по своему токену."""
    login = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "boss@savory.ai", "password": "topsecret"},
    )
    token = login.json()["data"]["accessToken"]

    seeded_admin.is_active = False
    await db_session.commit()

    resp = await client.get(
        "/api/v1/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
