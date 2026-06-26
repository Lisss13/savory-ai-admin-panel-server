"""HTTP-тесты `/api/v1/ai-topup/*`.

Покрывают:
- envelope + camelCase + фильтры + дефолт `status=pending` + пагинация + soft-delete;
- approve pending → `approved`, `processedAt` заполнен, создана одна квота с
  `requestsGranted = packsCount * requestsPerPack`, `expiresAt` = начало след. месяца;
- approve не-pending → 409, квота не создаётся; идемпотентность повторного approve;
- reject pending → `rejected`, квоты нет; reject не-pending → 409;
- NUL-байт в adminComment → 400; AdminLog на каждую мутацию.

Admin-only auth проверяется отдельно (см. модульные auth-тесты воркспейса).
"""

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log.models import AdminLogs
from app.ai_topup.helpers import next_month_start
from app.models import AIRequestQuotas

from .conftest import (
    OrganizationFactory,
    RestaurantFactory,
    TopUpRequestFactory,
    UserFactory,
)

# ---------- список ----------


async def test_list_returns_envelope_with_camel_case(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id, name="Saffron")
    await make_top_up_request(
        organization_id=org.id,
        restaurant_id=rest.id,
        user_id=user.id,
        packs_count=3,
        requests_per_pack=5000,
        price_per_pack=40,
    )

    resp = await client.get("/api/v1/ai-topup/requests", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["code"] == 200 and body["messages"] == []
    data = body["data"]
    assert data["total"] == 1 and data["limit"] == 10 and data["offset"] == 0

    item = data["items"][0]
    assert item["status"] == "pending"
    assert item["packsCount"] == 3
    assert item["requestsPerPack"] == 5000
    assert item["pricePerPack"] == 40
    assert item["totalPrice"] == 120
    assert item["currency"] == "USD"
    assert item["organization"]["id"] == org.id
    assert item["restaurant"]["id"] == rest.id and item["restaurant"]["name"] == "Saffron"
    assert item["user"]["id"] == user.id


async def test_list_default_status_is_pending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="pending"
    )
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="approved"
    )
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="rejected"
    )

    resp = await client.get("/api/v1/ai-topup/requests", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["status"] == "pending"


async def test_list_filters_by_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="pending"
    )
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="rejected"
    )

    resp = await client.get("/api/v1/ai-topup/requests?status=rejected", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1 and items[0]["status"] == "rejected"


async def test_list_hides_soft_deleted(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="pending"
    )
    await make_top_up_request(
        organization_id=org.id,
        restaurant_id=rest.id,
        user_id=user.id,
        status="pending",
        deleted_at=datetime.now(UTC),
    )

    resp = await client.get("/api/v1/ai-topup/requests", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


async def test_list_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    for _ in range(3):
        await make_top_up_request(
            organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="pending"
        )

    resp = await client.get("/api/v1/ai-topup/requests?limit=1&offset=1", headers=auth_headers)
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["limit"] == 1 and data["offset"] == 1 and data["total"] == 3
    assert len(data["items"]) == 1


# ---------- get by id ----------


async def test_get_by_id_404_for_missing(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/v1/ai-topup/requests/9999", headers=auth_headers)
    assert resp.status_code == 404


# ---------- approve ----------


async def test_approve_pending_creates_quota(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """Approve pending → status=approved, processedAt заполнен, одна квота."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(
        organization_id=org.id,
        restaurant_id=rest.id,
        user_id=user.id,
        packs_count=3,
        requests_per_pack=5000,
    )

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve",
        headers=auth_headers,
        json={"adminComment": "approved by phone"},
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["topUpRequest"]["status"] == "approved"
    assert data["topUpRequest"]["adminComment"] == "approved by phone"
    assert data["topUpRequest"]["processedAt"] is not None
    assert data["quota"]["requestsGranted"] == 3 * 5000

    # В БД ровно одна квота с верным requests_granted.
    quotas = (
        (
            await db_session.execute(
                select(AIRequestQuotas).where(AIRequestQuotas.top_up_request_id == req.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(quotas) == 1
    assert quotas[0].requests_granted == 3 * 5000
    assert quotas[0].restaurant_id == rest.id


async def test_approve_quota_expires_at_next_month_start(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """`expiresAt` квоты == начало следующего календарного месяца (UTC)."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(organization_id=org.id, restaurant_id=rest.id, user_id=user.id)

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve", headers=auth_headers, json={}
    )
    assert resp.status_code == 200, resp.json()

    expected = next_month_start(datetime.now(UTC))
    expires_iso = resp.json()["data"]["quota"]["expiresAt"]
    expires_dt = datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
    # Сравниваем по компонентам календаря — момент апрува тот же месяц.
    assert (expires_dt.year, expires_dt.month, expires_dt.day) == (
        expected.year,
        expected.month,
        expected.day,
    )
    assert expires_dt.hour == 0 and expires_dt.minute == 0


async def test_approve_non_pending_returns_409_no_quota(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """Approve уже approved/rejected заявки → 409, квота не создаётся."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="rejected"
    )

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve", headers=auth_headers, json={}
    )
    assert resp.status_code == 409, resp.json()

    count = (
        await db_session.execute(select(func.count()).select_from(AIRequestQuotas))
    ).scalar_one()
    assert count == 0


async def test_double_approve_is_idempotent_one_quota(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """Повторный approve той же заявки → 409 (статус-гейт), квота ровно одна."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(organization_id=org.id, restaurant_id=rest.id, user_id=user.id)

    first = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve", headers=auth_headers, json={}
    )
    assert first.status_code == 200, first.json()
    second = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve", headers=auth_headers, json={}
    )
    assert second.status_code == 409, second.json()

    count = (
        await db_session.execute(select(func.count()).select_from(AIRequestQuotas))
    ).scalar_one()
    assert count == 1


async def test_approve_404_for_missing(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.post(
        "/api/v1/ai-topup/requests/9999/approve", headers=auth_headers, json={}
    )
    assert resp.status_code == 404


async def test_approve_with_null_byte_in_admin_comment_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(organization_id=org.id, restaurant_id=rest.id, user_id=user.id)
    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve",
        headers=auth_headers,
        json={"adminComment": "bad\x00comment"},
    )
    assert resp.status_code == 400


async def test_approve_writes_admin_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """AdminLog approve: entity_type=ai_topup_request, action=update, details."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(
        organization_id=org.id,
        restaurant_id=rest.id,
        user_id=user.id,
        packs_count=2,
        requests_per_pack=5000,
    )

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/approve", headers=auth_headers, json={}
    )
    assert resp.status_code == 200, resp.json()

    log = (
        await db_session.execute(
            select(AdminLogs).where(
                AdminLogs.entity_type == "ai_topup_request",
                AdminLogs.entity_id == req.id,
            )
        )
    ).scalar_one()
    assert log.action == "update"
    assert log.details["status"] == "approved"
    assert log.details["requestsGranted"] == 2 * 5000
    assert log.details["restaurantId"] == rest.id


# ---------- reject ----------


async def test_reject_pending_no_quota(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    """Reject pending → status=rejected, processedAt заполнен, квоты нет."""
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(organization_id=org.id, restaurant_id=rest.id, user_id=user.id)

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/reject",
        headers=auth_headers,
        json={"adminComment": "no budget"},
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["status"] == "rejected" and data["adminComment"] == "no budget"
    assert data["processedAt"] is not None

    count = (
        await db_session.execute(select(func.count()).select_from(AIRequestQuotas))
    ).scalar_one()
    assert count == 0


async def test_reject_non_pending_returns_409(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(
        organization_id=org.id, restaurant_id=rest.id, user_id=user.id, status="approved"
    )
    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/reject", headers=auth_headers, json={}
    )
    assert resp.status_code == 409


async def test_reject_writes_admin_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_user: UserFactory,
    make_organization: OrganizationFactory,
    make_restaurant: RestaurantFactory,
    make_top_up_request: TopUpRequestFactory,
):
    org = await make_organization()
    user = await make_user()
    rest = await make_restaurant(organization_id=org.id)
    req = await make_top_up_request(organization_id=org.id, restaurant_id=rest.id, user_id=user.id)

    resp = await client.post(
        f"/api/v1/ai-topup/requests/{req.id}/reject", headers=auth_headers, json={}
    )
    assert resp.status_code == 200, resp.json()

    log = (
        await db_session.execute(
            select(AdminLogs).where(
                AdminLogs.entity_type == "ai_topup_request",
                AdminLogs.entity_id == req.id,
            )
        )
    ).scalar_one()
    assert log.action == "update"
    assert log.details["status"] == "rejected"
