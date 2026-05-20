from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.pagination import PaginationModel
from app.models import (
    AiRequestLogs,
    Dishes,
    MenuCategories,
    Organizations,
    Restaurants,
    Subscriptions,
    Tables,
)
from app.restaurants.schemas import RestaurantDetailResponse
from app.restaurants.utils import percentage

# Месячный лимит AI-запросов на один ресторан — синхронизирован с Go-`server/`
# (`app/storage/constants.go::MonthlyAIRequestLimit = 25000`).
MONTHLY_AI_REQUEST_LIMIT = 25_000


async def list_restaurants(
    db: AsyncSession,
    params: PaginationModel,
    subscription_is: bool | None = None,
) -> Sequence[dict[str, Any]]:
    """Активные рестораны + название организации, флаг подписки, кол-во столиков, остаток AI-лимита.

    Запрос построен через subquery + LEFT JOIN, чтобы рестораны без столиков /
    без AI-логов всё равно попадали в выдачу (`COALESCE → 0`). Подписка считается
    активной, если у организации есть строка `Subscriptions` с `is_active=true`,
    не soft-deleted, и `end_date >= now()` — это совпадает с условием
    "is active" из основного Go-`server/`.

    `subscription_is`:
      - `True`  → только рестораны организаций с активной подпиской;
      - `False` → только рестораны организаций без активной подписки;
      - `None`  → без фильтра.

    Сортировка `Restaurants.id ASC` — стабильна для пагинации (`limit`/`offset`).
    """
    now = datetime.now(tz=UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Кол-во столиков на ресторан (только активные строки `tables`).
    tables_count_sq = (
        select(
            Tables.restaurant_id.label("restaurant_id"),
            func.count(Tables.id).label("tables_count"),
        )
        .where(Tables.deleted_at.is_(None))
        .group_by(Tables.restaurant_id)
        .subquery()
    )

    # AI-запросы ресторана за текущий календарный месяц.
    ai_used_sq = (
        select(
            AiRequestLogs.restaurant_id.label("restaurant_id"),
            func.count(AiRequestLogs.id).label("ai_used"),
        )
        .where(
            AiRequestLogs.deleted_at.is_(None),
            AiRequestLogs.created_at >= month_start,
        )
        .group_by(AiRequestLogs.restaurant_id)
        .subquery()
    )

    # EXISTS-подзапрос: есть ли у организации активная подписка прямо сейчас.
    # Коррелируется через `Organizations.id` из внешнего FROM.
    has_active_subscription = (
        select(Subscriptions.id)
        .where(
            Subscriptions.organization_id == Organizations.id,
            Subscriptions.is_active.is_(True),
            Subscriptions.deleted_at.is_(None),
            Subscriptions.end_date >= now,
        )
        .exists()
    )

    stmt = (
        select(
            Restaurants.id.label("id"),
            Restaurants.name.label("name"),
            Organizations.id.label("organization_id"),
            Organizations.name.label("organization_name"),
            has_active_subscription.label("subscription_active"),
            func.coalesce(tables_count_sq.c.tables_count, 0).label("tables_count"),
            (MONTHLY_AI_REQUEST_LIMIT - func.coalesce(ai_used_sq.c.ai_used, 0)).label(
                "ai_requests_left"
            ),
        )
        .join(Organizations, Organizations.id == Restaurants.organization_id)
        .outerjoin(tables_count_sq, tables_count_sq.c.restaurant_id == Restaurants.id)
        .outerjoin(ai_used_sq, ai_used_sq.c.restaurant_id == Restaurants.id)
        .where(
            Restaurants.deleted_at.is_(None),
            Restaurants.is_active.is_(True),
        )
    )

    if subscription_is is not None:
        stmt = stmt.where(has_active_subscription if subscription_is else ~has_active_subscription)

    stmt = stmt.order_by(Restaurants.id.asc()).limit(params.limit).offset(params.offset)

    res = await db.execute(stmt)
    result = []
    for rom in res.mappings().all():
        rom = dict(rom)
        rom["subscription_active"] = bool(rom["subscription_active"])
        ai_used = MONTHLY_AI_REQUEST_LIMIT - rom["ai_requests_left"]
        rom["percentage_of_used_ai_req"] = percentage(ai_used, MONTHLY_AI_REQUEST_LIMIT)
        result.append(rom)
    return result


async def get_restaurant_by_id(
    db: AsyncSession, restaurant_id: int
) -> RestaurantDetailResponse | None:
    now = datetime.now(tz=UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    tables_count_sq = (
        select(
            Tables.restaurant_id.label("restaurant_id"),
            func.count(Tables.id).label("tables_count"),
        )
        .where(Tables.deleted_at.is_(None))
        .group_by(Tables.restaurant_id)
        .subquery()
    )

    ai_used_sq = (
        select(
            AiRequestLogs.restaurant_id.label("restaurant_id"),
            func.count(AiRequestLogs.id).label("ai_used"),
        )
        .where(
            AiRequestLogs.deleted_at.is_(None),
            AiRequestLogs.created_at >= month_start,
        )
        .group_by(AiRequestLogs.restaurant_id)
        .subquery()
    )

    # Активные категории меню ресторана.
    menu_categories_sq = (
        select(
            MenuCategories.restaurant_id.label("restaurant_id"),
            func.count(MenuCategories.id).label("menu_categories_count"),
        )
        .where(MenuCategories.deleted_at.is_(None))
        .group_by(MenuCategories.restaurant_id)
        .subquery()
    )

    # Всего блюд (`dishes_count`) и среди них доступных в меню (`dishes_active_count`).
    # В модели нет `is_active`, доступность блюда отражает `is_available`.
    dishes_sq = (
        select(
            Dishes.restaurant_id.label("restaurant_id"),
            func.count(Dishes.id).label("dishes_count"),
            func.count(Dishes.id)
            .filter(Dishes.is_available.is_(True))
            .label("dishes_active_count"),
        )
        .where(Dishes.deleted_at.is_(None))
        .group_by(Dishes.restaurant_id)
        .subquery()
    )

    has_active_subscription = (
        select(Subscriptions.id)
        .where(
            Subscriptions.organization_id == Organizations.id,
            Subscriptions.is_active.is_(True),
            Subscriptions.deleted_at.is_(None),
            Subscriptions.end_date >= now,
        )
        .exists()
    )

    ai_used_expr = func.coalesce(ai_used_sq.c.ai_used, 0)

    stmt = (
        select(
            Restaurants.id.label("id"),
            Restaurants.name.label("name"),
            Restaurants.default_language.label("default_language"),
            Restaurants.show_dish_links.label("show_dish_links"),
            Restaurants.ai_suggestions_enabled.label("ai_suggestions_enabled"),
            Restaurants.created_at.label("created_at"),
            Restaurants.updated_at.label("updated_at"),
            Organizations.id.label("organization_id"),
            Organizations.name.label("organization_name"),
            has_active_subscription.label("subscription_active"),
            func.coalesce(tables_count_sq.c.tables_count, 0).label("tables_count"),
            ai_used_expr.label("ai_requests_used"),
            (MONTHLY_AI_REQUEST_LIMIT - ai_used_expr).label("ai_requests_left"),
            func.coalesce(menu_categories_sq.c.menu_categories_count, 0).label(
                "menu_categories_count"
            ),
            func.coalesce(dishes_sq.c.dishes_count, 0).label("dishes_count"),
            func.coalesce(dishes_sq.c.dishes_active_count, 0).label("dishes_active_count"),
        )
        .join(Organizations, Organizations.id == Restaurants.organization_id)
        .outerjoin(tables_count_sq, tables_count_sq.c.restaurant_id == Restaurants.id)
        .outerjoin(ai_used_sq, ai_used_sq.c.restaurant_id == Restaurants.id)
        .outerjoin(menu_categories_sq, menu_categories_sq.c.restaurant_id == Restaurants.id)
        .outerjoin(dishes_sq, dishes_sq.c.restaurant_id == Restaurants.id)
        .where(
            Restaurants.deleted_at.is_(None),
            Restaurants.is_active.is_(True),
            Restaurants.id == restaurant_id,
        )
    )

    row = (await db.execute(stmt)).mappings().first()
    if row is None:
        return None

    data = dict(row)
    data["subscription_active"] = bool(data["subscription_active"])
    data["percentage_of_used_ai_req"] = percentage(
        data["ai_requests_used"], MONTHLY_AI_REQUEST_LIMIT
    )
    return RestaurantDetailResponse.model_validate(data)
