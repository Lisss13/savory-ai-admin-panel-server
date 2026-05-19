"""Фикстуры для тестов модуля dashboard.

`calculate_app_stats` агрегирует count'ы по трём таблицам — `organizations`,
`restaurants`, `subscriptions` — с фильтром `deleted_at IS NULL`. Поэтому
нужны фабрики этих сущностей плюс админ-пользователь как FK-таргет
для `Organizations.admin_id` (NOT NULL).

Дублируем фабрики локально (а не импортируем из `tests/restaurants/conftest.py`),
чтобы тестовые модули оставались независимыми — иначе изменение чужого
conftest незаметно ломает наши тесты.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import Organizations, Restaurants, Subscriptions, Users

OrganizationFactory = Callable[..., Awaitable[Organizations]]
RestaurantFactory = Callable[..., Awaitable[Restaurants]]
SubscriptionFactory = Callable[..., Awaitable[Subscriptions]]


# ---------- auth ----------


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="dashboard-admin@savory.ai",
        password="topsecret",
        name="DashboardAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "dashboard-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- доменные фабрики ----------


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> Users:
    """Пользователь-владелец организации (`Organizations.admin_id` — NOT NULL FK)."""
    user = Users(
        name="Org Owner",
        company="Acme",
        email="owner@dashboard.ae",
        phone="+971500000000",
        password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def make_organization(db_session: AsyncSession, owner_user: Users) -> OrganizationFactory:
    """Фабрика организаций. `admin_id` по умолчанию указывает на `owner_user`."""
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
        org = Organizations(
            name=name or f"Org #{idx}",
            phone=phone,
            admin_id=admin_id if admin_id is not None else owner_user.id,
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
        # Postgres-defaults сброшены в `tests/conftest.py` — задаём явно для SQLite.
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
    """Фабрика подписок. По умолчанию — `is_active=True`, неистёкшая.

    Для dashboard'а активность/просрочка значения не имеют (считаем все
    подписки, кроме soft-deleted), но удобно иметь живой кейс по умолчанию.
    """

    async def _factory(
        *,
        organization_id: int,
        period: int = 1,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        is_active: bool = True,
        deleted_at: datetime | None = None,
    ) -> Subscriptions:
        now = datetime.now(tz=UTC)
        subscription = Subscriptions(
            organization_id=organization_id,
            period=period,
            start_date=start_date or now - timedelta(days=30),
            end_date=end_date or now + timedelta(days=30),
            is_active=is_active,
            deleted_at=deleted_at,
        )
        db_session.add(subscription)
        await db_session.commit()
        await db_session.refresh(subscription)
        return subscription

    return _factory
