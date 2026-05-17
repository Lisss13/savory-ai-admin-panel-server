"""Unit-тесты `app/organization/service.py:get_organizations`.

Гоняем функцию напрямую на тестовой sqlite-сессии, без HTTP. Покрываем:
- контракт строки (полный набор полей орг + вложенный admin + restaurants);
- soft-delete фильтры (организации, рестораны);
- расчёт `subscription_active` (тот же критерий, что в `restaurants/service.py`:
  `is_active=true`, не soft-deleted, `end_date >= now`);
- продвижение этого флага в каждый ресторан организации;
- `restaurants_count` соответствует числу ресторанов после фильтра;
- сортировка `id ASC` и изоляция между организациями.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.pagination import PaginationParamsM
from app.organizations.service import get_organizations

from .conftest import (
    OrganizationFactory,
    RestaurantFactory,
    SubscriptionFactory,
    UserFactory,
)

DEFAULT_PAGE = PaginationParamsM(limit=100, offset=0)

# ---------- базовая выдача ----------


async def test_returns_empty_list_when_no_organizations(db_session: AsyncSession):
    """Пустая БД → пустой список (не None и не исключение)."""
    result = await get_organizations(db_session, DEFAULT_PAGE)
    assert result == []


async def test_returns_row_with_all_expected_keys(
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
):
    """Контракт верхнего уровня: id/name/phone + admin + restaurants + subscriptions + counts."""
    admin = await make_user(name="Boss", email="boss@acme.ae", phone="+971555000111")
    _ = await make_organization(name="Acme Corp", phone="+971500001111", admin_id=admin.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert len(result) == 1
    row = result[0]
    assert set(row.keys()) == {
        "id",
        "name",
        "phone",
        "admin",
        "restaurants",
        "restaurants_count",
        "subscriptions",
    }
    assert row["name"] == "Acme Corp"
    assert row["phone"] == "+971500001111"
    assert row["restaurants"] == []
    assert row["restaurants_count"] == 0
    assert row["subscriptions"] == []


async def test_admin_payload_contains_all_expected_fields(
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
):
    """`admin` — это `{id, name, phone, email}` именно этого админа орг."""
    admin = await make_user(name="Boss", email="boss@acme.ae", phone="+971555000111")
    _ = await make_organization(admin_id=admin.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["admin"] == {
        "id": admin.id,
        "name": "Boss",
        "phone": "+971555000111",
        "email": "boss@acme.ae",
    }


# ---------- фильтрация ----------


async def test_excludes_soft_deleted_organizations(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """Орг с `deleted_at IS NOT NULL` не должна попадать в выдачу."""
    active = await make_organization(name="active")
    _ = await make_organization(name="deleted", deleted_at=datetime.now(tz=UTC))

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert [r["id"] for r in result] == [active.id]


async def test_excludes_soft_deleted_restaurants_from_list_and_count(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Soft-deleted рестораны не попадают ни в `restaurants`, ни в `restaurants_count`."""
    org = await make_organization()
    visible = await make_restaurant(name="visible", organization_id=org.id)
    _ = await make_restaurant(name="gone", organization_id=org.id, deleted_at=datetime.now(tz=UTC))

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert len(result) == 1
    assert [r["id"] for r in result[0]["restaurants"]] == [visible.id]
    assert result[0]["restaurants_count"] == 1


async def test_includes_inactive_restaurants(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """В отличие от `list_restaurants`, тут `is_active=false` не отбрасывается —
    глобальной админке нужно видеть все рестораны организации."""
    org = await make_organization()
    active = await make_restaurant(name="on", organization_id=org.id, is_active=True)
    inactive = await make_restaurant(name="off", organization_id=org.id, is_active=False)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    ids = {r["id"] for r in result[0]["restaurants"]}
    assert ids == {active.id, inactive.id}
    assert result[0]["restaurants_count"] == 2


async def test_restaurant_carries_is_active_flag(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """`is_active` — обязательное поле в выдаче ресторана: фронт должен
    отличать рабочий ресторан от выключенного (выдаём и тех и тех)."""
    org = await make_organization()
    await make_restaurant(name="on", organization_id=org.id, is_active=True)
    await make_restaurant(name="off", organization_id=org.id, is_active=False)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    by_name = {r["name"]: r for r in result[0]["restaurants"]}

    assert by_name["on"]["is_active"] is True
    assert by_name["off"]["is_active"] is False


# ---------- ресторанные поля ----------


async def test_restaurants_carry_organization_id_and_name(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Каждый ресторан несёт `organization_id` и `organization_name` своей орг."""
    org = await make_organization(name="Acme Corp")
    rest = await make_restaurant(name="Main", organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    item = result[0]["restaurants"][0]
    assert item["id"] == rest.id
    assert item["name"] == "Main"
    assert item["organization_id"] == org.id
    assert item["organization_name"] == "Acme Corp"


async def test_restaurants_isolated_per_organization(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Рестораны орг A не должны протекать в орг B."""
    org_a = await make_organization(name="A")
    org_b = await make_organization(name="B")
    a1 = await make_restaurant(organization_id=org_a.id)
    a2 = await make_restaurant(organization_id=org_a.id)
    b1 = await make_restaurant(organization_id=org_b.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    by_org = {r["id"]: r for r in result}

    assert {x["id"] for x in by_org[org_a.id]["restaurants"]} == {a1.id, a2.id}
    assert {x["id"] for x in by_org[org_b.id]["restaurants"]} == {b1.id}
    assert by_org[org_a.id]["restaurants_count"] == 2
    assert by_org[org_b.id]["restaurants_count"] == 1


# ---------- subscription_active ----------


async def test_subscription_active_true_when_active_subscription_exists(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """`subscriptionActive=true` у орг, если есть активная неистёкшая подписка."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_subscription(organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["restaurants"][0]["subscription_active"] is True


async def test_subscription_active_false_when_no_subscription(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
):
    """Нет ни одной подписки → флаг `false`."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["restaurants"][0]["subscription_active"] is False


async def test_subscription_active_false_when_expired(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписка с `end_date < now` считается неактивной."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    past = datetime.now(tz=UTC) - timedelta(days=1)
    await make_subscription(organization_id=org.id, end_date=past)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["restaurants"][0]["subscription_active"] is False


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

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["restaurants"][0]["subscription_active"] is False


async def test_subscription_active_false_when_soft_deleted(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Soft-deleted подписка не учитывается в EXISTS."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_subscription(organization_id=org.id, deleted_at=datetime.now(tz=UTC))

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["restaurants"][0]["subscription_active"] is False


async def test_subscription_active_propagates_to_all_restaurants_of_org(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписка лежит на уровне орг — флаг одинаков у всех её ресторанов."""
    org = await make_organization()
    await make_restaurant(organization_id=org.id)
    await make_restaurant(organization_id=org.id)
    await make_subscription(organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    flags = [r["subscription_active"] for r in result[0]["restaurants"]]

    assert flags == [True, True]


async def test_subscription_active_isolated_between_organizations(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписка одной орг не должна включать флаг у другой орг."""
    with_sub = await make_organization(name="paid")
    without_sub = await make_organization(name="free")
    await make_restaurant(organization_id=with_sub.id)
    await make_restaurant(organization_id=without_sub.id)
    await make_subscription(organization_id=with_sub.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    by_org = {r["id"]: r for r in result}

    assert by_org[with_sub.id]["restaurants"][0]["subscription_active"] is True
    assert by_org[without_sub.id]["restaurants"][0]["subscription_active"] is False


# ---------- сортировка / выдача нескольких орг ----------


async def test_organizations_sorted_by_id_asc(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """Сортировка по `Organizations.id ASC` — стабильна для UI-листинга."""
    a = await make_organization()
    b = await make_organization()
    c = await make_organization()

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert [r["id"] for r in result] == sorted([a.id, b.id, c.id])


# ---------- subscriptions: куплено и когда истекают ----------


async def test_subscriptions_list_empty_when_none(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """У орг без подписок — пустой список `subscriptions`."""
    await make_organization()

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert result[0]["subscriptions"] == []


async def test_subscriptions_single_returned_with_expected_fields(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Каждая подписка возвращается с `id`, `end_date`, `is_active`, `restaurants_count`.

    `restaurants_count` — это `Subscriptions.restaurant_limit`: сколько
    ресторанов разрешает эта подписка. Фронту нужно для отображения "тариф".
    """
    org = await make_organization()
    end = datetime.now(tz=UTC) + timedelta(days=30)
    sub = await make_subscription(
        organization_id=org.id, end_date=end, is_active=True, restaurant_limit=3
    )

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert len(result[0]["subscriptions"]) == 1
    item = result[0]["subscriptions"][0]
    assert set(item.keys()) == {"id", "end_date", "is_active", "restaurants_count"}
    assert item["id"] == sub.id
    # SQLite не сохраняет tzinfo — сравниваем как naive (в Postgres tz сохранится).
    assert item["end_date"].replace(tzinfo=None) == end.replace(tzinfo=None)
    assert item["is_active"] is True
    assert item["restaurants_count"] == 3


async def test_subscriptions_restaurants_count_reflects_restaurant_limit(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`restaurants_count` в подписке равен `restaurant_limit` той же строки в БД."""
    org = await make_organization()
    await make_subscription(organization_id=org.id, restaurant_limit=1)
    await make_subscription(organization_id=org.id, restaurant_limit=5)
    await make_subscription(organization_id=org.id, restaurant_limit=10)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    limits = [s["restaurants_count"] for s in result[0]["subscriptions"]]

    assert sorted(limits) == [1, 5, 10]


async def test_subscriptions_includes_expired(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """В списке "куплено" истёкшие подписки тоже видны (фронт показывает историю)."""
    org = await make_organization()
    past = datetime.now(tz=UTC) - timedelta(days=1)
    expired = await make_subscription(organization_id=org.id, end_date=past)
    future = await make_subscription(organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    ids = {s["id"] for s in result[0]["subscriptions"]}
    assert ids == {expired.id, future.id}


async def test_subscriptions_includes_is_active_false(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`is_active=False` не исключает подписку из "куплено" — отдаём как есть."""
    org = await make_organization()
    inactive = await make_subscription(organization_id=org.id, is_active=False)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert len(result[0]["subscriptions"]) == 1
    assert result[0]["subscriptions"][0]["id"] == inactive.id
    assert result[0]["subscriptions"][0]["is_active"] is False


async def test_subscriptions_excludes_soft_deleted(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Soft-deleted подписка не попадает в список."""
    org = await make_organization()
    visible = await make_subscription(organization_id=org.id)
    _ = await make_subscription(organization_id=org.id, deleted_at=datetime.now(tz=UTC))

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert [s["id"] for s in result[0]["subscriptions"]] == [visible.id]


async def test_subscriptions_isolated_per_organization(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписки орг A не должны протекать в орг B."""
    org_a = await make_organization()
    org_b = await make_organization()
    a1 = await make_subscription(organization_id=org_a.id)
    a2 = await make_subscription(organization_id=org_a.id)
    b1 = await make_subscription(organization_id=org_b.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)
    by_org = {r["id"]: r for r in result}

    assert {s["id"] for s in by_org[org_a.id]["subscriptions"]} == {a1.id, a2.id}
    assert {s["id"] for s in by_org[org_b.id]["subscriptions"]} == {b1.id}


async def test_subscriptions_sorted_by_id_asc(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Подписки сортируются по `Subscriptions.id ASC` — консистентно с restaurants."""
    org = await make_organization()
    s1 = await make_subscription(organization_id=org.id)
    s2 = await make_subscription(organization_id=org.id)
    s3 = await make_subscription(organization_id=org.id)

    result = await get_organizations(db_session, DEFAULT_PAGE)

    assert [s["id"] for s in result[0]["subscriptions"]] == sorted([s1.id, s2.id, s3.id])


# ---------- пагинация ----------


async def test_pagination_default_limit_truncates_to_10(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """Дефолтный `limit=10` (из `PaginationParamsM`) обрезает выдачу до 10."""
    created = [await make_organization() for _ in range(12)]

    result = await get_organizations(db_session, PaginationParamsM())

    assert len(result) == 10
    assert [r["id"] for r in result] == [o.id for o in created[:10]]


async def test_pagination_limit_truncates_result(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """`limit=2` — возвращаются первые 2 орг по `id ASC`."""
    first = await make_organization()
    second = await make_organization()
    _ = await make_organization()

    result = await get_organizations(db_session, PaginationParamsM(limit=2, offset=0))

    assert [r["id"] for r in result] == [first.id, second.id]


async def test_pagination_offset_skips_records(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """`offset=2` — первые два пропускаются."""
    _ = await make_organization()
    _ = await make_organization()
    third = await make_organization()

    result = await get_organizations(db_session, PaginationParamsM(limit=10, offset=2))

    assert [r["id"] for r in result] == [third.id]


async def test_pagination_offset_beyond_total_returns_empty(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """`offset > total` — пустой список, без падения."""
    _ = await make_organization()

    result = await get_organizations(db_session, PaginationParamsM(limit=10, offset=100))

    assert result == []


async def test_pagination_only_loads_nested_data_for_returned_orgs(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Пагинация ограничивает не только орг, но и подтянутые рестораны/подписки.

    Это контракт против регресса: `IN (org_ids)` для ресторанов и подписок
    должен использовать ID **только пагинированной страницы**, иначе мы будем
    тянуть всю БД при выдаче одной орг.
    """
    page1_org = await make_organization()
    page2_org = await make_organization()
    await make_restaurant(organization_id=page1_org.id)
    await make_subscription(organization_id=page1_org.id)
    # Эти не должны попасть в выдачу первой страницы.
    await make_restaurant(organization_id=page2_org.id)
    await make_subscription(organization_id=page2_org.id)

    result = await get_organizations(db_session, PaginationParamsM(limit=1, offset=0))

    assert len(result) == 1
    assert result[0]["id"] == page1_org.id
    assert len(result[0]["restaurants"]) == 1
    assert len(result[0]["subscriptions"]) == 1
