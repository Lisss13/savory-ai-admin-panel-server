"""E2E-тесты HTTP-эндпоинтов `/api/v1/onboarding` + интеграция с audit-логом."""

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log.models import AdminLogs

from .conftest import RequestFactory


async def test_patch_writes_audit_log_record(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request: RequestFactory,
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
    make_request: RequestFactory,
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
    make_request: RequestFactory,
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
    make_request: RequestFactory,
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


async def test_patch_treats_soft_deleted_as_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request: RequestFactory,
):
    """Soft-deleted заявку нельзя патчить — должно быть 404, как и в GET.

    Контракт согласован с `get_onboarding_request_by_id` (см. тест
    `test_get_by_id_treats_soft_deleted_as_404` ниже): если заявка
    помечена `deleted_at IS NOT NULL`, она «не существует» для админ-API
    и в журнал аудита ничего писаться не должно.
    """
    request = await make_request(status="new", deleted_at=datetime.now(tz=UTC))

    resp = await client.patch(
        f"/api/v1/onboarding/{request.id}",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert resp.status_code == 404

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert logs == []


# ---------- GET /onboarding/{onboarding_id} ----------


async def test_get_by_id_requires_admin_auth(client: AsyncClient):
    """GET /onboarding/{id} без JWT → 401 (admin-only endpoint)."""
    resp = await client.get("/api/v1/onboarding/1")
    assert resp.status_code == 401


async def test_get_by_id_returns_envelope_with_camelcase_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_request: RequestFactory,
):
    """Ответ обёрнут в `{data, messages, code}`, поля сериализованы в camelCase."""
    request = await make_request(status="new", name="Alice")

    resp = await client.get(f"/api/v1/onboarding/{request.id}", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert isinstance(body["data"], dict)

    item = body["data"]
    # Контракт воркспейса: новые поля — camelCase.
    assert "createdAt" in item
    assert "created_at" not in item
    assert item["id"] == request.id
    assert item["status"] == "new"
    assert item["phone"] == request.phone
    assert item["email"] == request.email
    assert item["name"] == request.name


async def test_get_by_id_returns_404_for_unknown_id(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Несуществующий id → 404 в envelope-формате."""
    resp = await client.get("/api/v1/onboarding/999999", headers=auth_headers)
    assert resp.status_code == 404

    body = resp.json()
    assert body["code"] == 404
    assert body["data"] is None
    assert body["messages"]


async def test_get_by_id_treats_soft_deleted_as_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_request: RequestFactory,
):
    """Soft-deleted заявка → 404 (а не 200 с заполненным `deletedAt`)."""
    request = await make_request(status="new", deleted_at=datetime.now(tz=UTC))

    resp = await client.get(f"/api/v1/onboarding/{request.id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_by_id_returns_only_requested_record(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_request: RequestFactory,
):
    """В БД несколько заявок — endpoint возвращает ровно ту, что в пути."""
    await make_request(status="new", name="First")
    target = await make_request(status="contacted", name="Target")
    await make_request(status="installed", name="Third")

    resp = await client.get(f"/api/v1/onboarding/{target.id}", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["id"] == target.id
    assert data["status"] == "contacted"


async def test_get_by_id_rejects_non_integer_id(client: AsyncClient, auth_headers: dict[str, str]):
    """`{id}` — int в роуте; нечисловое значение → 400 от валидации path."""
    resp = await client.get("/api/v1/onboarding/abc", headers=auth_headers)
    assert resp.status_code == 400


async def test_get_by_id_does_not_write_audit_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_request: RequestFactory,
):
    """Read-операция не должна писать в `admin_logs` (журналим только мутации)."""
    request = await make_request(status="new")

    resp = await client.get(f"/api/v1/onboarding/{request.id}", headers=auth_headers)
    assert resp.status_code == 200

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert logs == []
