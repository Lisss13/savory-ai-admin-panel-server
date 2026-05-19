"""Фикстуры для тестов модуля subscriptions.

Фабрики намеренно дублируются (а не импортируются из `tests/dashboard/conftest.py`),
чтобы тесты оставались независимыми — изменение чужого conftest не должно
ломать наши тесты (см. соответствующий комментарий в `tests/dashboard/conftest.py`).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import (
    Organizations,
    Restaurants,
    SubscriptionExtensionRequests,
    Subscriptions,
    Users,
)

OrganizationFactory = Callable[..., Awaitable[Organizations]]
RestaurantFactory = Callable[..., Awaitable[Restaurants]]
SubscriptionFactory = Callable[..., Awaitable[Subscriptions]]
UserFactory = Callable[..., Awaitable[Users]]
ExtensionRequestFactory = Callable[..., Awaitable[SubscriptionExtensionRequests]]


# ---------- auth ----------


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Создаёт админа, логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="subscriptions-admin@savory.ai",
        password="topsecret",
        name="SubscriptionsAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "subscriptions-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- доменные фабрики ----------


@pytest.fixture
def make_user(db_session: AsyncSession) -> UserFactory:
    """Фабрика пользователей. Нужна как FK-таргет для `Organizations.admin_id`
    и `SubscriptionExtensionRequests.user_id`."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str = "+971500000000",
        company: str = "Acme",
    ) -> Users:
        idx = counter["n"]
        counter["n"] += 1
        user = Users(
            name=name or f"User #{idx}",
            company=company,
            email=email or f"user-{idx}-{id(counter)}@subs.test",
            phone=phone,
            password="hashed",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _factory


@pytest.fixture
def make_organization(db_session: AsyncSession, make_user: UserFactory) -> OrganizationFactory:
    """Фабрика организаций. `admin_id` по умолчанию указывает на новый Users."""
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
            owner = await make_user()
            admin_id = owner.id
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
    """Фабрика ресторанов. Нужна для тестов `activeRestaurants`/`totalRestaurants`."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        organization_id: int | None = None,
        address: str = "Dubai",
        phone: str = "+971500000000",
        is_active: bool = True,
        deleted_at: datetime | None = None,
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
    """Фабрика подписок. По умолчанию активна, не истекла, лимит = 1 ресторан."""

    async def _factory(
        *,
        organization_id: int,
        period: int = 1,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        is_active: bool | None = True,
        restaurant_limit: int | None = 1,
        deleted_at: datetime | None = None,
    ) -> Subscriptions:
        now = datetime.now(tz=UTC)
        subscription = Subscriptions(
            organization_id=organization_id,
            period=period,
            start_date=start_date or now - timedelta(days=30),
            end_date=end_date or now + timedelta(days=30),
            is_active=is_active,
            restaurant_limit=restaurant_limit,
            deleted_at=deleted_at,
            created_at=now,
            updated_at=now,
        )
        db_session.add(subscription)
        await db_session.commit()
        await db_session.refresh(subscription)
        return subscription

    return _factory


@pytest.fixture
def make_extension_request(db_session: AsyncSession) -> ExtensionRequestFactory:
    """Фабрика заявок на продление подписки."""

    async def _factory(
        *,
        organization_id: int,
        user_id: int,
        period: int | None = 3,
        requested_restaurant_limit: int | None = 0,
        status: str = "pending",
        admin_comment: str | None = None,
        comment: str | None = None,
        name: str = "Customer",
        phone: str = "+971500000000",
        email: str = "customer@subs.test",
        deleted_at: datetime | None = None,
    ) -> SubscriptionExtensionRequests:
        now = datetime.now(tz=UTC)
        req = SubscriptionExtensionRequests(
            organization_id=organization_id,
            user_id=user_id,
            name=name,
            phone=phone,
            email=email,
            period=period,
            requested_restaurant_limit=requested_restaurant_limit,
            comment=comment,
            status=status,
            admin_comment=admin_comment,
            created_at=now,
            updated_at=now,
            deleted_at=deleted_at,
        )
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)
        return req

    return _factory
