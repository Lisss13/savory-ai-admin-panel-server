"""E2E-тесты HTTP-эндпоинта `GET /api/v1/organizations`.

Покрывает только HTTP-слой:
- admin-only-контракт (без JWT → 401);
- envelope-форму ответа `{data, messages, code}` + camelCase-сериализацию
  (`organizationId`, `organizationName`, `subscriptionActive`, `restaurantsCount`);
- структуру вложенных объектов `admin` и `restaurants`.

Бизнес-правила фильтрации и расчёта `subscriptionActive` покрыты в
`test_service.py` — здесь только то, что относится к HTTP-границе.
"""

from httpx import AsyncClient

from .conftest import (
    OrganizationFactory,
    RestaurantFactory,
    SubscriptionFactory,
    UserFactory,
)

# ---------- авторизация ----------


async def test_list_requires_admin_auth(client: AsyncClient):
    """GET /organization без JWT → 401 (admin-only endpoint)."""
    resp = await client.get("/api/v1/organizations")
    assert resp.status_code == 401


async def test_list_rejects_invalid_bearer(client: AsyncClient):
    """Мусорный Bearer-токен → 401, без падения в 500."""
    resp = await client.get(
        "/api/v1/organizations",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------- envelope + camelCase ----------


async def test_list_returns_envelope_with_camelcase_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Ответ обёрнут в `{data, messages, code}`, поля сериализованы в camelCase."""
    admin = await make_user(name="Boss", email="boss@acme.ae", phone="+971555000111")
    org = await make_organization(name="Acme Corp", phone="+971500001111", admin_id=admin.id)
    await make_restaurant(name="Main", organization_id=org.id)
    await make_subscription(organization_id=org.id)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1

    item = body["data"][0]
    expected_top_camel = {"id", "name", "phone", "admin", "restaurants", "restaurantsCount"}
    assert expected_top_camel.issubset(item.keys())
    assert "restaurants_count" not in item

    assert item["name"] == "Acme Corp"
    assert item["phone"] == "+971500001111"
    assert item["restaurantsCount"] == 1


async def test_admin_subobject_camelcase(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
):
    """`admin` сериализуется как `{id, name, phone, email}` (без snake_case-полей)."""
    admin = await make_user(name="Boss", email="boss@acme.ae", phone="+971555000111")
    await make_organization(admin_id=admin.id)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    admin_json = resp.json()["data"][0]["admin"]

    assert admin_json == {
        "id": admin.id,
        "name": "Boss",
        "phone": "+971555000111",
        "email": "boss@acme.ae",
    }


async def test_restaurants_subobjects_camelcase(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Каждый ресторан внутри `restaurants` имеет camelCase-поля и булев `subscriptionActive`."""
    org = await make_organization(name="Acme Corp")
    await make_restaurant(name="Main", organization_id=org.id)
    await make_subscription(organization_id=org.id)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    rest = resp.json()["data"][0]["restaurants"][0]

    expected_camel = {
        "id",
        "name",
        "organizationId",
        "organizationName",
        "subscriptionActive",
        "isActive",
    }
    assert expected_camel.issubset(rest.keys())
    for snake in ("organization_id", "organization_name", "subscription_active", "is_active"):
        assert snake not in rest

    assert rest["name"] == "Main"
    assert rest["organizationName"] == "Acme Corp"
    assert rest["organizationId"] == org.id
    assert isinstance(rest["subscriptionActive"], bool)
    assert rest["subscriptionActive"] is True


async def test_restaurant_is_active_field_reflects_db_state(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """`isActive` отдаётся как camelCase-bool: True для работающих, False для выключенных."""
    org = await make_organization()
    await make_restaurant(name="on", organization_id=org.id, is_active=True)
    await make_restaurant(name="off", organization_id=org.id, is_active=False)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    by_name = {r["name"]: r for r in resp.json()["data"][0]["restaurants"]}

    assert by_name["on"]["isActive"] is True
    assert by_name["off"]["isActive"] is False


async def test_list_returns_empty_list_when_no_organizations(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Пустая БД → `data: []` (а не null) в envelope."""
    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == []


async def test_subscriptions_list_present_without_top_level_count(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """На верхнем уровне есть список `subscriptions`; `subscriptionsCount`
    больше нет — счётчик "ресторанов в подписке" живёт внутри каждой подписки."""
    org = await make_organization()
    await make_subscription(organization_id=org.id)
    await make_subscription(organization_id=org.id)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    item = resp.json()["data"][0]

    assert "subscriptions" in item
    assert "subscriptionsCount" not in item
    assert "subscriptions_count" not in item
    assert len(item["subscriptions"]) == 2


async def test_subscriptions_subobjects_camelcase(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Каждая подписка — `{id, endDate, isActive, restaurantsCount}` (camelCase)."""
    org = await make_organization()
    await make_subscription(organization_id=org.id, is_active=True, restaurant_limit=5)

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    sub = resp.json()["data"][0]["subscriptions"][0]

    assert set(sub.keys()) == {"id", "endDate", "isActive", "restaurantsCount"}
    for snake in ("end_date", "is_active", "restaurants_count"):
        assert snake not in sub
    assert isinstance(sub["endDate"], str)  # ISO datetime сериализуется в строку
    assert isinstance(sub["isActive"], bool)
    assert sub["isActive"] is True
    assert sub["restaurantsCount"] == 5


# ---------- пагинация (query-параметры) ----------


async def test_pagination_query_params_truncate_result(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
):
    """`?limit=2&offset=0` — первые две орг по `id ASC`."""
    first = await make_organization()
    second = await make_organization()
    await make_organization()

    resp = await client.get("/api/v1/organizations?limit=2&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert [r["id"] for r in data] == [first.id, second.id]


async def test_pagination_query_params_offset_skips(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
):
    """`?offset=2` — пропускает первые два."""
    await make_organization()
    await make_organization()
    third = await make_organization()

    resp = await client.get("/api/v1/organizations?limit=10&offset=2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert [r["id"] for r in data] == [third.id]


async def test_pagination_rejects_limit_over_max(client: AsyncClient, auth_headers: dict[str, str]):
    """`limit > 100` запрещён валидацией (`PaginationParamsM.limit: le=100`)."""
    resp = await client.get("/api/v1/organizations?limit=101", headers=auth_headers)
    assert 400 <= resp.status_code < 500


async def test_pagination_rejects_negative_offset(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """`offset < 0` запрещён валидацией (`ge=0`)."""
    resp = await client.get("/api/v1/organizations?offset=-1", headers=auth_headers)
    assert 400 <= resp.status_code < 500


async def test_pagination_rejects_zero_limit(client: AsyncClient, auth_headers: dict[str, str]):
    """`limit=0` запрещён (`ge=1`)."""
    resp = await client.get("/api/v1/organizations?limit=0", headers=auth_headers)
    assert 400 <= resp.status_code < 500
