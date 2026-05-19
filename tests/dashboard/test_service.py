"""Unit-тесты `app/dashboard/service.py:calculate_app_stats`.

Гоняем функцию напрямую на тестовой sqlite-сессии. Контракт сервиса:
вернуть `AppStats` с суммарными счётчиками по `organizations`, `restaurants`,
`subscriptions`, исключая soft-deleted записи (`deleted_at IS NULL`).
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.schemas import AppStats
from app.dashboard.service import calculate_app_stats

from .conftest import OrganizationFactory, RestaurantFactory, SubscriptionFactory

# ---------- базовый контракт ----------


async def test_returns_app_stats_with_zeros_on_empty_db(db_session: AsyncSession):
    """Пустая БД → все счётчики `0`, не `None` и не исключение."""
    result = await calculate_app_stats(db_session)

    assert isinstance(result, AppStats)
    assert result.total_organizations == 0
    assert result.total_restaurants == 0
    assert result.total_subscriptions == 0


# ---------- организации ----------


async def test_counts_organizations(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """`total_organizations` = число организаций без `deleted_at`."""
    await make_organization()
    await make_organization()
    await make_organization()

    result = await calculate_app_stats(db_session)

    assert result.total_organizations == 3


async def test_excludes_soft_deleted_organizations(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
):
    """Soft-deleted организации в счётчик не идут."""
    await make_organization()
    await make_organization(deleted_at=datetime.now(tz=UTC))
    await make_organization(deleted_at=datetime.now(tz=UTC))

    result = await calculate_app_stats(db_session)

    assert result.total_organizations == 1


# ---------- рестораны ----------


async def test_counts_restaurants(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """`total_restaurants` = число ресторанов без `deleted_at`."""
    await make_restaurant()
    await make_restaurant()

    result = await calculate_app_stats(db_session)

    assert result.total_restaurants == 2


async def test_excludes_soft_deleted_restaurants(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """Soft-deleted рестораны в счётчик не идут."""
    await make_restaurant()
    await make_restaurant(deleted_at=datetime.now(tz=UTC))

    result = await calculate_app_stats(db_session)

    assert result.total_restaurants == 1


async def test_counts_restaurants_regardless_of_is_active(
    db_session: AsyncSession,
    make_restaurant: RestaurantFactory,
):
    """В отличие от `list_restaurants`, dashboard считает и `is_active=false`.

    Поле `is_active` — про "ресторан включил/выключил AI", а не про удаление.
    В общей статистике учитываем оба состояния, фильтруем только удалённые.
    """
    await make_restaurant(is_active=True)
    await make_restaurant(is_active=False)

    result = await calculate_app_stats(db_session)

    assert result.total_restaurants == 2


# ---------- подписки ----------


async def test_counts_subscriptions(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """`total_subscriptions` = число подписок без `deleted_at`."""
    org = await make_organization()
    await make_subscription(organization_id=org.id)
    await make_subscription(organization_id=org.id)

    result = await calculate_app_stats(db_session)

    assert result.total_subscriptions == 2


async def test_excludes_soft_deleted_subscriptions(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Soft-deleted подписки в счётчик не идут."""
    org = await make_organization()
    await make_subscription(organization_id=org.id)
    await make_subscription(organization_id=org.id, deleted_at=datetime.now(tz=UTC))

    result = await calculate_app_stats(db_session)

    assert result.total_subscriptions == 1


async def test_counts_subscriptions_regardless_of_status(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
):
    """Истёкшие и `is_active=false` подписки тоже учитываются.

    Сервис фильтрует только по `deleted_at` — это «всего подписок», а не
    «сколько активных». Регрессия на случай, если кто-то «случайно» добавит
    фильтр по `is_active` или `end_date`.
    """
    org = await make_organization()
    await make_subscription(organization_id=org.id, is_active=True)
    await make_subscription(organization_id=org.id, is_active=False)
    await make_subscription(
        organization_id=org.id,
        end_date=datetime.now(tz=UTC).replace(year=2020),
    )

    result = await calculate_app_stats(db_session)

    assert result.total_subscriptions == 3


# ---------- независимость счётчиков ----------


async def test_counters_are_independent(
    db_session: AsyncSession,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_subscription: SubscriptionFactory,
):
    """Регрессия: каждый счётчик — отдельный subquery, результаты не «склеиваются».

    Был бы баг — count разных таблиц через JOIN дал бы декартово произведение
    (2*3*1=6). Здесь же независимые subqueries дают ровно: 2, 3, 1.
    """
    org_a = await make_organization()
    org_b = await make_organization()
    await make_restaurant(organization_id=org_a.id)
    await make_restaurant(organization_id=org_a.id)
    await make_restaurant(organization_id=org_b.id)
    await make_subscription(organization_id=org_a.id)

    result = await calculate_app_stats(db_session)

    assert result.total_organizations == 2
    assert result.total_restaurants == 3
    assert result.total_subscriptions == 1
