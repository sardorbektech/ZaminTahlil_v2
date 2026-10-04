"""To'liq API oqimi soxta GEE manbasi bilan: run, natijalar, 409, 422, sozlamalar, piksel, kompozit."""

import json

from httpx import AsyncClient

from backend.app.pipeline import storage as st
from tests.conftest import AOI, wait_for_run


async def start(client: AsyncClient, aoi=AOI) -> int:
    r = await client.post("/api/v1/recon", json={"aoi": aoi})
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


async def test_full_run_and_result_endpoints(client: AsyncClient, isolated_env):
    rid = await start(client)
    ev = await wait_for_run(rid)
    assert ev["type"] == "done", ev

    summ = (await client.get(f"/api/v1/recon/{rid}")).json()
    assert summ["status"] == "completed" and summ["report_status"] == "ok"
    assert summ["bounds_latlon"] and summ["completed_at_local"] != "maʼlumot yoʻq"
    assert len(summ["observation_dates"]) == 5  # 2×S2, 2×S1, 1×Landsat — faqat haqiqiy sanalar

    layers = (await client.get(f"/api/v1/recon/{rid}/layers")).json()["layers"]
    names = {lyr["name"] for lyr in layers}
    for n in ("rgb", "ndvi", "landcover", "vv", "lst", "elevation", "sm_surface", "delta_ndvi", "delta_vv", "class_change"):
        assert n in names, n
    for lyr in layers:
        assert lyr["acq_time_ts"] and lyr["acq_time_local"] and lyr["dataset"] and lyr["sensor"]
        assert "valid_pct" in lyr and lyr["legend"] is not None
    png = await client.get(layers[0]["image_url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"

    s2 = [lyr for lyr in layers if lyr["name"] == "rgb"][0]
    comp = await client.get(f"/api/v1/recon/{rid}/composite.png", params={"date": s2["acq_time_ts"], "r": "B8", "g": "B4", "b": "B3"})
    assert comp.status_code == 200
    bad = await client.get(f"/api/v1/recon/{rid}/composite.png", params={"date": s2["acq_time_ts"], "r": "B99", "g": "B4", "b": "B3"})
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_BAND"

    px = (await client.get(f"/api/v1/recon/{rid}/pixel", params={"lon": 69.2405, "lat": 41.3338})).json()
    assert px["groups"]
    for g in px["groups"]:
        assert g["acq_time_local"] and g["dataset"] and "scene_ids" in g
    s2g = [g for g in px["groups"] if g["sensor"] == "Sentinel-2"]
    assert any(v["name"] == "landcover" and v["class_label_uz"] == "Suv" for g in s2g for v in g["values"])
    out = await client.get(f"/api/v1/recon/{rid}/pixel", params={"lon": 10.0, "lat": 10.0})
    assert out.status_code == 404 and out.json()["message_uz"]

    classes = (await client.get(f"/api/v1/recon/{rid}/classes")).json()
    assert len(classes["dates"]) == 2
    assert abs(sum(c["pct"] for c in classes["dates"][0]["classes"]) - 100.0) < 0.1

    ch = (await client.get(f"/api/v1/recon/{rid}/changes")).json()
    assert len(ch["sentinel2"]) == 1 and len(ch["sentinel1"]) == 1
    assert ch["sentinel2"][0]["delta_ndvi"]["mean"] > 0  # soxta ma'lumotda NIR oshgan
    assert ch["cross_check"] and ch["cross_check"][0]["available"]

    wx = (await client.get(f"/api/v1/recon/{rid}/weather")).json()
    assert wx["past"] and wx["forecast"] and wx["chirps_daily"]
    assert all(r["source"] in ("era5", "gfs_analysis", "gfs_forecast", "chirps") and r["time_local"] for r in wx["past"] + wx["forecast"])
    cats = {i["category"] for i in wx["impact"]}
    assert {"frost", "strong_wind", "precip_past"} <= cats

    sats = (await client.get(f"/api/v1/recon/{rid}/satellites")).json()
    assert len(sats["scenes"]) == 5 and all(s["acq_time_local"] for s in sats["scenes"])

    rep = (await client.get(f"/api/v1/recon/{rid}/report")).json()
    assert rep["status"] == "ok" and rep["content_md"].startswith("## 1.")

    usage = (await client.get(f"/api/v1/usage/runs/{rid}")).json()
    assert usage["total_calls"] >= 6 and "Xizmatlar" in usage["markdown"]

    summary = st.load_json(st.summary_path(rid))
    assert summary["run"]["id"] == rid and "images" not in summary  # images faqat AI kirishida


async def test_conflict_when_running(client: AsyncClient, isolated_env):
    isolated_env["source"].delay_s = 0.3
    rid = await start(client)
    r = await client.post("/api/v1/recon", json={"aoi": AOI})
    assert r.status_code == 409 and r.json()["code"] == "JOB_ALREADY_RUNNING"
    active = (await client.get("/api/v1/recon/active")).json()
    assert active["active"] and active["run"]["id"] == rid and active["run"]["aoi"]["type"] == "Polygon"
    put = await client.put("/api/v1/settings", json={"lookback_days": 5})
    assert put.status_code == 409
    await client.post(f"/api/v1/recon/{rid}/cancel")


async def test_invalid_aoi_rejected(client: AsyncClient):
    big = {"type": "Polygon", "coordinates": [[[69.0, 41.0], [69.5, 41.0], [69.5, 41.5], [69.0, 41.5], [69.0, 41.0]]]}
    r = await client.post("/api/v1/recon", json={"aoi": big})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_AOI"
    bow = {"type": "Polygon", "coordinates": [[[69.0, 41.0], [69.01, 41.01], [69.01, 41.0], [69.0, 41.01], [69.0, 41.0]]]}
    r2 = await client.post("/api/v1/recon", json={"aoi": bow})
    assert r2.status_code == 422
    r3 = await client.post("/api/v1/recon", json={"aoi": {"type": "Point", "coordinates": [69, 41]}})
    assert r3.status_code == 422 and "message_uz" in r3.json()


async def test_settings_get_put_validation(client: AsyncClient):
    s = (await client.get("/api/v1/settings")).json()
    assert s["settings"]["lookback_days"] == 10 and s["settings"]["ai_model"] == "gpt-6-luna"
    assert s["settings"]["ai_provider"] == "openai" and "landcover" in s["choices"]["landcover_analyzer"]
    assert "openrouter_api_key" not in json.dumps(s)  # maxfiy kalitlar qaytarilmaydi
    ok = await client.put("/api/v1/settings", json={"lookback_days": 20, "s1_orbit_pass": "ASCENDING"})
    assert ok.status_code == 200 and ok.json()["settings"]["lookback_days"] == 20
    bad = await client.put("/api/v1/settings", json={"lookback_days": 61})
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_SETTINGS"
    bad2 = await client.put("/api/v1/settings", json={"ai_provider": "gemini"})
    assert bad2.status_code == 422


async def test_sse_stream_replays_until_done(client: AsyncClient):
    rid = await start(client)
    types = []
    async with client.stream("GET", f"/api/v1/recon/{rid}/events") as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                types.append(ev["type"])
                assert ev["ts_local"] and 0.0 <= ev["progress"] <= 1.0
    assert types[0] == "progress" and types[-1] == "done"
    # Tugagan run uchun SSE darhol yakuniy hodisani beradi
    async with client.stream("GET", f"/api/v1/recon/{rid}/events") as resp:
        lines = [ln async for ln in resp.aiter_lines() if ln.startswith("data: ")]
    assert json.loads(lines[-1][6:])["type"] == "done"


async def test_not_found_error_shape(client: AsyncClient):
    r = await client.get("/api/v1/recon/9999")
    assert r.status_code == 404 and set(r.json()) >= {"code", "message_uz"}
