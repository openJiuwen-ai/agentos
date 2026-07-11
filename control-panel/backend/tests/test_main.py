"""FastAPI 应用端点测试。

使用 httpx ASGITransport 在进程内测试，无需启动真实服务器。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root():
    """GET / → 返回服务名称和版本号。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "AgentOS Panel" in data["service"]
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health():
    """GET /health → 返回 {"status": "ok"}。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
