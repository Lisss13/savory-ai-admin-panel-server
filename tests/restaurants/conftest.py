"""Фикстуры для тестов модуля restaurants.

`list_restaurants` собирает данные из 5 таблиц (`organizations`, `restaurants`,
`tables`, `subscriptions`, `ai_request_logs`) + правила фильтрации
(soft-delete, `is_active`, `end_date >= now`, AI-логи только текущего месяца).
Поэтому фабрик много, и они принимают почти все поля как kwargs — иначе
один общий тест на 8 строк не сможет создать кейс "подписка истекла вчера".

`admin_user` нужен, потому что `Organizations.admin_id` — NOT NULL FK
на `users`. Один общий админ-пользователь на тест-сессии достаточно.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import (
    AiRequestLogs,
    Organizations,
    Restaurants,
    Subscriptions,
    Tables,
    Users,
)

OrganizationFactory = Callable[..., Awaitable[Organizations]]
RestaurantFactory = Callable[..., Awaitable[Restaurants]]
TableFactory = Callable[..., Awaitable[Tables]]
SubscriptionFactory = Callable[..., Awaitable[Subscriptions]]
AiLogFactory = Callable[..., Awaitable[AiRequestLogs]]


# ---------- auth ----------


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="rest-admin@savory.ai",
        password="topsecret",
        name="RestaurantsAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "rest-admin@savory.ai", "password": "topsecret"},
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
        email="owner@acme.ae",
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
        # Эти Postgres-defaults сброшены в conftest.py, поэтому в SQLite
        # их нужно задать явно — иначе NOT NULL constraint:
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
def make_table(db_session: AsyncSession) -> TableFactory:
    """Фабрика столиков. Принимает обязательный `restaurant_id`."""
    counter = {"n": 0}

    async def _factory(
        *,
        restaurant_id: int,
        name: str | None = None,
        guest_count: int = 2,
        deleted_at: datetime | None = None,
    ) -> Tables:
        idx = counter["n"]
        counter["n"] += 1
        table = Tables(
            restaurant_id=restaurant_id,
            name=name or f"Table #{idx}",
            guest_count=guest_count,
            deleted_at=deleted_at,
        )
        db_session.add(table)
        await db_session.commit()
        await db_session.refresh(table)
        return table

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


@pytest.fixture
def make_ai_log(db_session: AsyncSession) -> AiLogFactory:
    """Фабрика AI-логов. По умолчанию — `created_at = now` (попадает в "текущий месяц")."""

    async def _factory(
        *,
        restaurant_id: int,
        session_id: int = 1,
        created_at: datetime | None = None,
        deleted_at: datetime | None = None,
    ) -> AiRequestLogs:
        log = AiRequestLogs(
            restaurant_id=restaurant_id,
            session_id=session_id,
            created_at=created_at or datetime.now(tz=UTC),
            deleted_at=deleted_at,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)
        return log

    return _factory
