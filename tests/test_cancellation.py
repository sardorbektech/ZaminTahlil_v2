"""Bekor qilish: ~2 soniyada vazifa to'xtaydi, fayllar va DB qatorlari o'chiriladi, `cancelled` hodisasi."""

import asyncio
import time

from httpx import AsyncClient

from backend.app.db import session as db
from backend.app.db.models import RunModel
from backend.app.pipeline import storage as st
from backend.app.pipeline.jobs import job_manager
from tests.conftest import AOI


async def test_cancel_cleans_files_rows_and_unlocks(client: AsyncClient, isolated_env):
    isolated_env["source"].delay_s = 0.4
    rid = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    job = job_manager.get_job(rid)
    # Yuklash bosqichi boshlanguncha kutish (fayllar diskda paydo bo'ladi)
    for _ in range(200):
        if st.run_dir(rid).exists():
            break
        await asyncio.sleep(0.02)
    assert st.run_dir(rid).exists()

    t0 = time.perf_counter()
    r = await client.post(f"/api/v1/recon/{rid}/cancel")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200 and r.json()["cancelled"] is True
    assert elapsed < 2.5
    assert job is not None and job.task is not None and job.task.done()
    assert job.events[-1]["type"] == "cancelled"
    assert not st.run_dir(rid).exists()
    async with db.session_scope() as s:
        assert await s.get(RunModel, rid) is None
    assert job_manager.active_run_id() is None
    assert (await client.get("/api/v1/recon/active")).json()["active"] is False

    # Qayta bekor qilish — faol emas
    again = await client.post(f"/api/v1/recon/{rid}/cancel")
    assert again.status_code == 409

    # Yangi run boshlash mumkin
    isolated_env["source"].delay_s = 0.0
    r2 = await client.post("/api/v1/recon", json={"aoi": AOI})
    assert r2.status_code == 200
