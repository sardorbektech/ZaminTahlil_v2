"""Umumiy test sozlamalari: vaqtinchalik ma'lumot katalogi, alohida SQLite, soxta GEE va AI, tarmoq bloki."""

import asyncio
import base64
import os
import tempfile

# Ilova modullari import qilinishidan OLDIN: ma'lumotlar haqiqiy data/ katalogiga yozilmasin
os.environ["ZT_DATA_DIR"] = tempfile.mkdtemp(prefix="zt_test_")
os.environ["LOG_TO_CONSOLE"] = "false"

from collections.abc import AsyncGenerator  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.app.ai import chat as chat_module  # noqa: E402
from backend.app.ai import report_generator  # noqa: E402
from backend.app.core import config  # noqa: E402
from backend.app.core.time import now_ts  # noqa: E402
from backend.app.db import session as db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.pipeline import deps  # noqa: E402
from backend.app.pipeline.jobs import job_manager  # noqa: E402
from tests.fakes import FakeAIClient, FakeSource  # noqa: E402

AOI = {
    "type": "Polygon",
    "coordinates": [[[69.24, 41.33], [69.246, 41.33], [69.246, 41.334], [69.24, 41.334], [69.24, 41.33]]],
}


@pytest.fixture
def fake_ai() -> FakeAIClient:
    return FakeAIClient()


@pytest_asyncio.fixture(autouse=True)
async def isolated_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, fake_ai: FakeAIClient) -> AsyncGenerator[dict[str, Any], None]:
    """Har bir test: alohida katalog va baza, soxta manba, tarmoq taqiqlangan."""
    runs, logs = tmp_path / "runs", tmp_path / "logs" / "api_calls"
    runs.mkdir(parents=True)
    logs.mkdir(parents=True)
    monkeypatch.setattr(config, "RUNS_DIR", runs)
    monkeypatch.setattr(config, "API_CALLS_LOG_DIR", logs)

    async def _no_network(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("Testlarda tarmoqqa chiqish taqiqlangan")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _no_network)
    monkeypatch.setattr(report_generator, "ai_client", fake_ai)
    monkeypatch.setattr(chat_module, "ai_client", fake_ai)

    db.configure_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite'}")
    await db.init_db()
    job_manager.active, job_manager.last = None, None
    job_manager._lock = asyncio.Lock()
    source = FakeSource(now=now_ts())
    deps.set_data_source(source, None)
    yield {"source": source, "runs": runs, "logs": logs, "tmp": tmp_path}
    await job_manager.shutdown()
    await db.engine.dispose()


def basic(username: str, password: str) -> dict[str, str]:
    """HTTP Basic sarlavhasi (UTF-8)."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def make_client(username: str = "tester", password: str = "p") -> AsyncClient:
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=basic(username, password))
    r = await ac.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return ac


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    ac = await make_client()
    try:
        yield ac
    finally:
        await ac.aclose()


@pytest_asyncio.fixture
async def anon() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def wait_for_run(run_id: int, timeout: float = 30.0) -> dict[str, Any]:
    """Run yakuniy hodisasini kutadi va uni qaytaradi."""
    job = job_manager.get_job(run_id)
    assert job is not None
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not job.finished:
        if loop.time() > end:
            raise TimeoutError("Run tugamadi")
        await asyncio.sleep(0.02)
    if job.task is not None:
        await asyncio.wait_for(asyncio.shield(job.task), timeout=timeout)
    return job.events[-1]
