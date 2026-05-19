"""Параметризованный auth-тест для всех endpoints модуля subscriptions.

Один тест покрывает все 12 endpoints (8 admin/subscriptions + 4 extension-requests):
без `Authorization` каждый из них должен вернуть 401 — гарантирует, что ни один
эндпоинт не остался без `CurrentAdmin` dependency.
"""

import pytest
from httpx import AsyncClient

# (method, url, optional_body) для каждого endpoint. Body — минимальный валидный
# по схеме, чтобы 401 не маскировался 400-валидацией.
_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    # /subscriptions
    ("GET", "/api/v1/subscriptions", None),
    ("POST", "/api/v1/subscriptions", {"organizationId": 1, "period": 1}),
    # /subscriptions/extension
    ("GET", "/api/v1/subscriptions/extension", None),
    ("GET", "/api/v1/subscriptions/extension/1", None),
    ("POST", "/api/v1/subscriptions/extension/1/reject", {}),
    (
        "POST",
        "/api/v1/subscriptions/extension/1/approve",
        {"mode": "seamless"},
    ),
]


@pytest.mark.parametrize(
    "method,url,body", _ENDPOINTS, ids=lambda v: v if isinstance(v, str) else ""
)
async def test_endpoint_requires_admin_auth(
    client: AsyncClient, method: str, url: str, body: dict | None
):
    """Любой endpoint модуля без Bearer-токена → 401."""
    resp = await client.request(method, url, json=body)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,url,body", _ENDPOINTS)
async def test_endpoint_rejects_garbage_token(
    client: AsyncClient, method: str, url: str, body: dict | None
):
    """Мусорный Bearer-токен → 401 (не 500, не 400)."""
    resp = await client.request(
        method, url, json=body, headers={"Authorization": "Bearer garbage-not-jwt"}
    )
    assert resp.status_code == 401
