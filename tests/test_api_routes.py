"""FastAPI endpointlarini integratsion tekshirish testlari."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_settings(client: AsyncClient):
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "lookback_days" in data
    assert data["lookback_days"] == 10


@pytest.mark.asyncio
async def test_get_active_recon_empty(client: AsyncClient):
    resp = await client.get("/api/v1/recon/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is False


@pytest.mark.asyncio
async def test_get_usage_summary(client: AsyncClient):
    resp = await client.get("/api/v1/usage/runs/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == 1
    assert "markdown_report" in data
