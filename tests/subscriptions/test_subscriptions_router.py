"""HTTP-тесты `/api/v1/subscriptions/*` — только list + create.

Покрывают:
- envelope `{data, messages, code}` + camelCase;
- фильтры (`organizationId`, `isActive`, `expired`) и пагинацию;
- create + инвариант «≤ 1 активной» (деактивация существующей при `isActive=true`);
- AdminLog с `X-Forwarded-For` → `ip_address`.

Admin-only auth — отдельный параметризованный тест в `test_auth.py`.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log.models import AdminLogs

from .conftest import (
    OrganizationFactory,
    RestaurantFactory,
    SubscriptionFactory,
)

# ---------- envelope + контракт ----------


async def test_list_returns_envelope_with_camel_case(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_restaurant: RestaurantFactory,
):
    """Ответ списка — envelope, поля в camelCase, агрегаты по ресторанам считаются."""
    org = await make_organization()
    await make_subscription(organization_id=org.id, restaurant_limit=5)
    await make_restaurant(organization_id=org.id, is_active=True)
    await make_restaurant(organization_id=org.id, is_active=False)

    resp = await client.get("/api/v1/subscriptions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200 and body["messages"] == []

    data = body["data"]
    # PaginatedResponse — {items, total, limit, offset}; дефолт limit=10, offset=0.
    assert data["total"] == 1 and data["limit"] == 10 and data["offset"] == 0
    item = data["items"][0]
    assert item["organization"]["id"] == org.id
    assert item["restaurantLimit"] == 5
    assert item["totalRestaurants"] == 2
    assert item["activeRestaurants"] == 1
    assert item["isActive"] is True
    assert item["isExpired"] is False
    assert isinstance(item["daysLeft"], int)


# ---------- фильтры ----------


async def test_list_filters_by_organization_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`organizationId` изолирует выдачу одной организации."""
    org_a = await make_organization()
    org_b = await make_organization()
    await make_subscription(organization_id=org_a.id)
    await make_subscription(organization_id=org_b.id)

    resp = await client.get(
        f"/api/v1/subscriptions?organizationId={org_a.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1 and items[0]["organization"]["id"] == org_a.id


async def test_list_filters_by_is_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`isActive=false` отдаёт только неактивные."""
    org_a = await make_organization()
    org_b = await make_organization()
    await make_subscription(organization_id=org_a.id, is_active=True)
    await make_subscription(organization_id=org_b.id, is_active=False)

    resp = await client.get("/api/v1/subscriptions?isActive=false", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1 and items[0]["isActive"] is False


async def test_list_filters_by_expired(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`expired=true` отдаёт только истёкшие (endDate < now)."""
    now = datetime.now(UTC)
    org_a = await make_organization()
    org_b = await make_organization()
    await make_subscription(
        organization_id=org_a.id,
        start_date=now - timedelta(days=60),
        end_date=now - timedelta(days=1),
    )
    await make_subscription(
        organization_id=org_b.id,
        start_date=now - timedelta(days=10),
        end_date=now + timedelta(days=10),
    )

    resp = await client.get("/api/v1/subscriptions?expired=true", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1 and items[0]["organization"]["id"] == org_a.id
    assert items[0]["isExpired"] is True


async def test_list_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`limit=1&offset=1` отдаёт ровно одну запись и сохраняет реальный `total`."""
    org = await make_organization()
    for _ in range(3):
        await make_subscription(organization_id=org.id)

    resp = await client.get("/api/v1/subscriptions?limit=1&offset=1", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["limit"] == 1 and data["offset"] == 1 and data["total"] == 3
    assert len(data["items"]) == 1


async def test_list_excludes_soft_deleted(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписки с `deleted_at IS NOT NULL` не попадают в list."""
    org = await make_organization()
    await make_subscription(organization_id=org.id)
    await make_subscription(organization_id=org.id, deleted_at=datetime.now(UTC))

    resp = await client.get("/api/v1/subscriptions", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["data"]["total"] == 1


# ---------- create ----------


async def test_create_returns_201_and_deactivates_existing_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    db_session: AsyncSession,
):
    """POST с `isActive=true` (default) деактивирует существующую активную у орг."""
    org = await make_organization()
    old_sub = await make_subscription(organization_id=org.id, is_active=True)

    resp = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"organizationId": org.id, "period": 12, "restaurantLimit": 5},
    )
    assert resp.status_code == 201
    item = resp.json()["data"]
    assert item["isActive"] is True
    assert item["period"] == 12
    assert item["restaurantLimit"] == 5

    await db_session.refresh(old_sub)
    assert old_sub.is_active is False


async def test_create_with_is_active_false_keeps_existing_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    db_session: AsyncSession,
):
    """POST с явным `isActive=false` не трогает существующую активную."""
    org = await make_organization()
    old_sub = await make_subscription(organization_id=org.id, is_active=True)

    resp = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"organizationId": org.id, "period": 6, "isActive": False},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["isActive"] is False

    await db_session.refresh(old_sub)
    assert old_sub.is_active is True


async def test_create_on_missing_organization_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """POST на несуществующую орг → 404 OrganizationNotFound."""
    resp = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"organizationId": 9999, "period": 12},
    )
    assert resp.status_code == 404


# ---------- AdminLog: IP ----------


async def test_create_logs_x_forwarded_for_into_ip_address(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """X-Forwarded-For прокидывается в `admin_logs.ip_address`."""
    org = await make_organization()
    headers = {**auth_headers, "X-Forwarded-For": "203.0.113.42, 10.0.0.1"}
    resp = await client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={"organizationId": org.id, "period": 1},
    )
    assert resp.status_code == 201
    sub_id = resp.json()["data"]["id"]

    log = (
        await db_session.execute(
            select(AdminLogs).where(
                AdminLogs.entity_type == "subscription", AdminLogs.entity_id == sub_id
            )
        )
    ).scalar_one()
    assert log.action == "create"
    assert log.ip_address == "203.0.113.42"
