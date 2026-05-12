"""E2E-тесты HTTP-эндпоинтов `/api/v1/languages`.

Покрывают:
- доступ строго по админскому JWT (без токена — 401),
- создание/листинг/удаление,
- envelope-формат ответа,
- бизнес-правила (дубликат code → 409, удаление `en` → 409, мусорный id → 404).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Заводит админа и логинит — возвращает Bearer-токен."""
    await admin_service.create_admin(
        db_session,
        email="lang-admin@savory.ai",
        password="topsecret",
        name="LangAdmin",
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "lang-admin@savory.ai", "password": "topsecret"},
    )
    return str(resp.json()["data"]["accessToken"])


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


async def test_list_requires_admin_auth(client: AsyncClient):
    """Без JWT — 401, доступ только для админа."""
    resp = await client.get("/api/v1/languages")
    assert resp.status_code == 401


async def test_create_requires_admin_auth(client: AsyncClient):
    """POST без JWT — тоже 401."""
    resp = await client.post(
        "/api/v1/languages",
        json={"code": "fr", "name": "French"},
    )
    assert resp.status_code == 401


async def test_delete_requires_admin_auth(client: AsyncClient):
    """DELETE без JWT — 401."""
    resp = await client.delete("/api/v1/languages/1")
    assert resp.status_code == 401


async def test_create_language_returns_201_envelope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Успешное создание → 201 + envelope с camelCase-полями."""
    resp = await client.post(
        "/api/v1/languages",
        json={"code": "fr", "name": "French", "description": "Français"},
        headers=auth_headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 201
    assert body["messages"] == []

    data = body["data"]
    assert isinstance(data["id"], int) and data["id"] > 0
    assert data["code"] == "fr"
    assert data["name"] == "French"
    assert data["description"] == "Français"
    # camelCase в Response — обязательное соглашение воркспейса.
    assert "createdAt" in data
    assert "updatedAt" in data


async def test_create_language_validates_code_format(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Не-ISO 639-1 код (длина / регистр) → 400 от валидатора."""
    resp = await client.post(
        "/api/v1/languages",
        json={"code": "EN", "name": "English"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    resp = await client.post(
        "/api/v1/languages",
        json={"code": "eng", "name": "English"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_create_language_rejects_duplicate(client: AsyncClient, auth_headers: dict[str, str]):
    """Повторный POST с тем же `code` → 409."""
    payload = {"code": "de", "name": "German"}
    first = await client.post("/api/v1/languages", json=payload, headers=auth_headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/languages", json=payload, headers=auth_headers)
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == 409
    assert body["data"] is None
    assert body["messages"]


async def test_list_languages_returns_only_active(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """GET возвращает только активные (не soft-deleted) языки."""
    await client.post(
        "/api/v1/languages",
        json={"code": "es", "name": "Spanish"},
        headers=auth_headers,
    )
    created = await client.post(
        "/api/v1/languages",
        json={"code": "it", "name": "Italian"},
        headers=auth_headers,
    )
    italian_id = created.json()["data"]["id"]

    deleted = await client.delete(
        f"/api/v1/languages/{italian_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 200

    resp = await client.get("/api/v1/languages", headers=auth_headers)
    assert resp.status_code == 200
    codes = {lang["code"] for lang in resp.json()["data"]}
    assert codes == {"es"}


async def test_delete_default_language_returns_409(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Удаление `en` запрещено — 409 даже для админа."""
    created = await client.post(
        "/api/v1/languages",
        json={"code": "en", "name": "English"},
        headers=auth_headers,
    )
    en_id = created.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/languages/{en_id}", headers=auth_headers)
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == 409
    assert body["messages"]


async def test_delete_unknown_language_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Несуществующий id → 404 в envelope-формате (а не 500 на валидации респонса)."""
    resp = await client.delete("/api/v1/languages/999999", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
    assert body["data"] is None
    assert body["messages"]


async def test_delete_language_returns_id_envelope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Успешное удаление → 200 + `{id}` в envelope."""
    created = await client.post(
        "/api/v1/languages",
        json={"code": "pt", "name": "Portuguese"},
        headers=auth_headers,
    )
    lang_id = created.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/languages/{lang_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == {"id": lang_id}
