"""Foydalanuvchilar, saqlangan maydonlar, 3D/nomlar, AI suhbat, ML/CV kengaytmasi va baza hayotiy sikli."""

import base64
import json
from typing import Any

import httpx
import numpy as np
import pytest
from httpx import AsyncClient

from backend.app.ai.client import OpenAICompatibleProvider
from backend.app.analysis.models import PixelModelAnalyzer, register_model
from backend.app.analysis.registry import unregister_analyzer
from backend.app.core import constants as C
from backend.app.db import session as db
from backend.app.db.enums import LayerKind, SensorKind
from backend.app.pipeline.render import LAYER_SPECS, LayerSpec
from tests.conftest import AOI, basic, make_client, wait_for_run


async def _run(client: AsyncClient, name: str = "") -> int:
    r = await client.post("/api/v1/recon", json={"aoi": AOI, "name": name})
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    assert (await wait_for_run(rid))["type"] == "done"
    return rid


# ---------------------------------------------------------------------------
# Kirish
# ---------------------------------------------------------------------------
async def test_login_creates_then_verifies(anon: AsyncClient):
    r = await anon.post("/api/v1/auth/login", json={"username": "Oʻktam", "password": "x"})
    assert r.status_code == 200 and r.json()["created"] is True
    r2 = await anon.post("/api/v1/auth/login", json={"username": " Oʻktam ", "password": "x"})
    assert r2.status_code == 200 and r2.json()["created"] is False
    bad = await anon.post("/api/v1/auth/login", json={"username": "Oʻktam", "password": "y"})
    assert bad.status_code == 401 and bad.json()["code"] == "AUTH_FAILED"
    empty = await anon.post("/api/v1/auth/login", json={"username": "  ", "password": "x"})
    assert empty.status_code == 422
    nopw = await anon.post("/api/v1/auth/login", json={"username": "a", "password": ""})
    assert nopw.status_code == 422
    me = await anon.get("/api/v1/auth/me", headers=basic("Oʻktam", "x"))  # UTF-8 Basic
    assert me.status_code == 200 and me.json()["user"]["username"] == "Oʻktam"


async def test_endpoints_require_auth_and_do_not_autocreate(anon: AsyncClient):
    assert (await anon.get("/api/v1/recon")).status_code == 401
    assert (await anon.get("/api/v1/settings")).status_code == 401
    r = await anon.get("/api/v1/recon", headers=basic("yangi", "p"))
    assert r.status_code == 401  # faqat /auth/login yaratadi


async def test_users_see_only_their_own_areas(client: AsyncClient):
    rid = await _run(client, "Mening dalam")
    other = await make_client("boshqa", "q")
    try:
        assert (await other.get("/api/v1/recon")).json()["areas"] == []
        for path in ("", "/layers", "/report", "/chat", "/terrain3d"):
            assert (await other.get(f"/api/v1/recon/{rid}{path}")).status_code == 404, path
        assert (await other.get(f"/api/v1/usage/runs/{rid}")).status_code == 404
        assert (await other.delete(f"/api/v1/recon/{rid}")).status_code == 404
        # Boshqa foydalanuvchi aynan shu hududni tahlil qilsa — dublikat emas, o'z run'i
        r = await other.post("/api/v1/recon", json={"aoi": AOI})
        assert (await wait_for_run(r.json()["run_id"]))["type"] == "done"
    finally:
        await other.aclose()


# ---------------------------------------------------------------------------
# Saqlangan maydonlar
# ---------------------------------------------------------------------------
async def test_area_list_rename_delete(client: AsyncClient, isolated_env):
    rid = await _run(client, "Chirchiq boʻyi")
    areas = (await client.get("/api/v1/recon")).json()["areas"]
    assert areas[0]["id"] == rid and areas[0]["name"] == "Chirchiq boʻyi" and areas[0]["observation_dates"] == 5
    assert areas[0]["aoi"]["type"] == "Polygon"
    r = await client.patch(f"/api/v1/recon/{rid}", json={"name": "Yangi nom"})
    assert r.status_code == 200 and (await client.get(f"/api/v1/recon/{rid}")).json()["name"] == "Yangi nom"
    assert (await client.patch(f"/api/v1/recon/{rid}", json={"name": " "})).status_code == 422
    d = await client.delete(f"/api/v1/recon/{rid}")
    assert d.status_code == 200
    assert (await client.get(f"/api/v1/recon/{rid}")).status_code == 404
    assert not (isolated_env["runs"] / str(rid)).exists()


async def test_default_name_when_empty(client: AsyncClient):
    rid = await _run(client)
    name = (await client.get(f"/api/v1/recon/{rid}")).json()["name"]
    assert name.startswith("Maydon ")


# ---------------------------------------------------------------------------
# 3D va nomlar
# ---------------------------------------------------------------------------
async def test_terrain3d_and_labels(client: AsyncClient):
    rid = await _run(client)
    ctx = (await client.get(f"/api/v1/recon/{rid}/terrain3d")).json()  # standart: atrof bilan
    assert ctx["scope"] == "context" and ctx["resolution_m"] >= 30
    (cs, cw), (cn, ce) = ctx["bounds_latlon"]
    (as_, aw), (an, ae) = ctx["aoi_grid_bounds_latlon"]
    assert cs < as_ and cw < aw and cn > an and ce > ae  # AOI atrof ichida
    assert ctx["size_x_m"] >= 3000  # har tomondan ≥ 1.5 km
    t = (await client.get(f"/api/v1/recon/{rid}/terrain3d", params={"scope": "aoi"})).json()
    assert t["scope"] == "aoi"
    assert (await client.get(f"/api/v1/recon/{rid}/terrain3d", params={"scope": "x"})).status_code == 422
    heights = np.frombuffer(base64.b64decode(t["heights_b64"]), dtype="<f4")
    assert heights.size == t["width"] * t["height"]
    assert t["min_m"] <= heights.min() + 1e-3 and heights.max() <= t["max_m"] + 1e-3
    assert t["size_x_m"] > 0 and t["dataset"] == "COPERNICUS/DEM/GLO30_2024_1" and t["acq_time_local"]
    lab = (await client.get(f"/api/v1/recon/{rid}/labels")).json()
    assert len(lab["dates"]) == 2
    names = {p["label_uz"] for p in lab["dates"][-1]["labels"]}
    assert "Suv" in names and "Daraxtzor" in names
    for p in lab["dates"][-1]["labels"]:
        assert p["color"].startswith("#") and p["area_ha"] > 0
    assert (await client.get(f"/api/v1/recon/{rid}/labels")).json() == lab  # keshdan


def test_terrain_block_mean_no_interpolation():
    from backend.app.pipeline.terrain3d import block_mean

    a = np.array([[1, 2, 3], [3, 4, np.nan], [5, 6, 7]], dtype=np.float32)
    b = block_mean(a, 2)
    assert b.shape == (2, 2)
    assert b[0, 0] == 2.5 and b[0, 1] == 3.0 and b[1, 0] == 5.5 and b[1, 1] == 7.0


# ---------------------------------------------------------------------------
# AI suhbat
# ---------------------------------------------------------------------------
async def test_chat_about_area_with_history(client: AsyncClient, fake_ai):
    rid = await _run(client)
    r = await client.post(f"/api/v1/recon/{rid}/chat", json={"message": "Suv qancha?"})
    assert r.status_code == 200 and r.json()["answer"]["content"] == "Javob: Suv qancha?"
    sys_msgs = [m for m in fake_ai.last_messages if m["role"] == "system"]
    assert C.CHAT_OFF_TOPIC_UZ in sys_msgs[0]["content"]  # mavzudan tashqari savollarga rad javobi
    assert '"class_areas"' in sys_msgs[1]["content"]  # maydon natijalari kontekstda
    await client.post(f"/api/v1/recon/{rid}/chat", json={"message": "Relyef?"})
    assert [m["role"] for m in fake_ai.last_messages[2:]] == ["user", "assistant", "user"]
    hist = (await client.get(f"/api/v1/recon/{rid}/chat")).json()["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]
    assert (await client.post(f"/api/v1/recon/{rid}/chat", json={"message": "  "})).status_code == 422
    assert (await client.delete(f"/api/v1/recon/{rid}/chat")).json()["cleared"]
    assert (await client.get(f"/api/v1/recon/{rid}/chat")).json()["messages"] == []


async def test_chat_failure_stores_nothing(client: AsyncClient, fake_ai):
    rid = await _run(client)
    fake_ai.fail_times = fake_ai.calls + 1
    r = await client.post(f"/api/v1/recon/{rid}/chat", json={"message": "Savol"})
    assert r.status_code == 502
    assert (await client.get(f"/api/v1/recon/{rid}/chat")).json()["messages"] == []


async def test_openai_provider_drops_unsupported_temperature():
    seen: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature'"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    p = OpenAICompatibleProvider(
        "openai", "https://api.openai.com/v1", lambda: "k",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await p.complete([{"role": "user", "content": "x"}], "gpt-6-luna", None, purpose="area_chat") == "ok"
    assert "temperature" in seen[0] and "temperature" not in seen[1]
    await p.complete([{"role": "user", "content": "x"}], "gpt-6-luna", None)
    assert len(seen) == 3  # keyingi so'rovlarda darhol temperature'siz


# ---------------------------------------------------------------------------
# ML / CV kengaytmasi
# ---------------------------------------------------------------------------
class _ThresholdModel(PixelModelAnalyzer):
    """Test uchun "klassik ML": NDVI > 0.5 → 1 (ehtimollar bilan)."""

    name = "test_veg_model"
    version = "ml-0.1"
    inputs = ["ndvi", "ndwi"]
    output_specs = {
        "test_veg": LayerSpec(LayerKind.MODEL_OUTPUT, SensorKind.SENTINEL2, "Test ML oʻsimlik", "", "mask", 0, 1, "mask", "ML modellari"),
    }

    def predict_pixels(self, x: np.ndarray) -> np.ndarray:
        p1 = (x[:, 0] > 0.5).astype(np.float32)
        return np.stack([1 - p1, p1], axis=1)


@pytest.fixture
def ml_model():
    m = _ThresholdModel()
    register_model(m)
    yield m
    unregister_analyzer(m.name)
    LAYER_SPECS.pop("test_veg", None)


async def test_extra_ml_model_layer_flows_to_api(client: AsyncClient, ml_model):
    rid = await _run(client)
    layers = (await client.get(f"/api/v1/recon/{rid}/layers")).json()["layers"]
    ml = [lyr for lyr in layers if lyr["name"] == "test_veg"]
    assert len(ml) == 2  # har bir Sentinel-2 sanasi uchun
    assert ml[0]["producer"] == {"method": "classic_ml", "analyzer": "test_veg_model", "version": "ml-0.1"}
    assert ml[0]["group_uz"] == "ML modellari" and ml[0]["legend"]["type"] == "classes"
    lc = [lyr for lyr in layers if lyr["name"] == "landcover"][0]
    assert lc["producer"]["method"] == "rules"


async def test_landcover_slot_can_be_replaced(client: AsyncClient):
    class _MLLandcover(PixelModelAnalyzer):
        name = "ml_landcover"
        version = "rf-0.1"
        slot = "landcover"
        inputs = ["ndvi"]
        output_specs = {"landcover": LAYER_SPECS["landcover"]}

        def predict_pixels(self, x: np.ndarray) -> np.ndarray:
            return np.where(x[:, 0] > 0.6, C.CLASS_FOREST, C.CLASS_CROPLAND)

    register_model(_MLLandcover())
    try:
        s = (await client.get("/api/v1/settings")).json()
        assert "ml_landcover" in s["choices"]["landcover_analyzer"]
        assert (await client.put("/api/v1/settings", json={"landcover_analyzer": "ml_landcover"})).status_code == 200
        rid = await _run(client)
        lc = [lyr for lyr in (await client.get(f"/api/v1/recon/{rid}/layers")).json()["layers"] if lyr["name"] == "landcover"][0]
        assert lc["producer"]["method"] == "classic_ml" and lc["producer"]["analyzer"] == "ml_landcover"
        codes = {c["class_code"] for c in (await client.get(f"/api/v1/recon/{rid}/classes")).json()["dates"][0]["classes"]}
        assert codes <= {C.CLASS_UNKNOWN, C.CLASS_FOREST, C.CLASS_CROPLAND}
        assert (await client.put("/api/v1/settings", json={"landcover_analyzer": "yoq_model"})).status_code == 422
    finally:
        unregister_analyzer("ml_landcover")


# ---------------------------------------------------------------------------
# Baza: qo'lda o'chirish, eski WAL
# ---------------------------------------------------------------------------
async def test_deleting_db_file_is_safe(isolated_env):
    tmp = isolated_env["tmp"]
    path = tmp / "manual.sqlite"
    db.configure_engine(f"sqlite+aiosqlite:///{path}")
    await db.init_db()
    await db.engine.dispose()
    path.unlink()
    (tmp / "manual.sqlite-wal").write_bytes(b"eski jurnal")  # qolib ketgan WAL
    db.configure_engine(f"sqlite+aiosqlite:///{path}")
    assert not (tmp / "manual.sqlite-wal").exists()
    await db.init_db()  # bo'sh bazadan qayta yaratiladi
    ac = await make_client("qayta", "1")  # foydalanuvchi qayta yaratiladi
    try:
        assert (await ac.get("/api/v1/recon")).json()["areas"] == []
    finally:
        await ac.aclose()
