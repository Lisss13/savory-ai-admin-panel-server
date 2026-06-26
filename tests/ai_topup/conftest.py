"""Фикстуры для тестов модуля ai_topup.

Фабрики намеренно дублируются (а не импортируются из соседних conftest),
чтобы тесты оставались независимыми — изменение чужого conftest не должно
ломать наши тесты.
"""

import decimal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.models import (
    AIRequestTopUpRequests,
    Organizations,
    Restaurants,
    Users,
)

OrganizationFactory = Callable[..., Awaitable[Organizations]]
RestaurantFactory = Callable[..., Awaitable[Restaurants]]
UserFactory = Callable[..., Awaitable[Users]]
TopUpRequestFactory = Callable[..., Awaitable[AIRequestTopUpRequests]]


# ---------- auth ----------


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Создаёт админа, логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="ai-topup-admin@savory.ai",
        password="topsecret",
        name="AiTopUpAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ai-topup-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- доменные фабрики ----------


@pytest.fixture
def make_user(db_session: AsyncSession) -> UserFactory:
    """Фабрика пользователей — FK-таргет для orgs (admin_id) и заявок (user_id)."""
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
            email=email or f"user-{idx}-{id(counter)}@topup.test",
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
    """Фабрика ресторанов — целевой ресторан докупки."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str | None = None,
        organization_id: int | None = None,
        address: str = "Dubai",
        phone: str = "+971500000000",
        is_active: bool = True,
        deleted_at: datetime | None = None,
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
            table_turnover_minutes=15,
            slot_interval=30,
            ordering_enabled=False,
        )
        db_session.add(restaurant)
        await db_session.commit()
        await db_session.refresh(restaurant)
        return restaurant

    return _factory


@pytest.fixture
def make_top_up_request(db_session: AsyncSession) -> TopUpRequestFactory:
    """Фабрика заявок на докупку AI-запросов."""

    async def _factory(
        *,
        organization_id: int,
        restaurant_id: int,
        user_id: int,
        packs_count: int = 2,
        requests_per_pack: int = 5000,
        price_per_pack: decimal.Decimal | float = decimal.Decimal("50.00"),
        currency: str = "USD",
        total_price: decimal.Decimal | float | None = None,
        comment: str = "",
        status: str = "pending",
        admin_comment: str = "",
        processed_at: datetime | None = None,
        name: str = "Customer",
        phone: str = "+971500000000",
        email: str = "customer@topup.test",
        deleted_at: datetime | None = None,
    ) -> AIRequestTopUpRequests:
        now = datetime.now(tz=UTC)
        price = decimal.Decimal(str(price_per_pack))
        total = (
            decimal.Decimal(str(total_price)) if total_price is not None else price * packs_count
        )
        req = AIRequestTopUpRequests(
            organization_id=organization_id,
            restaurant_id=restaurant_id,
            user_id=user_id,
            name=name,
            phone=phone,
            email=email,
            packs_count=packs_count,
            requests_per_pack=requests_per_pack,
            price_per_pack=price,
            currency=currency,
            total_price=total,
            comment=comment,
            status=status,
            admin_comment=admin_comment,
            processed_at=processed_at,
            created_at=now,
            updated_at=now,
            deleted_at=deleted_at,
        )
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)
        return req

    return _factory
