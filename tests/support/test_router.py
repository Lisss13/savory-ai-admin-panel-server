"""E2E-тесты HTTP-эндпоинтов `/api/v1/support`.

По контракту воркспейса (см. `../CLAUDE.md`, gate в admin_panel_global)
этот модуль должен быть admin-only — поэтому в тестах все три эндпоинта
проверяются с Bearer-токеном.

Примечание: в текущем коде роутера зависимость `CurrentAdmin` закомменчена
на всех трёх эндпоинтах (см. ревью). Поэтому три теста группы «авторизация»
заведомо красные — это намеренно. Тесты кодируют целевой admin-only-контракт
по `../CLAUDE.md`, а не текущий баг.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service

from .conftest import TicketFactory


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="support-admin@savory.ai",
        password="topsecret",
        name="SupportAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "support-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- авторизация ----------


async def test_list_requires_admin_auth(client: AsyncClient):
    """GET /support без JWT → 401 (admin-only endpoint).

    NB: пока в роутере зависимость закомменчена — тест будет красным.
    Это сигнал к фиксу, а не повод ослабить тест.
    """
    resp = await client.get("/api/v1/support")
    assert resp.status_code == 401


async def test_get_requires_admin_auth(client: AsyncClient):
    """GET /support/{id} без JWT → 401.

    NB: пока в роутере зависимость закомменчена — тест будет красным.
    """
    resp = await client.get("/api/v1/support/1")
    assert resp.status_code == 401


async def test_patch_requires_admin_auth(client: AsyncClient):
    """PATCH /support/{id} без JWT → 401.

    NB: пока в роутере зависимость закомменчена — тест будет красным.
    """
    resp = await client.patch("/api/v1/support/1", json={"status": "in_progress"})
    assert resp.status_code == 401


# ---------- GET /support ----------


async def test_list_returns_envelope_with_camelcase_fields(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """Ответ обёрнут в `{data, messages, code}` и поля — camelCase.

    Сериализатор теперь отдаёт владельца как вложенный объект `user`
    (см. `SupportTicketResp` / `UserResp`), а не плоское `userId`.
    """
    await make_ticket(status="new", title="lone ticket")

    resp = await client.get("/api/v1/support", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1

    item = body["data"][0]
    # camelCase — обязательное соглашение воркспейса.
    assert "createdAt" in item
    assert "updatedAt" in item
    assert item["title"] == "lone ticket"
    assert item["status"] == "new"

    # Владелец — вложенный объект UserResp.
    assert isinstance(item["user"], dict)
    assert {"id", "email", "phone", "name", "company"} <= item["user"].keys()
    assert isinstance(item["user"]["id"], int)


async def test_list_orders_by_updated_at_desc(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """В ответе сначала свежее, в хвосте — старое."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(tz=UTC)
    older = await make_ticket(status="new", updated_at=now - timedelta(days=2))
    newest = await make_ticket(status="new", updated_at=now)
    middle = await make_ticket(status="new", updated_at=now - timedelta(days=1))

    resp = await client.get("/api/v1/support", headers=auth_headers)
    ids = [t["id"] for t in resp.json()["data"]]
    assert ids == [newest.id, middle.id, older.id]


async def test_list_excludes_soft_deleted(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """Soft-deleted тикет не виден через API."""
    from datetime import UTC, datetime

    visible = await make_ticket(status="new", title="visible")
    await make_ticket(status="new", title="hidden", deleted_at=datetime.now(tz=UTC))

    resp = await client.get("/api/v1/support", headers=auth_headers)
    ids = [t["id"] for t in resp.json()["data"]]
    assert ids == [visible.id]


async def test_list_filters_by_status_query_param(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """`?status=in_progress` — отдаёт только тикеты этого статуса."""
    await make_ticket(status="new", title="n")
    in_progress = await make_ticket(status="in_progress", title="ip")
    await make_ticket(status="completed", title="c")

    resp = await client.get("/api/v1/support?status=in_progress", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert [t["id"] for t in data] == [in_progress.id]


async def test_list_rejects_invalid_status_query_param(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """`?status=archived` (нет в enum) → 400 от Pydantic-валидации query."""
    resp = await client.get("/api/v1/support?status=archived", headers=auth_headers)
    assert resp.status_code == 400


# ---------- GET /support/{ticket_id} ----------


async def test_get_ticket_returns_envelope(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """Базовый кейс — тикет по id, ответ в envelope."""
    ticket = await make_ticket(status="new", title="findable")

    resp = await client.get(f"/api/v1/support/{ticket.id}", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["id"] == ticket.id
    assert body["data"]["title"] == "findable"


async def test_get_ticket_returns_404_for_unknown_id(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Несуществующий id → 404 + envelope с сообщением."""
    resp = await client.get("/api/v1/support/999999", headers=auth_headers)
    assert resp.status_code == 404

    body = resp.json()
    assert body["code"] == 404
    assert body["data"] is None
    assert body["messages"]


async def test_get_ticket_treats_soft_deleted_as_404(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """Soft-deleted → 404 (а не 200 с deleted_at)."""
    from datetime import UTC, datetime

    ticket = await make_ticket(status="new", title="dead", deleted_at=datetime.now(tz=UTC))
    resp = await client.get(f"/api/v1/support/{ticket.id}", headers=auth_headers)
    assert resp.status_code == 404


# ---------- PATCH /support/{ticket_id} ----------


async def test_patch_updates_status(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """Успешный patch меняет статус, в ответе — обновлённый тикет."""
    ticket = await make_ticket(status="new")

    resp = await client.patch(
        f"/api/v1/support/{ticket.id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["id"] == ticket.id
    assert body["data"]["status"] == "in_progress"


async def test_patch_returns_404_for_unknown_id(client: AsyncClient, auth_headers: dict[str, str]):
    """Patch несуществующего id → 404 в envelope."""
    resp = await client.patch(
        "/api/v1/support/999999",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
    assert body["data"] is None


async def test_patch_rejects_invalid_status(
    client: AsyncClient, auth_headers: dict[str, str], make_ticket: TicketFactory
):
    """`status` не из enum → 400 на уровне валидации тела."""
    ticket = await make_ticket(status="new")

    resp = await client.patch(
        f"/api/v1/support/{ticket.id}",
        json={"status": "archived"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------- audit log integration ----------


async def test_patch_writes_audit_log_record(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_ticket: TicketFactory,
):
    """Успешный PATCH создаёт строку в admin_logs с deталями из body."""
    from sqlalchemy import select

    from app.admin_log.models import AdminLogs

    ticket = await make_ticket(status="new")

    resp = await client.patch(
        f"/api/v1/support/{ticket.id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    log = (await db_session.execute(select(AdminLogs))).scalar_one()
    assert log.action == "update"
    assert log.entity_type == "support_ticket"
    assert log.entity_id == ticket.id
    assert log.details == {
        "before": {"status": "new"},
        "after": {"status": "in_progress"},
    }


async def test_patch_with_same_value_does_not_duplicate_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    make_ticket: TicketFactory,
):
    """Повторный PATCH с тем же значением → лог не пишется (фикс дублирования)."""
    from sqlalchemy import select

    from app.admin_log.models import AdminLogs

    ticket = await make_ticket(status="new")
    first = await client.patch(
        f"/api/v1/support/{ticket.id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = await client.patch(
        f"/api/v1/support/{ticket.id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert second.status_code == 200

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert len(logs) == 1


async def test_patch_404_does_not_write_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """404 (ticket не найден) — лог не пишем."""
    from sqlalchemy import select

    from app.admin_log.models import AdminLogs

    resp = await client.patch(
        "/api/v1/support/999999",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 404

    logs = (await db_session.execute(select(AdminLogs))).scalars().all()
    assert logs == []
