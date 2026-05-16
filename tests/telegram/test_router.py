"""E2E-тесты HTTP-эндпоинта `GET /api/v1/telegram`.

Покрывают:
- admin-only-контракт (без JWT → 401);
- envelope-форму ответа и camelCase-сериализацию;
- сортировку `chat_id ASC`;
- nullable-поля (`username` / `firstName`) — регрессия на баг с
  `ResponseValidationError`, из-за которого ранее /telegram отдавал 500;
- сериализацию `createdAt` в ISO-строку (а не сырой `datetime`).
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service

from .conftest import SubscriberFactory


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="telegram-admin@savory.ai",
        password="topsecret",
        name="TelegramAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "telegram-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- авторизация ----------


async def test_list_requires_admin_auth(client: AsyncClient):
    """GET /telegram без JWT → 401 (admin-only endpoint)."""
    resp = await client.get("/api/v1/telegram")
    assert resp.status_code == 401


async def test_list_rejects_invalid_bearer(client: AsyncClient):
    """Мусорный Bearer-токен → 401, без падения в 500."""
    resp = await client.get(
        "/api/v1/telegram",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------- успешные ответы ----------


async def test_list_returns_envelope_with_camelcase_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_subscriber: SubscriberFactory,
):
    """Ответ обёрнут в `{data, messages, code}`, поля сериализованы в camelCase."""
    created = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    await make_subscriber(
        chat_id=555,
        username="alice",
        first_name="Alice",
        created_at=created,
    )

    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1

    item = body["data"][0]
    # Контракт воркспейса: новые поля — camelCase.
    assert "chatId" in item
    assert "firstName" in item
    assert "createdAt" in item
    # snake_case-вариантов в ответе быть не должно.
    assert "chat_id" not in item
    assert "first_name" not in item
    assert "created_at" not in item

    assert item["chatId"] == 555
    assert item["username"] == "alice"
    assert item["firstName"] == "Alice"


async def test_list_orders_by_chat_id_ascending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_subscriber: SubscriberFactory,
):
    """Сортировка `chat_id ASC` — наименьший chat_id первым, независимо от порядка вставки."""
    await make_subscriber(chat_id=300)
    await make_subscriber(chat_id=100)
    await make_subscriber(chat_id=200)

    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    chat_ids = [s["chatId"] for s in resp.json()["data"]]
    assert chat_ids == [100, 200, 300]


async def test_list_serializes_null_username_and_first_name(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_subscriber: SubscriberFactory,
):
    """Регрессия: `username` / `firstName` = `None` не валит ответ 500.

    Раньше схема объявляла их как `str`, и Pydantic v2 отказывался
    сериализовать `None` — endpoint падал с `ResponseValidationError`.
    """
    await make_subscriber(chat_id=1, username=None, first_name=None)

    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert item["username"] is None
    assert item["firstName"] is None


async def test_list_serializes_created_at_as_iso_string(
    client: AsyncClient,
    auth_headers: dict[str, str],
    make_subscriber: SubscriberFactory,
):
    """`createdAt` сериализуется в ISO-строку (Pydantic v2 не отдаёт сырой `datetime`)."""
    await make_subscriber(chat_id=1, created_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC))

    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert isinstance(item["createdAt"], str)
    # ISO 8601 — должен парситься обратно в datetime. Сравниваем по wall-clock,
    # потому что SQLite в тестах не хранит tzinfo (в проде Postgres хранит).
    parsed = datetime.fromisoformat(item["createdAt"])
    assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (
        2026,
        5,
        1,
        12,
        0,
    )


async def test_list_serializes_null_created_at(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """`createdAt` в БД nullable — отдаётся как `null`, не валит ответ 500."""
    from app.models import TelegramSubscribers

    db_session.add(TelegramSubscribers(chat_id=1, username=None, first_name=None, created_at=None))
    await db_session.commit()

    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    item = resp.json()["data"][0]
    assert item["createdAt"] is None


async def test_list_returns_empty_list_when_no_subscribers(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Без подписчиков — `data: []`, не `null`."""
    resp = await client.get("/api/v1/telegram", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == []
