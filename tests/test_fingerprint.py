"""Barmoq izi: deterministiklik, dublikat run'ni aniqlash va hisobotni bir marta yaratish qoidasi."""

from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.db import session as db
from backend.app.db.models import ReportModel, RunModel
from backend.app.pipeline import storage as st
from backend.app.pipeline.fingerprint import compute_recon_fingerprint
from tests.conftest import AOI, wait_for_run


def test_fingerprint_deterministic_and_order_independent():
    fp1 = compute_recon_fingerprint(AOI, ["S2_b", "S2_a", "S1_a"])
    fp2 = compute_recon_fingerprint(AOI, ["S1_a", "S2_a", "S2_b"])
    assert fp1 == fp2 and len(fp1) == 32
    assert compute_recon_fingerprint(AOI, ["S2_a"]) != fp1


async def test_duplicate_run_shows_existing(client: AsyncClient, isolated_env, fake_ai):
    r1 = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    assert (await wait_for_run(r1))["type"] == "done"
    r2 = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    ev = await wait_for_run(r2)
    assert ev["type"] == "duplicate" and ev["message_uz"] == "Yangi sunʼiy yoʻldosh maʼlumoti yoʻq"
    assert ev["data"]["existing_run_id"] == r1
    async with db.session_scope() as s:
        assert await s.get(RunModel, r2) is None  # dublikat run saqlanmaydi
    assert not st.run_dir(r2).exists()
    assert fake_ai.calls == 1  # hisobot faqat birinchi run uchun

    # Yangi kadr paydo bo'lsa — yangi run va yangi hisobot
    isolated_env["source"].scene_suffix = "new"
    r3 = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    assert (await wait_for_run(r3))["type"] == "done"
    assert fake_ai.calls == 2


async def test_report_once_per_fingerprint_and_retry_after_failure(client: AsyncClient, fake_ai):
    fake_ai.fail_times = 1  # quvurdagi birinchi urinish muvaffaqiyatsiz
    rid = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    ev = await wait_for_run(rid)
    assert ev["type"] == "done"  # AI xatosi run'ni buzmaydi
    rep = (await client.get(f"/api/v1/recon/{rid}/report")).json()
    assert rep["status"] == "failed" and rep["error"]

    retry = await client.post(f"/api/v1/recon/{rid}/report")
    assert retry.status_code == 200 and retry.json()["status"] == "ok" and retry.json()["attempts"] == 2

    again = await client.post(f"/api/v1/recon/{rid}/report")
    assert again.status_code == 409 and again.json()["code"] == "REPORT_EXISTS"
    async with db.session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(ReportModel))).scalar() == 1


async def test_bad_format_report_is_rejected(client: AsyncClient, fake_ai):
    fake_ai.content = '```json\n{"a": 1}\n```'
    rid = (await client.post("/api/v1/recon", json={"aoi": AOI})).json()["run_id"]
    assert (await wait_for_run(rid))["type"] == "done"
    rep = (await client.get(f"/api/v1/recon/{rid}/report")).json()
    assert rep["status"] == "failed" and "format" in rep["error"]
    assert fake_ai.calls == 2  # bitta tuzatish so'rovi bilan
