"""E2E-тесты HTTP-эндпоинта `GET /api/v1/restaurants`.

Покрывают:
- admin-only-контракт (без JWT → 401);
- envelope-форму ответа + camelCase-сериализацию;
- query-параметр `subscriptionActive` (алиас, не snake_case `subscription_is`);
- query-параметры `limit`/`offset` и их валидацию;
- сортировку `id ASC`.

Бизнес-правила фильтрации/подсчёта уже покрыты в `test_service.py` —
здесь проверяется именно HTTP-слой: статус-коды, имена полей в JSON,
сериализация типов (`subscriptionActive: bool`, `percentageOfUsedAiReq: float`).
"""

from httpx import AsyncClient

from app.restaurants.service import MONTHLY_AI_REQUEST_LIMIT

from .conftest import (
    AiLogFactory,
    OrganizationFactory,
    RestaurantFactory,
    SubscriptionFactory,
    TableFactory,
)

# ---------- авторизация ----------


async def test_list_requires_admin_auth(client: AsyncClient):
    """GET /restaurants без JWT → 401 (admin-only endpoint)."""
    resp = await client.get("/api/v1/restaurants")
    assert resp.status_code == 401


async def test_list_rejects_invalid_bearer(client: AsyncClient):
    """Мусорный Bearer-токен → 401, без падения в 500."""
    resp = await client.get(
        "/api/v1/restaurants",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------- envelope + camelCase ----------


async def test_list_returns_envelope_with_camelcase_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Ответ обёрнут в `{data, messages, code}`, поля сериализованы в camelCase."""
    org = await make_organization(name="Acme Corp")
    await make_restaurant(name="Main", organization_id=org.id)

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1

    item = body["data"][0]
    # Контракт воркспейса: новые поля — camelCase.
    expected_camel = {
        "id",
        "name",
        "organizationId",
        "organizationName",
        "subscriptionActive",
        "tablesCount",
        "aiRequestsLeft",
        "percentageOfUsedAiReq",
    }
    assert expected_camel.issubset(item.keys())
    # snake_case-варианты не должны попасть наружу.
    for snake in (
        "organization_id",
        "organization_name",
        "subscription_active",
        "tables_count",
        "ai_requests_left",
        "percentage_of_used_ai_req",
    ):
        assert snake not in item

    assert item["name"] == "Main"
    assert item["organizationName"] == "Acme Corp"
    assert item["organizationId"] == org.id
    # Числовые/булевы типы — не строки.
    assert isinstance(item["tablesCount"], int)
    assert isinstance(item["aiRequestsLeft"], int)
    assert isinstance(item["subscriptionActive"], bool)
    assert isinstance(item["percentageOfUsedAiReq"], float)


async def test_list_returns_empty_list_when_no_restaurants(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Без ресторанов — `data: []`, не `null`."""
    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == []


# ---------- сортировка ----------


async def test_list_orders_by_id_ascending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
):
    """Сортировка `id ASC` — наименьший `id` первым, независимо от порядка вставки."""
    first = await make_restaurant()
    second = await make_restaurant()
    third = await make_restaurant()

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    ids = [r["id"] for r in resp.json()["data"]]
    assert ids == [first.id, second.id, third.id]


# ---------- query: subscriptionActive (alias) ----------


async def test_filter_subscription_active_true_keeps_only_with_subscription(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`?subscriptionActive=true` — рестораны только с активной подпиской."""
    org_with = await make_organization(name="with-sub")
    org_without = await make_organization(name="no-sub")
    rest_with = await make_restaurant(organization_id=org_with.id)
    await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    resp = await client.get(
        "/api/v1/restaurants?subscriptionActive=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    ids = [r["id"] for r in resp.json()["data"]]
    assert ids == [rest_with.id]


async def test_filter_subscription_active_false_keeps_only_without(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`?subscriptionActive=false` — рестораны только без активной подписки."""
    org_with = await make_organization()
    org_without = await make_organization()
    await make_restaurant(organization_id=org_with.id)
    rest_without = await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    resp = await client.get(
        "/api/v1/restaurants?subscriptionActive=false",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    ids = [r["id"] for r in resp.json()["data"]]
    assert ids == [rest_without.id]


async def test_filter_query_uses_camelcase_alias_not_snake(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Регрессия контракта: query-параметр — camelCase, snake_case игнорируется.

    Если фронт по ошибке отправит `?subscription_is=true`, фильтр не применится:
    backend не должен молча матчить «похожее» имя.
    """
    org_with = await make_organization()
    org_without = await make_organization()
    await make_restaurant(organization_id=org_with.id)
    await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    resp = await client.get(
        "/api/v1/restaurants?subscription_is=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # Фильтр не применился → возвращаются оба ресторана.
    assert len(resp.json()["data"]) == 2


# ---------- query: limit / offset ----------


async def test_pagination_limit_truncates(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
):
    """`?limit=2` — возвращаются ровно 2 первых ресторана."""
    first = await make_restaurant()
    second = await make_restaurant()
    await make_restaurant()

    resp = await client.get("/api/v1/restaurants?limit=2", headers=auth_headers)
    assert resp.status_code == 200

    ids = [r["id"] for r in resp.json()["data"]]
    assert ids == [first.id, second.id]


async def test_pagination_offset_skips(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
):
    """`?offset=2` — первые два ресторана пропускаются."""
    await make_restaurant()
    await make_restaurant()
    third = await make_restaurant()

    resp = await client.get("/api/v1/restaurants?offset=2", headers=auth_headers)
    assert resp.status_code == 200

    ids = [r["id"] for r in resp.json()["data"]]
    assert ids == [third.id]


async def test_pagination_default_limit_and_offset(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
):
    """Без query — по умолчанию `limit=10`, `offset=0` (см. PaginationParamsM)."""
    created = [await make_restaurant() for _ in range(11)]

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert len(data) == 10  # дефолтный limit
    assert data[0]["id"] == created[0].id
    assert data[-1]["id"] == created[9].id


async def test_pagination_rejects_limit_over_max(client: AsyncClient, auth_headers: dict[str, str]):
    """`limit > 100` запрещён валидацией (ge=1, le=100) → ошибка 4xx, не 500."""
    resp = await client.get("/api/v1/restaurants?limit=101", headers=auth_headers)
    assert 400 <= resp.status_code < 500


async def test_pagination_rejects_negative_offset(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """`offset < 0` запрещён валидацией (ge=0)."""
    resp = await client.get("/api/v1/restaurants?offset=-1", headers=auth_headers)
    assert 400 <= resp.status_code < 500


async def test_pagination_rejects_zero_limit(client: AsyncClient, auth_headers: dict[str, str]):
    """`limit=0` запрещён (ge=1)."""
    resp = await client.get("/api/v1/restaurants?limit=0", headers=auth_headers)
    assert 400 <= resp.status_code < 500


# ---------- значения полей (smoke на интеграцию с сервисом) ----------


async def test_ai_requests_left_value_through_http(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """Smoke на HTTP-слой: `aiRequestsLeft` = MONTHLY_LIMIT - count(logs за месяц)."""
    rest = await make_restaurant()
    for _ in range(3):
        await make_ai_log(restaurant_id=rest.id)

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert item["aiRequestsLeft"] == MONTHLY_AI_REQUEST_LIMIT - 3


async def test_percentage_used_value_through_http(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """Регрессия фикса: 250 логов → percentageOfUsedAiReq == 1.0 (1% от 25000)."""
    rest = await make_restaurant()
    for _ in range(250):
        await make_ai_log(restaurant_id=rest.id)

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert item["percentageOfUsedAiReq"] == 1.0


async def test_tables_count_value_through_http(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_restaurant: RestaurantFactory,
    make_table: TableFactory,
):
    """Smoke на HTTP-слой: `tablesCount` — целое, считается верно."""
    rest = await make_restaurant()
    await make_table(restaurant_id=rest.id)
    await make_table(restaurant_id=rest.id)

    resp = await client.get("/api/v1/restaurants", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert item["tablesCount"] == 2
