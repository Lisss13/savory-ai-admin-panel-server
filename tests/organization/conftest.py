"""Фикстуры для тестов модуля organization.

`get_organizations` собирает данные из 4 таблиц (`organizations`, `users`,
`restaurants`, `subscriptions`) + правила фильтрации (soft-delete) и
производит `subscription_active` по тем же условиям, что и
`restaurants/service.py`.

В отличие от `tests/restaurants/conftest.py`, тут нужен **`make_user`** —
у каждой организации в выдаче возвращается её собственный админ (`Users`),
и тесты должны различать админов между орг.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import Organizations, Restaurants, Subscriptions, Users

UserFactory = Callable[..., Awaitable[Users]]
OrganizationFactory = Callable[..., Awaitable[Organizations]]
RestaurantFactory = Callable[..., Awaitable[Restaurants]]
SubscriptionFactory = Callable[..., Awaitable[Subscriptions]]


# ---------- auth ----------


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="org-admin@savory.ai",
        password="topsecret",
        name="OrganizationsAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "org-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- доменные фабрики ----------


@pytest.fixture
def make_user(db_session: AsyncSession) -> UserFactory:
    """Фабрика пользователей. `email` уникален по индексу — генерим из счётчика."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str = "+971500000000",
        company: str = "Acme",
        deleted_at: datetime | None = None,
    ) -> Users:
        idx = counter["n"]
        counter["n"] += 1
        user = Users(
            name=name or f"User #{idx}",
            email=email or f"user-{idx}@example.com",
            phone=phone,
            company=company,
            password="hashed",
            deleted_at=deleted_at,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _factory


@pytest.fixture
def make_organization(db_session: AsyncSession, make_user: UserFactory) -> OrganizationFactory:
    """Фабрика организаций. Если `admin_id` не передан — создаётся новый юзер-админ."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        phone: str = "+971500000000",
        admin_id: int | None = None,
        deleted_at: datetime | None = None,
    ) -> Organizations:
        idx = counter["n"]
        counter["n"] += 1
        if admin_id is None:
            admin = await make_user()
            admin_id = admin.id
        org = Organizations(
            name=name or f"Org #{idx}",
            phone=phone,
            admin_id=admin_id,
            deleted_at=deleted_at,
        )
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        return org

    return _factory


@pytest.fixture
def make_restaurant(
    db_session: AsyncSession, make_organization: OrganizationFactory
) -> RestaurantFactory:
    """Фабрика ресторанов. Если `organization_id` не передан — создаётся новая орг."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        organization_id: int | None = None,
        address: str = "Dubai",
        phone: str = "+971500000000",
        is_active: bool = True,
        deleted_at: datetime | None = None,
        # Postgres-defaults сброшены в tests/conftest.py — в SQLite задаём явно.
        table_turnover_minutes: int = 15,
        slot_interval: int = 30,
        ordering_enabled: bool = False,
    ) -> Restaurants:
        idx = counter["n"]
        counter["n"] += 1
        if organization_id is None:
            org = await make_organization()
            organization_id = org.id
        restaurant = Restaurants(
            name=name or f"Restaurant #{idx}",
            organization_id=organization_id,
            address=address,
            phone=phone,
            is_active=is_active,
            deleted_at=deleted_at,
            table_turnover_minutes=table_turnover_minutes,
            slot_interval=slot_interval,
            ordering_enabled=ordering_enabled,
        )
        db_session.add(restaurant)
        await db_session.commit()
        await db_session.refresh(restaurant)
        return restaurant

    return _factory


@pytest.fixture
def make_subscription(db_session: AsyncSession) -> SubscriptionFactory:
    """Фабрика подписок. По умолчанию — активная (end_date в будущем, is_active=True)."""

    async def _factory(
        *,
        organization_id: int,
        period: int = 1,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        is_active: bool = True,
        deleted_at: datetime | None = None,
        restaurant_limit: int = 1,
    ) -> Subscriptions:
        now = datetime.now(tz=UTC)
        subscription = Subscriptions(
            organization_id=organization_id,
            period=period,
            start_date=start_date or now - timedelta(days=30),
            end_date=end_date or now + timedelta(days=30),
            is_active=is_active,
            deleted_at=deleted_at,
            restaurant_limit=restaurant_limit,
        )
        db_session.add(subscription)
        await db_session.commit()
        await db_session.refresh(subscription)
        return subscription

    return _factory
