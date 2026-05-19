"""Сервис dashboard: агрегированная статистика по всему приложению."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.schemas import AppStats
from app.models import Organizations, Restaurants, Subscriptions


async def calculate_app_stats(db: AsyncSession) -> AppStats:
    """Считает суммарные метрики по системе для главного экрана админки."""
    orgs_count = (
        select(func.count(Organizations.id))
        .where(Organizations.deleted_at.is_(None))
        .scalar_subquery()
    )
    restaurants_count = (
        select(func.count(Restaurants.id)).where(Restaurants.deleted_at.is_(None)).scalar_subquery()
    )
    subscriptions_count = (
        select(func.count(Subscriptions.id))
        .where(Subscriptions.deleted_at.is_(None))
        .scalar_subquery()
    )

    stmt = select(
        orgs_count.label("total_organizations"),
        restaurants_count.label("total_restaurants"),
        subscriptions_count.label("total_subscriptions"),
    )
    row = (await db.execute(stmt)).mappings().one()
    return AppStats.model_validate(dict(row))
