"""Deterministik oflayn Mock GEE Gateway.

Haqiqiy Google serverlariga bog'lanmagan holda, testlar va mustaqil ishlash uchun
fizik va geometrik jihatdan to'liq mos keluvchi sintetik raster massivlarni yaratadi.
"""

from typing import Any

import numpy as np

from backend.app.core.time import now_ts


class MockGEEGateway:
    """Oflayn testlar va tekshiruvlar uchun sun'iy GEE shlyuzi."""

    def __init__(self) -> None:
        self.failover_triggered: bool = False
        self.should_simulate_timeout: bool = False
        self.should_simulate_quota_error: bool = False

    async def discover_scenes(
        self, aoi_geojson: dict[str, Any], lookback_days: int = 10
    ) -> list[dict[str, Any]]:
        """Sintetik sun'iy yo'ldosh kadrlari (scenes) ro'yxatini qaytaradi."""
        current_time = now_ts()
        scenes: list[dict[str, Any]] = []

        # 1. Sentinel-2 kadrlar (masalan, 2 ta sana: 2 kun oldin va 7 kun oldin)
        for days_ago in [2, 7]:
            acq = current_time - (days_ago * 86400)
            scenes.append({
                "scene_id": f"S2A_MSIL2A_2026{acq}_N0500_R001",
                "sensor": 1,  # Sentinel-2
                "sensor_name": "Sentinel-2",
                "acq_time": acq,
                "cloud_pct": 5.0 if days_ago == 2 else 12.0,
            })

        # 2. Sentinel-1 SAR (3 kun oldin va 8 kun oldin)
        for days_ago in [3, 8]:
            acq = current_time - (days_ago * 86400)
            scenes.append({
                "scene_id": f"S1A_IW_GRDH_1SDV_2026{acq}",
                "sensor": 2,  # Sentinel-1
                "sensor_name": "Sentinel-1",
                "acq_time": acq,
                "cloud_pct": 0.0,
            })

        # 3. Landsat 8/9 (4 kun oldin)
        acq_ls = current_time - (4 * 86400)
        scenes.append({
            "scene_id": f"LC09_L2SP_153032_2026{acq_ls}",
            "sensor": 3,  # Landsat
            "sensor_name": "Landsat 9",
            "acq_time": acq_ls,
            "cloud_pct": 8.0,
        })

        return sorted(scenes, key=lambda s: s["acq_time"], reverse=True)

    async def download_raster(
        self,
        sensor: str,
        bands: list[str],
        width: int = 100,
        height: int = 100,
        acq_time: int | None = None,
    ) -> dict[str, np.ndarray]:
        """Berilgan sensor va bandlar uchun deterministik sintetik massivlar yaratadi."""
        y, x = np.mgrid[0:height, 0:width]
        result: dict[str, np.ndarray] = {}

        if sensor == "sentinel2":
            # Sintetik landshaft yaratish:
            # Chap yuqori: suv (past NIR, yuqori Green)
            # O'ng tomon: o'rmon (yuqori NIR, past Red)
            # Markaz: ekinzorlar va yo'l
            water_zone = (x < width * 0.3) & (y < height * 0.4)
            forest_zone = (x > width * 0.6) & (y > height * 0.3)
            road_line = (y >= height * 0.48) & (y <= height * 0.52)  # Uzun gorizontal yo'l

            # B4 (Red)
            red = np.full((height, width), 0.12, dtype=np.float32)
            red[water_zone] = 0.04
            red[forest_zone] = 0.03
            red[road_line] = 0.18

            # B3 (Green)
            green = np.full((height, width), 0.15, dtype=np.float32)
            green[water_zone] = 0.18
            green[forest_zone] = 0.08
            green[road_line] = 0.16

            # B2 (Blue)
            blue = np.full((height, width), 0.08, dtype=np.float32)
            blue[water_zone] = 0.14

            # B8 (NIR)
            nir = np.full((height, width), 0.35, dtype=np.float32)
            nir[water_zone] = 0.02  # Suvda NIR juda past
            nir[forest_zone] = 0.75  # O'rmonda NIR juda yuqori
            nir[road_line] = 0.15

            # B11 (SWIR1)
            swir1 = np.full((height, width), 0.20, dtype=np.float32)
            swir1[water_zone] = 0.01
            swir1[road_line] = 0.28  # Imorat va yo'lda SWIR yuqori

            # B12 (SWIR2)
            swir2 = np.full((height, width), 0.15, dtype=np.float32)

            # SCL (Scene Classification Layer)
            scl = np.full((height, width), 4, dtype=np.uint8)  # 4 - vegetation
            scl[water_zone] = 6  # 6 - water
            scl[road_line] = 5  # 5 - bare / non-veg

            bands_map = {
                "B2": blue,
                "B3": green,
                "B4": red,
                "B5": red * 1.2,
                "B8": nir,
                "B8A": nir * 0.95,
                "B11": swir1,
                "B12": swir2,
                "SCL": scl.astype(np.float32),
                "cs_cdf": np.full((height, width), 0.95, dtype=np.float32),  # Toza ochiq osmon
            }
            for b in bands:
                if b in bands_map:
                    result[b] = bands_map[b]

        elif sensor == "sentinel1":
            # SAR VV va VH desibellarda (dB)
            vv = np.full((height, width), -12.0, dtype=np.float32)
            vh = np.full((height, width), -18.0, dtype=np.float32)

            # Suv zonasi (past VV, masalan -20 dB)
            water_zone = (x < width * 0.3) & (y < height * 0.4)
            vv[water_zone] = -22.0
            vh[water_zone] = -28.0

            # O'rmon zonasi (yuqori hajm tarqalishi, yuqori VH)
            forest_zone = (x > width * 0.6) & (y > height * 0.3)
            vv[forest_zone] = -9.0
            vh[forest_zone] = -13.0

            result["VV"] = vv
            result["VH"] = vh

        elif sensor == "dem":
            # Relyef (Copernicus DEM)
            dem = 450.0 + (x * 0.5) + (y * 0.8) + (np.sin(x / 10.0) * 15.0)
            result["DEM"] = dem.astype(np.float32)

        elif sensor == "landsat":
            # ST_B10 termal DN qiymati: Kelvin = DN * 0.00341802 + 149.0
            # Selsiy = 25 °C => Kelvin = 298.15 => DN = (298.15 - 149.0) / 0.00341802 ≈ 43636
            st_b10 = np.full((height, width), 43636.0, dtype=np.float32)
            # Suv zonasida harorat pastroq (20 °C)
            water_zone = (x < width * 0.3) & (y < height * 0.4)
            st_b10[water_zone] = 42173.0  # ≈ 20 °C

            result["ST_B10"] = st_b10
            # Landsat SR
            result["SR_B4"] = np.full((height, width), 0.12, dtype=np.float32)
            result["SR_B5"] = np.full((height, width), 0.35, dtype=np.float32)

        elif sensor == "smap":
            # Tuproq namligi m3/m3 (0.05 dan 0.45 gacha)
            sm_surf = np.full((height, width), 0.22, dtype=np.float32)
            sm_root = np.full((height, width), 0.25, dtype=np.float32)
            result["sm_surface"] = sm_surf
            result["sm_rootzone"] = sm_root

        return result

    async def fetch_weather_series(
        self, past_days: int = 5, forecast_days: int = 5
    ) -> list[dict[str, Any]]:
        """Sintetik ERA5, GFS va CHIRPS ob-havo qatorlarini yaratadi."""
        current_time = now_ts()
        records: list[dict[str, Any]] = []

        # O'tmish soatlari (ERA5-Land)
        total_past_hours = past_days * 24
        for h in range(total_past_hours, 0, -3):
            ts = current_time - (h * 3600)
            records.append({
                "source": 1,  # ERA5
                "ts": ts,
                "temp_c": 22.0 + np.sin(h / 4.0) * 6.0,
                "dewpoint_c": 12.0,
                "precip_mm": 2.5 if h in [24, 27] else 0.0,
                "wind_speed_ms": 3.5,
                "wind_deg": 180.0,
                "soil_moisture": 0.24,
                "is_forecast": 0,
            })

        # Kelajak soatlari (GFS Forecast)
        total_fc_hours = forecast_days * 24
        for h in range(3, total_fc_hours + 1, 3):
            ts = current_time + (h * 3600)
            records.append({
                "source": 3,  # GFS_FORECAST
                "ts": ts,
                "temp_c": 24.0 + np.sin(h / 4.0) * 7.0,
                "dewpoint_c": 11.0,
                "precip_mm": 5.0 if h in [12, 15] else 0.0,
                "wind_speed_ms": 4.2,
                "wind_deg": 210.0,
                "soil_moisture": 0.22,
                "is_forecast": 1,
            })

        return records
