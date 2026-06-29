from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"status": "ok"}


async def test_health_content_type_is_json(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert "application/json" in resp.headers["content-type"]
