"""HTTP-тесты `/api/v1/subscriptions/extension/*`.

Покрывают:
- envelope + camelCase + фильтры + дефолт `status=pending` + пагинацию;
- POST `/reject` без побочного эффекта на подписку + AdminLog;
- POST `/approve` все 4 ветки:
  - SEAMLESS с активной подпиской → `mode=seamless_extend`, продление;
  - SEAMLESS без активной → fallback `mode=immediate_new`, создание новой;
  - IMMEDIATE с активной → `mode=immediate_new`, старая деактивирована;
  - IMMEDIATE без активной → `mode=immediate_new`, новая создана;
- валидация `endDateOverride` (в прошлом, до start), `restaurantLimit` приоритет,
  NUL-байты, статус-гейт, AdminLog с подробным `details`.

Admin-only auth — отдельный параметризованный тест в `test_auth.py`.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log.models import AdminLogs
from app.models import Subscriptions

from .conftest import (
    ExtensionRequestFactory,
    OrganizationFactory,
    SubscriptionFactory,
    UserFactory,
)

# ---------- envelope + список ----------


async def test_list_returns_envelope_with_camel_case(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    await make_extension_request(
        organization_id=org.id, user_id=user.id, period=6, requested_restaurant_limit=4
    )

    resp = await client.get("/api/v1/subscriptions/extension", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200 and body["messages"] == []
    data = body["data"]
    assert data["page"] == 1 and data["total"] == 1

    item = data["items"][0]
    assert item["status"] == "pending"
    assert item["requestedRestaurantLimit"] == 4
    assert item["organization"]["id"] == org.id
    assert item["user"]["id"] == user.id


async def test_list_filters_by_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    await make_extension_request(organization_id=org.id, user_id=user.id, status="pending")
    await make_extension_request(organization_id=org.id, user_id=user.id, status="rejected")

    resp = await client.get("/api/v1/subscriptions/extension?status=rejected", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1 and items[0]["status"] == "rejected"


async def test_list_default_status_is_pending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """Без явного `?status=` показываются только pending (очередь работы)."""
    org = await make_organization()
    user = await make_user()
    await make_extension_request(organization_id=org.id, user_id=user.id, status="pending")
    await make_extension_request(organization_id=org.id, user_id=user.id, status="completed")
    await make_extension_request(organization_id=org.id, user_id=user.id, status="rejected")

    resp = await client.get("/api/v1/subscriptions/extension", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["status"] == "pending"


async def test_list_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """`pageSize=1` отдаёт одну запись, `total` отражает реальное число."""
    org = await make_organization()
    user = await make_user()
    for _ in range(3):
        await make_extension_request(organization_id=org.id, user_id=user.id, status="pending")

    resp = await client.get(
        "/api/v1/subscriptions/extension?page=2&pageSize=1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["page"] == 2 and data["pageSize"] == 1 and data["total"] == 3
    assert len(data["items"]) == 1


# ---------- get by id ----------


async def test_get_by_id_404_for_missing(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/v1/subscriptions/extension/9999", headers=auth_headers)
    assert resp.status_code == 404


# ---------- POST /reject ----------


async def test_reject_changes_only_request(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """Reject переводит заявку в `rejected`, подписку НЕ трогает."""
    org = await make_organization()
    user = await make_user()
    sub = await make_subscription(organization_id=org.id, is_active=True)
    req = await make_extension_request(organization_id=org.id, user_id=user.id)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/reject",
        headers=auth_headers,
        json={"adminComment": "no budget"},
    )
    assert resp.status_code == 200
    item = resp.json()["data"]
    assert item["status"] == "rejected" and item["adminComment"] == "no budget"

    # Подписка не тронута.
    await db_session.refresh(sub)
    assert sub.is_active is True


async def test_reject_from_non_pending_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """Reject уже-completed/rejected заявки → 400 ExtensionRequestNotPending."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(
        organization_id=org.id, user_id=user.id, status="completed", period=3
    )
    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/reject",
        headers=auth_headers,
        json={"adminComment": "duplicate"},
    )
    assert resp.status_code == 400


async def test_reject_writes_admin_log_with_details(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """AdminLog reject содержит `previousStatus`, `newStatus`, `adminComment`."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/reject",
        headers=auth_headers,
        json={"adminComment": "no funds"},
    )
    assert resp.status_code == 200, resp.json()

    log = (
        await db_session.execute(
            select(AdminLogs).where(
                AdminLogs.entity_type == "subscription_extension_request",
                AdminLogs.entity_id == req.id,
            )
        )
    ).scalar_one()
    assert log.action == "update"
    assert log.details == {
        "previousStatus": "pending",
        "newStatus": "rejected",
        "adminComment": "no funds",
    }


# ---------- approve: SEAMLESS с активной → seamless_extend ----------


async def test_approve_seamless_extends_active_subscription(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """SEAMLESS + есть активная → endDate += period мес., period += request.period."""
    now = datetime.now(UTC)
    org = await make_organization()
    user = await make_user()
    old_end = now + timedelta(days=30)
    sub = await make_subscription(
        organization_id=org.id,
        period=1,
        start_date=now - timedelta(days=10),
        end_date=old_end,
        is_active=True,
        restaurant_limit=2,
    )
    req = await make_extension_request(
        organization_id=org.id,
        user_id=user.id,
        period=3,
        requested_restaurant_limit=0,
    )

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "seamless", "adminComment": "approved by phone"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "seamless_extend"
    assert data["extensionRequest"]["status"] == "completed"
    assert data["subscription"]["id"] == sub.id
    assert data["subscription"]["period"] == 1 + 3  # инкремент
    assert data["subscription"]["isActive"] is True

    # endDate сдвинулась примерно на 3 месяца от старого endDate
    new_end_dt = datetime.fromisoformat(data["subscription"]["endDate"].replace("Z", "+00:00"))
    delta_days = (new_end_dt - old_end).days
    assert 85 <= delta_days <= 95  # ~3 мес


# ---------- approve: SEAMLESS без активной → fallback immediate_new ----------


async def test_approve_seamless_without_active_falls_back_to_immediate_new(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """SEAMLESS, активной нет → фолбэк IMMEDIATE_NEW: создаётся новая подписка."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=6)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "seamless"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "immediate_new"
    assert data["subscription"]["period"] == 6
    assert data["subscription"]["isActive"] is True
    assert data["subscription"]["restaurantLimit"] == 1  # default


# ---------- approve: IMMEDIATE с активной → старая деактивирована ----------


async def test_approve_immediate_without_active_creates_fresh(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """IMMEDIATE без активной подписки → создаётся новая с `start_date=now`."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=4)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["mode"] == "immediate_new"
    assert data["subscription"]["period"] == 4
    assert data["subscription"]["isActive"] is True


async def test_approve_immediate_with_end_date_override(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """IMMEDIATE с `endDateOverride` → endDate из override, `period` подписки = request.period."""
    now = datetime.now(UTC)
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=2)
    override = now + timedelta(days=500)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate", "endDateOverride": override.isoformat()},
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["mode"] == "immediate_new"
    end_dt = datetime.fromisoformat(data["subscription"]["endDate"].replace("Z", "+00:00"))
    # Допуск в пару секунд на исполнение запроса.
    assert abs((end_dt - override).total_seconds()) < 5


async def test_approve_immediate_deactivates_old_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """IMMEDIATE с активной → создаётся новая, старая `is_active=False`."""
    org = await make_organization()
    user = await make_user()
    old_sub = await make_subscription(organization_id=org.id, is_active=True)
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=3)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "immediate_new"
    assert data["subscription"]["id"] != old_sub.id

    await db_session.refresh(old_sub)
    assert old_sub.is_active is False


# ---------- approve: restaurantLimit приоритет ----------


async def test_approve_uses_override_restaurant_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """`restaurantLimit` в теле approve — высший приоритет."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(
        organization_id=org.id, user_id=user.id, period=3, requested_restaurant_limit=2
    )

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate", "restaurantLimit": 7},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["subscription"]["restaurantLimit"] == 7


async def test_approve_uses_requested_limit_when_no_override(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """Нет override → берётся `requested_restaurant_limit` (если > 0)."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(
        organization_id=org.id, user_id=user.id, period=3, requested_restaurant_limit=4
    )

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["subscription"]["restaurantLimit"] == 4


# ---------- approve: endDateOverride ----------


async def test_approve_with_end_date_override_seamless_no_period_increment(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """В seamless с override `period` НЕ инкрементится (override — источник правды)."""
    now = datetime.now(UTC)
    org = await make_organization()
    user = await make_user()
    sub = await make_subscription(
        organization_id=org.id,
        period=12,
        start_date=now - timedelta(days=5),
        end_date=now + timedelta(days=30),
        is_active=True,
    )
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=6)
    new_end = now + timedelta(days=200)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={
            "mode": "seamless",
            "endDateOverride": new_end.isoformat(),
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "seamless_extend"
    assert data["subscription"]["period"] == 12  # не изменён
    assert data["subscription"]["id"] == sub.id


async def test_approve_with_end_date_override_in_past_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """`endDateOverride <= now` → 400 InvalidEndDateOverride."""
    now = datetime.now(UTC)
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=3)
    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={
            "mode": "immediate",
            "endDateOverride": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert resp.status_code == 400


async def test_approve_with_end_date_override_before_start_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_subscription: SubscriptionFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """SEAMLESS с `endDateOverride <= active_sub.start_date` → 400."""
    now = datetime.now(UTC)
    org = await make_organization()
    user = await make_user()
    # Активная подписка стартовала далеко в будущем (синтетический кейс):
    # override в "позже now, но раньше start" должен дать 400.
    future_start = now + timedelta(days=60)
    await make_subscription(
        organization_id=org.id,
        period=12,
        start_date=future_start,
        end_date=future_start + timedelta(days=365),
        is_active=True,
    )
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=6)
    override = now + timedelta(days=30)  # > now, но < future_start

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "seamless", "endDateOverride": override.isoformat()},
    )
    assert resp.status_code == 400


# ---------- approve: гейты ----------


async def test_approve_already_completed_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """approve на не-pending заявке → 400 ExtensionRequestNotPending."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(
        organization_id=org.id, user_id=user.id, status="completed", period=3
    )
    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 400


async def test_approve_without_period_and_override_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """`period=0/None` и нет override → 400 ExtensionPeriodRequired."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=None)
    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 400


async def test_approve_with_null_byte_in_admin_comment_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """NUL-байт `\\x00` в `adminComment` → 400 InvalidStringCharacters."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=3)
    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate", "adminComment": "bad\x00comment"},
    )
    assert resp.status_code == 400


async def test_approve_404_for_missing_request(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.post(
        "/api/v1/subscriptions/extension/9999/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    assert resp.status_code == 404


# ---------- approve: subscriptions actually persisted ----------


async def test_approve_writes_admin_log_with_details(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """AdminLog approve содержит `mode`, `subscriptionId`, `organizationId`, `adminComment`."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=3)

    resp = await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate", "adminComment": "ok"},
    )
    assert resp.status_code == 200, resp.json()
    sub_id = resp.json()["data"]["subscription"]["id"]

    log = (
        await db_session.execute(
            select(AdminLogs).where(
                AdminLogs.entity_type == "subscription_extension_request",
                AdminLogs.entity_id == req.id,
            )
        )
    ).scalar_one()
    assert log.action == "update"
    assert log.details == {
        "mode": "immediate_new",
        "subscriptionId": sub_id,
        "organizationId": org.id,
        "adminComment": "ok",
    }


async def test_approve_immediate_new_creates_subscription_in_db(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_extension_request: ExtensionRequestFactory,
):
    """В БД появляется новая активная подписка после `approve immediate`."""
    org = await make_organization()
    user = await make_user()
    req = await make_extension_request(organization_id=org.id, user_id=user.id, period=3)
    await client.post(
        f"/api/v1/subscriptions/extension/{req.id}/approve",
        headers=auth_headers,
        json={"mode": "immediate"},
    )
    subs = (
        (
            await db_session.execute(
                select(Subscriptions).where(
                    Subscriptions.organization_id == org.id,
                    Subscriptions.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(subs) == 1
    assert subs[0].is_active is True
