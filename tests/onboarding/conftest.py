"""Фикстуры для тестов модуля onboarding.

Общие для всех файлов (`test_router.py`, `test_service.py`) — заведение
админа + Bearer-токен и фабрика заявок `make_request`.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import OnboardingRequests

RequestFactory = Callable[..., Awaitable[OnboardingRequests]]


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="ob-admin@savory.ai",
        password="topsecret",
        name="OnboardingAdmin",
    )
    await db_session.commit()
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ob-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def make_request(db_session: AsyncSession) -> RequestFactory:
    """Фабрика онбординг-заявок для тестов.

    `updated_at` сдвигается на минуту назад для каждого следующего вызова —
    чтобы порядок создания совпадал с порядком сортировки `updated_at DESC`.
    """
    counter = {"n": 0}

    async def _factory(
        *,
        name: str = "John",
        phone: str = "+1234567890",
        email: str = "john@example.com",
        status: str = "new",
        deleted_at: datetime | None = None,
        updated_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> OnboardingRequests:
        idx = counter["n"]
        counter["n"] += 1
        now = datetime.now(tz=UTC)
        upd = updated_at or now - timedelta(minutes=idx)
        cr = created_at or upd - timedelta(hours=1)

        req = OnboardingRequests(
            name=f"{name}-{idx}",
            phone=phone,
            email=email,
            status=status,
            created_at=cr,
            updated_at=upd,
            deleted_at=deleted_at,
        )
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)
        return req

    return _factory
