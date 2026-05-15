"""E2E-тесты HTTP-эндпоинтов `/api/v1/admin/logs`."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    await admin_service.create_admin(
        db_session,
        email="log-admin@savory.ai",
        password="topsecret",
        name="LogAdmin",
    )
    await db_session.commit()
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "log-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


async def test_list_requires_admin_auth(client: AsyncClient):
    """GET /admin/logs без JWT → 401."""
    resp = await client.get("/api/v1/admin/logs")
    assert resp.status_code == 401


async def test_my_requires_admin_auth(client: AsyncClient):
    """GET /admin/logs/me без JWT → 401."""
    resp = await client.get("/api/v1/admin/logs/me")
    assert resp.status_code == 401


async def test_list_returns_envelope_with_camelcase(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    """Ответ — envelope `{data: {items, page, pageSize, total}}`, поля camelCase."""
    # Кладём админа-автора лога (того же, который под токеном) — id берём из БД.
    from sqlalchemy import select

    from app.admin.models import Admin

    admin = (await db_session.execute(select(Admin))).scalar_one()
    await admin_log_service.log_action(
        db_session,
        admin_id=admin.id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.SUPPORT_TICKET,
        entity_id=1,
        details={"status": "in_progress"},
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    resp = await client.get("/api/v1/admin/logs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert {"items", "page", "pageSize", "total"} <= data.keys()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["adminId"] == admin.id
    assert item["adminEmail"] == "log-admin@savory.ai"
    assert item["action"] == "update"
    assert item["entityType"] == "support_ticket"
    assert item["entityId"] == 1
    # details клиент получает уже распарсенным объектом, а не строкой.
    assert item["details"] == {"status": "in_progress"}
    assert item["ipAddress"] == "10.0.0.1"
    assert "createdAt" in item


async def test_my_shows_only_current_admin_records(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    """/admin/logs/me возвращает только записи текущего админа."""
    from sqlalchemy import select

    from app.admin.models import Admin

    current = (await db_session.execute(select(Admin))).scalar_one()
    # Второй админ, его записи не должны попасть в /me.
    other = await admin_service.create_admin(
        db_session,
        email="other@savory.ai",
        password="topsecret",
        name="Other",
    )
    await db_session.commit()

    await admin_log_service.log_action(
        db_session,
        admin_id=current.id,
        action=AdminAction.CREATE,
        entity_type=EntityType.LANGUAGE,
        entity_id=1,
        details={"code": "de"},
        ip_address=None,
    )
    await admin_log_service.log_action(
        db_session,
        admin_id=other.id,
        action=AdminAction.CREATE,
        entity_type=EntityType.LANGUAGE,
        entity_id=2,
        details={"code": "fr"},
        ip_address=None,
    )
    await db_session.commit()

    resp = await client.get("/api/v1/admin/logs/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["adminId"] == current.id


async def test_pagination_respects_query_params(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    """?page=2&pageSize=1 возвращает один элемент, total корректный."""
    from sqlalchemy import select

    from app.admin.models import Admin

    admin = (await db_session.execute(select(Admin))).scalar_one()
    for i in range(3):
        await admin_log_service.log_action(
            db_session,
            admin_id=admin.id,
            action=AdminAction.UPDATE,
            entity_type=EntityType.SUPPORT_TICKET,
            entity_id=i,
            details=None,
            ip_address=None,
        )
    await db_session.commit()

    resp = await client.get("/api/v1/admin/logs?page=2&pageSize=1", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert data["page"] == 2
    assert data["pageSize"] == 1
    assert len(data["items"]) == 1


async def test_pagination_rejects_invalid_values(client: AsyncClient, auth_headers: dict[str, str]):
    """page<1 или pageSize>100 → 400 от валидатора."""
    resp = await client.get("/api/v1/admin/logs?page=0", headers=auth_headers)
    assert resp.status_code == 400

    resp = await client.get("/api/v1/admin/logs?pageSize=999", headers=auth_headers)
    assert resp.status_code == 400
