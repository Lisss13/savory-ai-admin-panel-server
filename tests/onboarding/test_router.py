"""E2E-тесты HTTP-эндпоинтов `/api/v1/onboarding` + интеграция с audit-логом."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin_log.models import AdminLogs
from app.models import OnboardingRequests


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    await admin_service.create_admin(
        db_session,
        email="ob-admin@savory.ai",
        password="topsecret",
        name="OnboardingAdmin",
    )
    await db_session.commit()
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ob-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
async def make_request(db_session: AsyncSession):
    """Фабрика онбординг-заявок для тестов."""
    counter = {"n": 0}

    async def _factory(
        *,
        name: str = "John",
        phone: str = "+1234567890",
        email: str = "john@example.com",
        status: str = "new",
    ) -> OnboardingRequests:
        idx = counter["n"]
        counter["n"] += 1
        now = datetime.now(tz=UTC)
        req = OnboardingRequests(
            name=f"{name}-{idx}",
            phone=phone,
            email=email,
            status=status,
            created_at=now,
            updated_at=now,
        )
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)
        return req

    return _factory


async def test_patch_writes_audit_log_record(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request,
):
    """Успешный PATCH создаёт строку в admin_logs с правильными деталями."""
    request = await make_request(status="new")

    resp = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.action == "update"
    assert log.entity_type == "onboarding_request"
    assert log.entity_id == request.id
    assert log.details == {
        "before": {"status": "new"},
        "after": {"status": "contacted"},
    }


async def test_patch_with_same_value_does_not_duplicate_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request,
):
    """Повторный PATCH с тем же телом → лог не пишется (фикс дублирования)."""
    request = await make_request(status="new")

    first = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert second.status_code == 200

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert len(logs) == 1


async def test_patch_records_client_ip_from_forwarded_for(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request,
):
    """ip_address берётся из X-Forwarded-For (важно для Railway-деплоя за прокси)."""
    request = await make_request(status="new")

    headers = {**auth_headers, "X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    resp = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={"status": "contacted"},
        headers=headers,
    )
    assert resp.status_code == 200

    log = (await db_session.execute(select(AdminLogs))).scalar_one()
    assert log.ip_address == "203.0.113.10"


async def test_patch_with_empty_body_does_not_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request,
):
    """Пустой PATCH (без полей) — не действие, в журнал ничего не пишем."""
    request = await make_request(status="new")

    resp = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert logs == []


async def test_patch_404_does_not_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Failed mutation (404 на несуществующий id) — в журнал ничего не пишем."""
    resp = await client.patch(
        "/api/v1/onboarding/999999",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert resp.status_code == 404

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert logs == []
