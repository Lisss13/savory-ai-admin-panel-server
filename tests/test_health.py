import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok_status(client: AsyncClient):
    """Эндпоинт `/health` отвечает 200 и сообщает статус БД в envelope."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["messages"] == []
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] in {"ok", "down"}


@pytest.mark.asyncio
async def test_unknown_route_returns_envelope_error(client: AsyncClient):
    """404 от FastAPI тоже приходит в форме envelope."""
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body == {"data": None, "messages": ["Not Found"], "code": 404}
