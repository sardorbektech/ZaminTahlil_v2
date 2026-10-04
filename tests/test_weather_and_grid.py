"""Ob-havo yordamchilari (GFS yog'in farqi, shamol yo'nalishi, ta'sir qoidalari) va to'r/AOI."""

import math

import numpy as np
import pytest

from backend.app.core.errors import AOIValidationError
from backend.app.gee.convert import convert_landsat, convert_s2
from backend.app.gee.sources import gfs_precip_increments, reduce_scale_m, wind_dir_deg
from backend.app.pipeline.grid import (
    aoi_area_km2,
    build_grid,
    normalize_aoi,
    rasterize_aoi,
    validate_aoi,
)
from backend.app.pipeline.recon import group_observations
from backend.app.weather.impact import analyze_weather_impact, daily_precip
from tests.conftest import AOI


def test_gfs_precip_bucket_differencing():
    # F1..F6 bitta 6 soatlik bo'lak, F7 yangi bo'lak; F120 dan keyin 3 soatlik qadam
    acc = {1: 1.0, 2: 1.5, 3: 1.5, 6: 3.0, 7: 0.5, 120: 2.0, 123: 1.0, 126: 1.8}
    out = {f: (span, inc) for f, span, inc in gfs_precip_increments(list(acc.items()))}
    assert out[1] == (1, 1.0)
    assert out[2] == (1, 0.5)
    assert out[3] == (1, 0.0)
    assert out[6] == (3, 1.5)
    assert out[7] == (1, 0.5)  # yangi bo'lak boshi — qiymatning o'zi
    assert out[123] == (3, 1.0)  # 120 dan keyin yangi bo'lak (121–126)
    assert out[126] == (3, pytest.approx(0.8))
    assert gfs_precip_increments([(1, None), (2, 1.0)])[0][2] is None


def test_wind_direction_and_reduce_scale():
    assert math.isclose(wind_dir_deg(0.0, -5.0), 0.0, abs_tol=1e-9)  # shimoldan esadi
    assert math.isclose(wind_dir_deg(-5.0, 0.0), 90.0)  # sharqdan
    assert wind_dir_deg(None, 1.0) is None
    assert reduce_scale_m(100.0) == 1000.0 and reduce_scale_m(0.01) == 25.0


def test_scaling_conversions():
    s2 = convert_s2({"B4": np.array([0, 1000], np.uint16), "SCL": np.array([0, 4], np.uint16),
                     "cs_cdf": np.array([65535, 9000], np.uint16)})
    assert np.isnan(s2["B4"][0]) and np.isclose(s2["B4"][1], 0.1)
    assert np.isnan(s2["SCL"][0]) and s2["SCL"][1] == 4
    assert np.isnan(s2["cs_cdf"][0]) and np.isclose(s2["cs_cdf"][1], 0.9)
    ls = convert_landsat({"SR_B4": np.array([0, 10000], np.uint16)})
    assert np.isnan(ls["SR_B4"][0]) and np.isclose(ls["SR_B4"][1], 10000 * 0.0000275 - 0.2)


def _wx(ts: int, fc: int, t: float = 15.0, p: float | None = 0.0, w: float = 3.0) -> dict:
    return {"source": 3 if fc else 1, "ts": ts, "is_forecast": fc, "temp_c": t, "temp_min_c": t, "temp_max_c": t,
            "precip_mm": p, "wind_speed_ms": w, "wind_max_ms": w}


def test_weather_impact_rules():
    now = 1790000000
    recs = [_wx(now - h * 3600, 0, p=2.0 if h < 6 else 0.0) for h in range(1, 48)]
    recs += [_wx(now + h * 3600, 1, t=-2.0 if h == 10 else 10.0, p=1.0 if h < 20 else 0.0, w=15.0 if h == 5 else 3.0) for h in range(1, 48)]
    out = analyze_weather_impact(recs, depression_pct=4.0,
                                 soil_moisture_trend={"available": True, "first_ts": now - 86400, "last_ts": now, "first": 0.2, "last": 0.25, "delta": 0.05},
                                 vv_changes=[{"prev_ts": now - 5 * 86400, "ts": now, "mean_delta": 1.6}])
    cats = {o["category"]: o for o in out}
    assert cats["precip_past"]["values"]["past_precip_mm"] == 10.0
    assert "oshgan" in cats["precip_past"]["message_uz"] and "+1.60 dB" in cats["precip_past"]["message_uz"]
    assert cats["waterlogging_risk"]["values"]["forecast_precip_mm"] == 19.0
    assert "frost" in cats and "strong_wind" in cats
    assert all("." in o["message_uz"] for o in out)


def test_weather_impact_no_data_is_explicit():
    out = analyze_weather_impact([])
    assert out[0]["category"] == "no_data" and "maʼlumot yoʻq" in out[0]["message_uz"]
    past_no_rain = [_wx(1790000000 - h * 3600, 0, p=None) for h in range(1, 5)]
    out2 = analyze_weather_impact(past_no_rain)
    assert any(o["category"] == "precip_past_missing" for o in out2)


def test_daily_precip_uses_tashkent_days():
    # 18:30 UTC va 19:30 UTC — Toshkentda turli kunlar (23:30 va 00:30)
    from datetime import UTC, datetime

    t1 = int(datetime(2026, 9, 26, 18, 30, tzinfo=UTC).timestamp())
    d = daily_precip([_wx(t1, 0, p=1.0), _wx(t1 + 3600, 0, p=2.0)])
    assert [x["precip_mm"] for x in d] == [1.0, 2.0]


def test_aoi_validation_and_grid():
    aoi = normalize_aoi({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [AOI["coordinates"][0][:-1]]}})
    assert aoi["coordinates"][0][0] == aoi["coordinates"][0][-1]  # halqa yopildi
    area = validate_aoi(aoi, 100.0)
    assert 0.1 < area < 0.3
    with pytest.raises(AOIValidationError):
        validate_aoi(aoi, 0.01)
    g = build_grid(aoi, 10.0)
    assert math.isclose(g.pixel_size, 10.0 / math.cos(math.radians(41.332)), rel_tol=1e-3)
    mask = rasterize_aoi(aoi, g)
    ground = float((g.row_pixel_area_m2()[:, None] * mask).sum()) / 1e6
    assert abs(ground - aoi_area_km2(aoi)) / aoi_area_km2(aoi) < 0.08
    (s, w), (n, e) = g.bounds_latlon()
    assert s <= 41.33 and n >= 41.334 and w <= 69.24 and e >= 69.246
    assert g.pixel_of(69.2401, 41.3339) == (0, 0) or g.pixel_of(69.2401, 41.3339)[0] <= 1
    assert g.pixel_of(0, 0) is None


def test_group_observations_same_day_mosaic():
    from backend.app.db.enums import SensorKind
    from backend.app.gee.types import SceneInfo

    t = 1790489869
    sc = [SceneInfo("a", SensorKind.SENTINEL2, "S2A", "d", t), SceneInfo("b", SensorKind.SENTINEL2, "S2A", "d", t + 5),
          SceneInfo("c", SensorKind.SENTINEL2, "S2B", "d", t + 86400 * 2), SceneInfo("d", SensorKind.SENTINEL1, "S1", "d", t)]
    obs = group_observations(sc)
    assert [(o.sensor, len(o.scenes)) for o in obs] == [(SensorKind.SENTINEL2, 2), (SensorKind.SENTINEL2, 1), (SensorKind.SENTINEL1, 1)]
    assert obs[0].obs_time == t


def test_dem_tiles_filtered_by_name_cell():
    from backend.app.gee.sources import dem_tiles_for_aoi

    ids = ["Copernicus_DSM_COG_10_N41_00_E069_00_DEM", "Copernicus_DSM_COG_10_S90_00_E000_00_DEM", "odd"]
    assert dem_tiles_for_aoi(ids, AOI) == [ids[0], "odd"]
