"""Testlar uchun soxta (tarmoqsiz) GEE ma'lumot manbasi va AI mijozi.

Bu modul faqat testlarda ishlatiladi; ilova kodida sintetik ma'lumot manbasi yo'q.
"""

import asyncio
from typing import Any

import numpy as np

from backend.app.core.errors import AIReportError
from backend.app.core.run_settings import RunSettings
from backend.app.db.enums import SensorKind, WeatherSource
from backend.app.gee import datasets as D
from backend.app.gee.gateway import CallContext
from backend.app.gee.types import Discovery, Observation, SceneInfo, StaticProduct, WeatherBundle
from backend.app.pipeline.grid import Grid
from backend.app.usage.tracker import record_api_call

DAY = 86400


class FakeSource:
    """Deterministik sintetik landshaft: chap-yuqorida suv, o'ngda o'rmon, o'rtada yo'l, qolgani dala."""

    def __init__(self, now: int, scene_suffix: str = "a", delay_s: float = 0.0) -> None:
        self.now = now
        self.scene_suffix = scene_suffix
        self.delay_s = delay_s
        self.calls: list[str] = []

    def is_configured(self) -> bool:
        return True

    async def _log(self, ctx: CallContext, op: str, purpose: str, dataset: str) -> None:
        self.calls.append(purpose)
        await record_api_call(run_id=ctx.run_id, service="gee_primary", operation=op, purpose=purpose,
                              dataset=dataset, status="success", duration_ms=1.0)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)

    async def discover(self, aoi: dict[str, Any], start_ts: int, end_ts: int, s: RunSettings, ctx: CallContext) -> Discovery:
        await self._log(ctx, "listScenes", "scene_discovery", D.S2_COLLECTION)
        t = self.now
        scenes = [
            SceneInfo(f"S2_{self.scene_suffix}_1", SensorKind.SENTINEL2, "Sentinel-2A", D.S2_COLLECTION, t - 7 * DAY, 5.0),
            SceneInfo(f"S2_{self.scene_suffix}_2", SensorKind.SENTINEL2, "Sentinel-2B", D.S2_COLLECTION, t - 2 * DAY, 3.0),
            SceneInfo(f"S1_{self.scene_suffix}_1", SensorKind.SENTINEL1, "Sentinel-1A", D.S1_COLLECTION, t - 8 * DAY, None, "ASCENDING"),
            SceneInfo(f"S1_{self.scene_suffix}_2", SensorKind.SENTINEL1, "Sentinel-1A", D.S1_COLLECTION, t - 3 * DAY, None, "ASCENDING"),
            SceneInfo(f"LC09_{self.scene_suffix}", SensorKind.LANDSAT, "LANDSAT_9", D.LANDSAT_COLLECTIONS["LC09"], t - 3 * DAY + 3600, 8.0),
        ]
        dem = StaticProduct(SensorKind.DEM, D.DEM_COLLECTION, t - 3000 * DAY, ["DEM_tile"], (t - 4000 * DAY, t - 3000 * DAY))
        smap = StaticProduct(SensorKind.SMAP, D.SMAP_COLLECTION, t - 4 * DAY, ["SMAP_x"])
        return Discovery(scenes=scenes, dem=dem, smap=smap)

    @staticmethod
    def _zones(grid: Grid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        y, x = np.mgrid[0 : grid.height, 0 : grid.width]
        water = (x < grid.width * 0.3) & (y < grid.height * 0.4)
        forest = (x > grid.width * 0.6) & (y > grid.height * 0.3)
        road = (np.abs(y - grid.height // 2) <= 0) & ~water & ~forest
        return water, forest, road

    async def download_observation(self, obs: Observation, grid: Grid, s: RunSettings, ctx: CallContext) -> dict[str, np.ndarray]:
        await self._log(ctx, "computePixels", f"{obs.sensor.name.lower()}_download", obs.datasets[0])
        water, forest, road = self._zones(grid)
        shape = (grid.height, grid.width)
        later = obs.obs_time > self.now - 5 * DAY
        if obs.sensor == SensorKind.SENTINEL2:
            def band(v: float, w: float, f: float, r: float) -> np.ndarray:
                a = np.full(shape, v, np.float32)
                a[water], a[forest], a[road] = w, f, r
                return a
            nir = band(0.40 if later else 0.33, 0.02, 0.75, 0.20)
            out = {
                "B2": band(0.06, 0.08, 0.03, 0.15), "B3": band(0.09, 0.12, 0.06, 0.17),
                "B4": band(0.08, 0.04, 0.03, 0.19), "B5": band(0.12, 0.04, 0.10, 0.20),
                "B8": nir, "B8A": nir * 0.97, "B11": band(0.20, 0.01, 0.15, 0.32),
                "B12": band(0.14, 0.01, 0.07, 0.28),
                "SCL": band(4, 6, 4, 5), "cs_cdf": np.full(shape, 0.95, np.float32),
            }
            out["cs_cdf"][0, -1] = 0.1  # bitta bulutli piksel
            return out
        if obs.sensor == SensorKind.SENTINEL1:
            vv = np.full(shape, -11.0, np.float32)
            vh = np.full(shape, -18.0, np.float32)
            vv[water], vh[water] = -22.0, -28.0
            vv[forest], vh[forest] = -8.0, -13.0
            vv[road] = -6.0
            if later:
                vv += 1.5
            return {"VV": vv, "VH": vh}
        if obs.sensor == SensorKind.LANDSAT:
            dn = lambda refl: np.full(shape, (refl + 0.2) / 0.0000275, np.float32)  # noqa: E731
            st = np.full(shape, (298.15 - 149.0) / 0.00341802, np.float32)  # 25 °C
            qa = np.full(shape, 21824, np.float32)  # toza piksel
            qa[0, 0] = 22280  # bulut biti
            return {"SR_B2": dn(0.06), "SR_B3": dn(0.09), "SR_B4": dn(0.08), "SR_B5": dn(0.40),
                    "SR_B6": dn(0.2), "SR_B7": dn(0.14), "ST_B10": st, "QA_PIXEL": qa}
        raise AssertionError(obs.sensor)

    async def download_dem_context(self, grid: Grid, ctx: CallContext) -> dict[str, np.ndarray]:
        await self._log(ctx, "computePixels", "dem_context_download", D.DEM_COLLECTION)
        y, x = np.mgrid[0 : grid.height, 0 : grid.width]
        return {"DEM": (400.0 + x * 0.2 + y * 0.1).astype(np.float32)}

    async def download_static(self, product: StaticProduct, grid: Grid, s: RunSettings, ctx: CallContext) -> dict[str, np.ndarray]:
        await self._log(ctx, "computePixels", f"{product.sensor.name.lower()}_download", product.dataset)
        y, x = np.mgrid[0 : grid.height, 0 : grid.width]
        if product.sensor == SensorKind.DEM:
            dem = (450.0 + x * 0.5 + y * 0.3).astype(np.float32)
            dem[grid.height // 2 - 1 : grid.height // 2 + 2, 2:5] -= 5.0  # kichik chuqurlik
            return {"DEM": dem}
        return {"sm_surface": np.full(y.shape, 0.22, np.float32), "sm_rootzone": np.full(y.shape, 0.25, np.float32)}

    async def fetch_weather(self, aoi: dict[str, Any], area_km2: float, now: int, s: RunSettings, ctx: CallContext) -> WeatherBundle:
        await self._log(ctx, "reduceRegion", "weather_past", D.ERA5_LAND_HOURLY)
        hourly: list[dict[str, Any]] = []
        for h in range(s.weather_past_days * 24, 0, -1):
            ts = now - h * 3600
            hourly.append(_rec(WeatherSource.ERA5, ts, 3600, 0, 20.0, 3.0 if h in (30, 31, 32, 33) else 0.0, 4.0))
        for h in range(1, s.weather_forecast_days * 24 + 1):
            ts = now + h * 3600
            r = _rec(WeatherSource.GFS_FORECAST, ts, 3600, 1, -1.0 if h == 40 else 18.0, 2.0 if 10 <= h < 20 else 0.0, 13.0 if h == 50 else 4.0)
            r["issued_ts"] = now - 3 * 3600
            hourly.append(r)
        chirps = [{"source": int(WeatherSource.CHIRPS), "ts": now - d * DAY, "period_s": DAY, "precip_mm": 1.0,
                   "precip_min_mm": 0.5, "precip_max_mm": 1.5} for d in range(s.weather_past_days, 0, -1)]
        smap_series = [{"ts": now - (10 - i) * DAY, "sm_surface": 0.20 + i * 0.005, "sm_rootzone": 0.25} for i in range(10)]
        return WeatherBundle(hourly=hourly, chirps_daily=chirps, smap_series=smap_series,
                             gfs_run_ts=now - 3 * 3600, era5_last_ts=now - 3600)


def _rec(src: WeatherSource, ts: int, period: int, fc: int, t: float, p: float, w: float) -> dict[str, Any]:
    return {
        "source": int(src), "ts": ts, "period_s": period, "issued_ts": None, "is_forecast": fc,
        "temp_c": t, "temp_min_c": t - 1, "temp_max_c": t + 1, "dewpoint_c": 8.0, "rh_pct": 50.0,
        "precip_mm": p, "precip_min_mm": p, "precip_max_mm": p, "wind_speed_ms": w, "wind_min_ms": w - 1,
        "wind_max_ms": w + 1, "wind_deg": 180.0, "cloud_pct": 20.0, "soil_moisture": 0.2,
    }


VALID_REPORT = "\n\n".join(
    f"## {i}. {s}\nMatn." for i, s in enumerate(
        ["Umumiy maʼlumot", "Relyef", "Yer qoplami", "Oʻzgarishlar", "Ob-havo va taʼsiri",
         "Prognoz va xavflar", "Maʼlumot sifati va cheklovlar"], 1)
)


class FakeAIClient:
    """AI mijozining soxtasi: chaqiruvlarni sanaydi, kerak bo'lsa xato beradi."""

    def __init__(self, fail_times: int = 0, content: str = VALID_REPORT) -> None:
        self.fail_times = fail_times
        self.content = content
        self.calls = 0

    async def generate(self, **kwargs: Any) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise AIReportError("Soxta provayder xatosi")
        return self.content

    async def chat(self, provider: str, model: str, messages: list[dict[str, str]], run_id: int | None = None) -> str:
        """Soxta suhbat: oxirgi savolni va kontekstda maydon bor-yo'qligini aks ettiradi."""
        self.calls += 1
        self.last_messages = messages
        if self.calls <= self.fail_times:
            raise AIReportError("Soxta provayder xatosi")
        return f"Javob: {messages[-1]['content']}"
