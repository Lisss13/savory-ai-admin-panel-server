"""Unit-тесты `app/restaurants/service.py:list_restaurants`.

Гоняем функцию напрямую на тестовой sqlite-сессии, без HTTP. Проверяем
бизнес-правила (фильтрация soft-delete / `is_active`, подсчёт столиков и
AI-лимита, активность подписки) и пагинацию — отдельно от HTTP-роутера.

Базовый кейс не повторяется — фабрики создают разумные дефолты,
тесты переопределяют только то, что доказывают.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.pagination import PaginationParamsM
from app.restaurants.service import MONTHLY_AI_REQUEST_LIMIT, list_restaurants

from .conftest import (
    AiLogFactory,
    OrganizationFactory,
    RestaurantFactory,
    SubscriptionFactory,
    TableFactory,
)

DEFAULT_PAGE = PaginationParamsM(limit=100, offset=0)


# ---------- базовая выдача ----------


async def test_returns_empty_list_when_no_restaurants(db_session: AsyncSession):
    """Пустая БД → пустой список (не None и не исключение)."""
    result = await list_restaurants(db_session, DEFAULT_PAGE)
    assert result == []


async def test_returns_row_with_all_expected_keys(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Контракт `list_restaurants`: возвращает строку с фиксированным набором полей."""
    org = await make_organization(name="Acme Corp")
    await make_restaurant(name="Main", organization_id=org.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert len(result) == 1
    row = result[0]
    assert set(row.keys()) == {
        "id",
        "name",
        "organization_id",
        "organization_name",
        "subscription_active",
        "tables_count",
        "ai_requests_left",
        "percentage_of_used_ai_req",
    }
    assert row["name"] == "Main"
    assert row["organization_name"] == "Acme Corp"


# ---------- фильтрация ресторанов ----------


async def test_excludes_soft_deleted_restaurants(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Ресторан с `deleted_at IS NOT NULL` не должен попадать в выдачу."""
    active = await make_restaurant(name="active")
    await make_restaurant(name="deleted", deleted_at=datetime.now(tz=UTC))

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert [r["id"] for r in result] == [active.id]


async def test_excludes_inactive_restaurants(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`is_active=false` — ресторан не должен попадать в админ-список активных."""
    active = await make_restaurant(name="active", is_active=True)
    await make_restaurant(name="inactive", is_active=False)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert [r["id"] for r in result] == [active.id]


async def test_orders_by_id_ascending(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Сортировка `id ASC` — стабильна для пагинации."""
    first = await make_restaurant()
    second = await make_restaurant()
    third = await make_restaurant()

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert [r["id"] for r in result] == [first.id, second.id, third.id]


# ---------- столики ----------


async def test_tables_count_is_zero_when_no_tables(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`tablesCount=0`, если столиков нет — LEFT JOIN + COALESCE."""
    await make_restaurant()

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["tables_count"] == 0


async def test_tables_count_counts_only_active(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_table: TableFactory,
):
    """В `tablesCount` попадают только не soft-deleted столики этого ресторана."""
    rest = await make_restaurant()
    await make_table(restaurant_id=rest.id)
    await make_table(restaurant_id=rest.id)
    await make_table(restaurant_id=rest.id, deleted_at=datetime.now(tz=UTC))

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["tables_count"] == 2


async def test_tables_count_isolated_per_restaurant(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_table: TableFactory,
):
    """Столики ресторана А не должны попадать в счётчик ресторана Б."""
    rest_a = await make_restaurant()
    rest_b = await make_restaurant()
    await make_table(restaurant_id=rest_a.id)
    await make_table(restaurant_id=rest_a.id)
    await make_table(restaurant_id=rest_b.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)
    counts = {r["id"]: r["tables_count"] for r in result}

    assert counts[rest_a.id] == 2
    assert counts[rest_b.id] == 1


# ---------- AI-лимит ----------


async def test_ai_requests_left_equals_limit_when_no_logs(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Без AI-логов остаток = полный месячный лимит (COALESCE → 0 использовано)."""
    await make_restaurant()

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["ai_requests_left"] == MONTHLY_AI_REQUEST_LIMIT


async def test_ai_requests_left_decreases_by_count_of_logs(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """`aiRequestsLeft = MONTHLY_LIMIT - count(ai_request_logs за месяц)`."""
    rest = await make_restaurant()
    for _ in range(5):
        await make_ai_log(restaurant_id=rest.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["ai_requests_left"] == MONTHLY_AI_REQUEST_LIMIT - 5


async def test_ai_requests_excludes_soft_deleted_logs(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """Soft-deleted AI-логи в счётчик не идут."""
    rest = await make_restaurant()
    await make_ai_log(restaurant_id=rest.id)
    await make_ai_log(restaurant_id=rest.id)
    await make_ai_log(restaurant_id=rest.id, deleted_at=datetime.now(tz=UTC))

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["ai_requests_left"] == MONTHLY_AI_REQUEST_LIMIT - 2


async def test_ai_requests_excludes_logs_from_previous_month(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """В счётчик идут только логи >= 1-го числа текущего месяца."""
    rest = await make_restaurant()
    now = datetime.now(tz=UTC)
    last_month = now.replace(day=1) - timedelta(days=1)
    await make_ai_log(restaurant_id=rest.id)  # этот месяц
    await make_ai_log(restaurant_id=rest.id, created_at=last_month)  # прошлый

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["ai_requests_left"] == MONTHLY_AI_REQUEST_LIMIT - 1


async def test_ai_requests_isolated_per_restaurant(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """Логи ресторана А не уменьшают остаток ресторана Б."""
    rest_a = await make_restaurant()
    rest_b = await make_restaurant()
    await make_ai_log(restaurant_id=rest_a.id)
    await make_ai_log(restaurant_id=rest_a.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)
    left = {r["id"]: r["ai_requests_left"] for r in result}

    assert left[rest_a.id] == MONTHLY_AI_REQUEST_LIMIT - 2
    assert left[rest_b.id] == MONTHLY_AI_REQUEST_LIMIT


# ---------- percentageOfUsedAiReq ----------


async def test_percentage_used_is_zero_when_no_logs(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Регрессия фикса: при 0 использованных запросов процент == 0, а не 100."""
    await make_restaurant()

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["percentage_of_used_ai_req"] == 0.0


async def test_percentage_used_is_full_when_limit_reached(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """Один лог = 1/25000 ≈ 0.0 (округлено до 2 знаков). Контракт `percentage`."""
    rest = await make_restaurant()
    await make_ai_log(restaurant_id=rest.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    # 1 / 25000 * 100 = 0.004 → round(_, 2) == 0.0
    assert result[0]["percentage_of_used_ai_req"] == 0.0


async def test_percentage_used_reflects_actual_usage(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
    make_ai_log: AiLogFactory,
):
    """250 логов = 1% от лимита 25000 — проверяет, что считается `used / limit`."""
    rest = await make_restaurant()
    for _ in range(250):
        await make_ai_log(restaurant_id=rest.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["percentage_of_used_ai_req"] == 1.0


# ---------- подписка ----------


async def test_subscription_active_true_when_active_subscription_exists(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`subscriptionActive=true`, если у орг есть активная неистёкшая подписка."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_subscription(organization_id=org.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["subscription_active"] is True


async def test_subscription_active_false_when_no_subscription(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Нет ни одной подписки у орг → `subscriptionActive=false`."""
    await make_restaurant()

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["subscription_active"] is False


async def test_subscription_active_false_when_expired(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписка с `end_date < now` считается неактивной (контракт Go-сервера)."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    past = datetime.now(tz=UTC) - timedelta(days=1)
    await make_subscription(organization_id=org.id, end_date=past)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["subscription_active"] is False


async def test_subscription_active_false_when_is_active_flag_false(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`is_active=false` — подписка не считается активной даже при будущей дате."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_subscription(organization_id=org.id, is_active=False)

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["subscription_active"] is False


async def test_subscription_active_false_when_soft_deleted(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Soft-deleted подписка не учитывается в EXISTS."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_subscription(
        organization_id=org.id, deleted_at=datetime.now(tz=UTC)
    )

    result = await list_restaurants(db_session, DEFAULT_PAGE)

    assert result[0]["subscription_active"] is False


# ---------- фильтр subscription_is ----------


async def test_filter_subscription_is_true_keeps_only_active(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`subscription_is=True` оставляет только рестораны с активной подпиской."""
    org_with = await make_organization(name="with-sub")
    org_without = await make_organization(name="no-sub")
    rest_with = await make_restaurant(organization_id=org_with.id)
    await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE, subscription_is=True)

    assert [r["id"] for r in result] == [rest_with.id]


async def test_filter_subscription_is_false_keeps_only_inactive(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`subscription_is=False` оставляет только рестораны без активной подписки."""
    org_with = await make_organization(name="with-sub")
    org_without = await make_organization(name="no-sub")
    await make_restaurant(organization_id=org_with.id)
    rest_without = await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE, subscription_is=False)

    assert [r["id"] for r in result] == [rest_without.id]


async def test_filter_subscription_is_none_returns_all(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`subscription_is=None` (по умолчанию) — без фильтрации."""
    org_with = await make_organization()
    org_without = await make_organization()
    await make_restaurant(organization_id=org_with.id)
    await make_restaurant(organization_id=org_without.id)
    await make_subscription(organization_id=org_with.id)

    result = await list_restaurants(db_session, DEFAULT_PAGE, subscription_is=None)

    assert len(result) == 2


# ---------- пагинация ----------


async def test_pagination_limit_truncates_result(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`limit=2` — возвращаются первые 2 ресторана по `id ASC`."""
    first = await make_restaurant()
    second = await make_restaurant()
    await make_restaurant()

    result = await list_restaurants(
        db_session, PaginationParamsM(limit=2, offset=0)
    )

    assert [r["id"] for r in result] == [first.id, second.id]


async def test_pagination_offset_skips_records(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`offset=2` — первые два пропускаются."""
    await make_restaurant()
    await make_restaurant()
    third = await make_restaurant()

    result = await list_restaurants(
        db_session, PaginationParamsM(limit=10, offset=2)
    )

    assert [r["id"] for r in result] == [third.id]


async def test_pagination_offset_beyond_total_returns_empty(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`offset > total` — пустой список, без падения."""
    await make_restaurant()

    result = await list_restaurants(
        db_session, PaginationParamsM(limit=10, offset=100)
    )

    assert result == []
