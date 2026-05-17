"""Сервис модуля organization: список орг с админом, ресторанами и подписками."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.pagination import PaginationParamsM
from app.models import Organizations, Restaurants, Subscriptions, Users


async def get_organizations(
    db: AsyncSession,
    params: PaginationParamsM,
) -> Sequence[dict[str, Any]]:
    """Отдает все organization: список орг с админом, ресторанами и подписками."""

    now = datetime.now(tz=UTC)

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

    org_stmt = (
        select(
            Organizations.id.label("id"),
            Organizations.name.label("name"),
            Organizations.phone.label("phone"),
            has_active_subscription.label("subscription_active"),
            Users.id.label("admin_id"),
            Users.name.label("admin_name"),
            Users.phone.label("admin_phone"),
            Users.email.label("admin_email"),
        )
        .join(Users, Users.id == Organizations.admin_id)
        .where(Organizations.deleted_at.is_(None))
        .order_by(Organizations.id.asc())
        .limit(params.limit)
        .offset(params.offset)
    )

    org_rows = (await db.execute(org_stmt)).mappings().all()
    if not org_rows:
        return []

    org_ids = [r["id"] for r in org_rows]
    org_names_by_id = {r["id"]: r["name"] for r in org_rows}
    sub_active_by_org = {r["id"]: bool(r["subscription_active"]) for r in org_rows}

    rest_stmt = (
        select(
            Restaurants.id.label("id"),
            Restaurants.name.label("name"),
            Restaurants.organization_id.label("organization_id"),
            Restaurants.is_active.label("is_active"),
        )
        .where(
            Restaurants.organization_id.in_(org_ids),
            Restaurants.deleted_at.is_(None),
        )
        .order_by(Restaurants.id.asc())
    )

    rest_rows = (await db.execute(rest_stmt)).mappings().all()

    restaurants_by_org: dict[int, list[dict[str, Any]]] = {oid: [] for oid in org_ids}
    for r in rest_rows:
        oid = r["organization_id"]
        restaurants_by_org[oid].append(
            {
                "id": r["id"],
                "name": r["name"],
                "organization_id": oid,
                "organization_name": org_names_by_id[oid],
                "subscription_active": sub_active_by_org[oid],
                # `Restaurants.is_active` nullable в схеме (server_default=false);
                # null трактуем как False — ресторан не "опубликован".
                "is_active": bool(r["is_active"]),
            }
        )

    sub_stmt = (
        select(
            Subscriptions.id.label("id"),
            Subscriptions.organization_id.label("organization_id"),
            Subscriptions.end_date.label("end_date"),
            Subscriptions.is_active.label("is_active"),
            Subscriptions.restaurant_limit.label("restaurant_limit"),
        )
        .where(
            Subscriptions.organization_id.in_(org_ids),
            Subscriptions.deleted_at.is_(None),
        )
        .order_by(Subscriptions.id.asc())
    )

    sub_rows = (await db.execute(sub_stmt)).mappings().all()

    subscriptions_by_org: dict[int, list[dict[str, Any]]] = {oid: [] for oid in org_ids}
    for s in sub_rows:
        subscriptions_by_org[s["organization_id"]].append(
            {
                "id": s["id"],
                "end_date": s["end_date"],
                "is_active": bool(s["is_active"]),
                # `restaurant_limit` nullable в БД; для UI null превращаем в 0.
                "restaurants_count": s["restaurant_limit"] or 0,
            }
        )

    result: list[dict[str, Any]] = []
    for r in org_rows:
        restaurants = restaurants_by_org[r["id"]]
        subscriptions = subscriptions_by_org[r["id"]]
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "phone": r["phone"],
                "admin": {
                    "id": r["admin_id"],
                    "name": r["admin_name"],
                    "phone": r["admin_phone"],
                    "email": r["admin_email"],
                },
                "restaurants": restaurants,
                "restaurants_count": len(restaurants),
                "subscriptions": subscriptions,
            }
        )
    return result
