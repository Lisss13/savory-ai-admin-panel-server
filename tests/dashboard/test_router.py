"""E2E-тесты HTTP-эндпоинта `GET /api/v1/dashboard`.

Покрывают:
- admin-only-контракт (без JWT → 401);
- envelope-форму ответа;
- набор полей в `data` и их типы;
- соответствие значений данным в БД.

Бизнес-правила (что считается, что исключается soft-delete) — в `test_service.py`.
Здесь — только HTTP-слой.
"""

from datetime import UTC, datetime

from httpx import AsyncClient

from .conftest import OrganizationFactory, RestaurantFactory, SubscriptionFactory

# ---------- авторизация ----------


async def test_get_stats_requires_admin_auth(client: AsyncClient):
    """GET /dashboard без JWT → 401 (admin-only endpoint)."""
    resp = await client.get("/api/v1/dashboard")
    assert resp.status_code == 401


async def test_get_stats_rejects_invalid_bearer(client: AsyncClient):
    """Мусорный Bearer-токен → 401, без падения в 500."""
    resp = await client.get(
        "/api/v1/dashboard",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------- envelope + контракт полей ----------


async def test_get_stats_returns_envelope_on_empty_db(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Пустая БД → envelope `{data, messages, code}` с нулевыми счётчиками."""
    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []

    data = body["data"]
    assert data["total_organizations"] == 0
    assert data["total_restaurants"] == 0
    assert data["total_subscriptions"] == 0


async def test_get_stats_data_field_types(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
):
    """Счётчики сериализуются как `int`, не как строки."""
    await make_organization()

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert isinstance(data["total_organizations"], int)
    assert isinstance(data["total_restaurants"], int)
    assert isinstance(data["total_subscriptions"], int)


# ---------- интеграция со счётчиками ----------


async def test_get_stats_reflects_db_state_through_http(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Smoke на HTTP-слой: значения в `data` совпадают с данными в БД."""
    org_a = await make_organization()
    org_b = await make_organization()
    await make_restaurant(organization_id=org_a.id)
    await make_restaurant(organization_id=org_a.id)
    await make_restaurant(organization_id=org_b.id)
    await make_subscription(organization_id=org_a.id)
    await make_subscription(organization_id=org_b.id)

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["total_organizations"] == 2
    assert data["total_restaurants"] == 3
    assert data["total_subscriptions"] == 2


async def test_get_stats_excludes_soft_deleted_through_http(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """HTTP-уровень соблюдает фильтр `deleted_at IS NULL` для всех трёх таблиц."""
    deleted = datetime.now(tz=UTC)

    org_live = await make_organization()
    await make_organization(deleted_at=deleted)
    await make_restaurant(organization_id=org_live.id)
    await make_restaurant(organization_id=org_live.id, deleted_at=deleted)
    await make_subscription(organization_id=org_live.id)
    await make_subscription(organization_id=org_live.id, deleted_at=deleted)

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["total_organizations"] == 1
    assert data["total_restaurants"] == 1
    assert data["total_subscriptions"] == 1
