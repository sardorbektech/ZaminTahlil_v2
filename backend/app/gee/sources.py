"""Haqiqiy GEE ma'lumot manbasi: kadrlarni topish, computePixels bilan yuklash va ob-havo.

Bu modulda faqat `ee` ifodalari quriladi; bajarish har doim gateway.call orqali
(thread, semafor, qayta urinish, failover, jurnal) amalga oshiriladi.
"""

import asyncio
import math
import re
from typing import Any

import numpy as np

from backend.app.core import constants as C
from backend.app.core.errors import GEEMemoryLimitError
from backend.app.core.run_settings import RunSettings
from backend.app.core.telemetry import log_telemetry
from backend.app.db.enums import SensorKind, WeatherSource
from backend.app.gee import datasets as D
from backend.app.gee.convert import (
    CS_MISSING_UINT16,
    convert_float_product,
    convert_landsat,
    convert_s2,
    structured_to_dict,
)
from backend.app.gee.gateway import CallContext, GEEGateway
from backend.app.gee.gateway import gateway as default_gateway
from backend.app.gee.types import Discovery, Observation, SceneInfo, StaticProduct, WeatherBundle
from backend.app.pipeline.grid import Grid

HOUR = 3600
DAY = 86400


def _ee() -> Any:
    import ee

    return ee


def reduce_scale_m(area_km2: float) -> float:
    """Kichik AOI ham bir nechta namuna nuqtasiga ega bo'lishi uchun reduceRegion masshtabi."""
    side_m = math.sqrt(max(area_km2, 1e-6) * 1_000_000.0)
    return float(min(D.WEATHER_REDUCE_SCALE_M, max(10.0, side_m / 4.0)))


def wind_dir_deg(u: float | None, v: float | None) -> float | None:
    """Shamol yo'nalishi (qayerdan esadi, meteorologik daraja) o'rtacha u, v dan."""
    if u is None or v is None:
        return None
    return float((270.0 - math.degrees(math.atan2(v, u))) % 360.0)


def gfs_precip_increments(rows: list[tuple[int, float | None]]) -> list[tuple[int, int, float | None]]:
    """GFS to'plangan yog'inni oraliq qiymatlariga aylantiradi.

    Katalog: total_precipitation_surface — oldingi ((F − 1) % 6) + 1 soatdagi yig'indi.
    Kirish: (forecast_hours, AOI o'rtacha qiymati) tartiblangan ro'yxati.
    Chiqish: (F, oraliq uzunligi soatda, F−oraliq..F dagi yog'in mm).
    Bir bo'lak ichida: inc = acc(F) − acc(F_oldingi); yangi bo'lak boshida: inc = acc(F).
    """
    out: list[tuple[int, int, float | None]] = []
    prev_f: int | None = None
    prev_acc: float | None = None
    for f, acc in sorted(rows, key=lambda r: r[0]):
        if f <= 0:
            prev_f, prev_acc = f, None
            continue
        bucket_len = ((f - 1) % D.GFS_BUCKET_HOURS) + 1
        bucket_start = f - bucket_len
        if prev_f is not None and prev_f > bucket_start:
            # Bir bo'lak ichida
            inc = None if (acc is None or prev_acc is None) else max(0.0, acc - prev_acc)
            out.append((f, f - prev_f, inc))
        else:
            out.append((f, bucket_len if prev_f is None else f - prev_f, acc))
        prev_f, prev_acc = f, acc
    return out


_DEM_TILE_RE = re.compile(r"([NS])(\d{2})_\d{2}_([EW])(\d{3})_\d{2}")


def dem_tiles_for_aoi(ids: list[str], aoi: dict[str, Any]) -> list[str]:
    """Copernicus DEM plitkalarini nomidagi 1° katak bo'yicha AOI bilan kesishganlariga cheklaydi.

    Ba'zi plitkalar (masalan, S90_*) katalogda noto'g'ri qamrovga ega va filterBounds ularni ham qaytaradi.
    Nomi tushunarsiz plitkalar o'zgarishsiz qoldiriladi.
    """
    ring = aoi["coordinates"][0]
    lo_lon, hi_lon = min(p[0] for p in ring), max(p[0] for p in ring)
    lo_lat, hi_lat = min(p[1] for p in ring), max(p[1] for p in ring)
    out = []
    for tid in ids:
        m = _DEM_TILE_RE.search(tid)
        if not m:
            out.append(tid)
            continue
        lat = int(m.group(2)) * (1 if m.group(1) == "N" else -1)
        lon = int(m.group(4)) * (1 if m.group(3) == "E" else -1)
        if lat <= hi_lat and lat + 1 >= lo_lat and lon <= hi_lon and lon + 1 >= lo_lon:
            out.append(tid)
    return out or ids


class GEESource:
    """Google Earth Engine'dan ma'lumot oluvchi manba."""

    def __init__(self, gw: GEEGateway | None = None) -> None:
        self.gw = gw or default_gateway

    def is_configured(self) -> bool:
        return self.gw.is_configured()

    # ------------------------------------------------------------------
    # Yordamchilar
    # ------------------------------------------------------------------
    @staticmethod
    def _geom(aoi: dict[str, Any]) -> Any:
        ee = _ee()
        return ee.Geometry.Polygon(aoi["coordinates"], None, False)

    async def _info(self, build: Any, ctx: CallContext, operation: str, purpose: str, dataset: str, request: str = "") -> Any:
        """`build()` qaytargan ee obyektining getInfo natijasi (thread ichida quriladi)."""

        def _fn() -> Any:
            return build().getInfo()

        return await self.gw.call(
            _fn, ctx=ctx, operation=operation, purpose=purpose, dataset=dataset, request=request
        )

    # ------------------------------------------------------------------
    # 3-bosqich: kadrlarni topish (faqat metama'lumot)
    # ------------------------------------------------------------------
    async def discover(
        self, aoi: dict[str, Any], start_ts: int, end_ts: int, s: RunSettings, ctx: CallContext
    ) -> Discovery:
        ee_start, ee_end = start_ts * 1000, end_ts * 1000

        def meta_fc(col_id: str, props: dict[str, str], filters: list[Any]) -> Any:
            ee = _ee()
            col = ee.ImageCollection(col_id).filterBounds(self._geom(aoi)).filterDate(ee_start, ee_end)
            for f in filters:
                col = col.filter(f)

            def to_feat(img: Any) -> Any:
                d = {"id": img.get("system:index"), "t": img.get("system:time_start")}
                d.update({k: img.get(v) for k, v in props.items()})
                return ee.Feature(None, d)

            return ee.FeatureCollection(col.limit(500).map(to_feat))

        def s2_build() -> Any:
            ee = _ee()
            return meta_fc(
                D.S2_COLLECTION,
                {"c": D.S2_CLOUD_PROPERTY, "p": D.S2_PLATFORM_PROPERTY},
                [ee.Filter.lte(D.S2_CLOUD_PROPERTY, s.max_scene_cloud_pct)],
            )

        def s1_build() -> Any:
            ee = _ee()
            flt = [
                ee.Filter.eq("instrumentMode", D.S1_INSTRUMENT_MODE),
                ee.Filter.listContains("transmitterReceiverPolarisation", "VV"),
                ee.Filter.listContains("transmitterReceiverPolarisation", "VH"),
            ]
            if s.s1_orbit_pass != "BOTH":
                flt.append(ee.Filter.eq(D.S1_PASS_PROPERTY, s.s1_orbit_pass))
            return meta_fc(D.S1_COLLECTION, {"o": D.S1_PASS_PROPERTY, "p": "platform_number"}, flt)

        def ls_build(col_id: str) -> Any:
            ee = _ee()
            return meta_fc(
                col_id,
                {"c": D.LANDSAT_CLOUD_PROPERTY, "p": "SPACECRAFT_ID"},
                [ee.Filter.lte(D.LANDSAT_CLOUD_PROPERTY, s.max_scene_cloud_pct)],
            )

        def dem_build() -> Any:
            ee = _ee()
            col = ee.ImageCollection(D.DEM_COLLECTION).filterBounds(self._geom(aoi))
            return ee.Dictionary(
                {
                    "ids": col.aggregate_array("system:index"),
                    "tmin": col.aggregate_min("system:time_start"),
                    "tmax": col.aggregate_max("system:time_start"),
                }
            )

        def smap_build() -> Any:
            ee = _ee()
            col = (
                ee.ImageCollection(D.SMAP_COLLECTION)
                .filterBounds(self._geom(aoi))
                .filterDate(ee_start, ee_end)
                .sort("system:time_start", False)
                .limit(1)
            )
            return ee.Dictionary(
                {"ids": col.aggregate_array("system:index"), "t": col.aggregate_array("system:time_start")}
            )

        tasks = [
            self._info(s2_build, ctx, "listScenes", "scene_discovery", D.S2_COLLECTION),
            self._info(s1_build, ctx, "listScenes", "scene_discovery", D.S1_COLLECTION),
            *[
                self._info(lambda c=cid: ls_build(c), ctx, "listScenes", "scene_discovery", cid)
                for cid in D.LANDSAT_COLLECTIONS.values()
            ],
            self._info(dem_build, ctx, "listTiles", "dem_discovery", D.DEM_COLLECTION),
            self._info(smap_build, ctx, "listImages", "smap_discovery", D.SMAP_COLLECTION),
        ]
        s2_fc, s1_fc, l8_fc, l9_fc, dem_info, smap_info = await asyncio.gather(*tasks)

        scenes: list[SceneInfo] = []

        def feats(fc: dict[str, Any]) -> list[dict[str, Any]]:
            return [f.get("properties", {}) for f in (fc or {}).get("features", [])]

        for p in feats(s2_fc):
            scenes.append(
                SceneInfo(
                    scene_id=str(p["id"]),
                    sensor=SensorKind.SENTINEL2,
                    platform=str(p.get("p") or "Sentinel-2"),
                    dataset=D.S2_COLLECTION,
                    acq_time=int(p["t"]) // 1000,
                    cloud_pct=float(p["c"]) if p.get("c") is not None else None,
                )
            )
        for p in feats(s1_fc):
            scenes.append(
                SceneInfo(
                    scene_id=str(p["id"]),
                    sensor=SensorKind.SENTINEL1,
                    platform=f"Sentinel-1{p.get('p') or ''}",
                    dataset=D.S1_COLLECTION,
                    acq_time=int(p["t"]) // 1000,
                    orbit_pass=p.get("o"),
                )
            )
        for fc, cid in ((l8_fc, D.LANDSAT_COLLECTIONS["LC08"]), (l9_fc, D.LANDSAT_COLLECTIONS["LC09"])):
            for p in feats(fc):
                scenes.append(
                    SceneInfo(
                        scene_id=str(p["id"]),
                        sensor=SensorKind.LANDSAT,
                        platform=str(p.get("p") or "Landsat"),
                        dataset=cid,
                        acq_time=int(p["t"]) // 1000,
                        cloud_pct=float(p["c"]) if p.get("c") is not None else None,
                    )
                )
        for sc in scenes:
            log_telemetry(sc.platform, "Kadr topildi", f"{sc.scene_id} | bulut: {sc.cloud_pct}", sc.acq_time)

        dem = None
        if dem_info and dem_info.get("ids"):
            dem_info["ids"] = dem_tiles_for_aoi([str(x) for x in dem_info["ids"]], aoi)
            tmin, tmax = dem_info.get("tmin"), dem_info.get("tmax")
            dem = StaticProduct(
                sensor=SensorKind.DEM,
                dataset=D.DEM_COLLECTION,
                acq_time=int(tmax) // 1000 if tmax else 0,
                item_ids=[str(x) for x in dem_info["ids"]],
                time_range=(int(tmin) // 1000, int(tmax) // 1000) if tmin and tmax else None,
            )
        smap = None
        if smap_info and smap_info.get("ids"):
            smap = StaticProduct(
                sensor=SensorKind.SMAP,
                dataset=D.SMAP_COLLECTION,
                acq_time=int(smap_info["t"][0]) // 1000,
                item_ids=[str(smap_info["ids"][0])],
            )
        return Discovery(scenes=scenes, dem=dem, smap=smap)

    # ------------------------------------------------------------------
    # 5-bosqich: computePixels bilan yuklash (bo'laklarga bo'lingan, parallel)
    # ------------------------------------------------------------------
    async def _compute_pixels(
        self,
        build_image: Any,
        grid: Grid,
        ctx: CallContext,
        purpose: str,
        dataset: str,
        sentinel: float,
        dtype: Any,
    ) -> dict[str, np.ndarray]:
        """To'rni bo'laklarga bo'lib yuklaydi; xotira chegarasida bo'lakni to'rtga bo'ladi."""
        result: dict[str, np.ndarray] = {}

        async def fetch(row0: int, col0: int, h: int, w: int) -> None:
            def _fn() -> np.ndarray:
                ee = _ee()
                return ee.data.computePixels(
                    {
                        "expression": build_image(),
                        "fileFormat": "NUMPY_NDARRAY",
                        "grid": {
                            "dimensions": {"width": w, "height": h},
                            "affineTransform": grid.affine(col0, row0),
                            "crsCode": "EPSG:3857",
                        },
                    }
                )

            try:
                arr = await self.gw.call(
                    _fn,
                    ctx=ctx,
                    operation="computePixels",
                    purpose=purpose,
                    dataset=dataset,
                    request=f"tile r{row0} c{col0} {w}x{h}",
                )
            except GEEMemoryLimitError:
                if max(h, w) <= C.MIN_TILE_SIZE_PX:
                    raise
                h2, w2 = max(1, h // 2), max(1, w // 2)
                parts = [(row0, col0, h2, w2), (row0, col0 + w2, h2, w - w2),
                         (row0 + h2, col0, h - h2, w2), (row0 + h2, col0 + w2, h - h2, w - w2)]
                await asyncio.gather(*[fetch(*p) for p in parts if p[2] > 0 and p[3] > 0])
                return
            bands = structured_to_dict(arr)
            for b, v in bands.items():
                if b not in result:
                    result[b] = np.full((grid.height, grid.width), sentinel, dtype=dtype)
                result[b][row0 : row0 + h, col0 : col0 + w] = v

        tiles = [
            (r, c, min(C.TILE_SIZE_PX, grid.height - r), min(C.TILE_SIZE_PX, grid.width - c))
            for r in range(0, grid.height, C.TILE_SIZE_PX)
            for c in range(0, grid.width, C.TILE_SIZE_PX)
        ]
        await asyncio.gather(*[fetch(*t) for t in tiles])
        return result

    async def download_observation(
        self, obs: Observation, grid: Grid, s: RunSettings, ctx: CallContext
    ) -> dict[str, np.ndarray]:
        ids = obs.scene_ids
        t0, t1 = (obs.obs_time - HOUR) * 1000, (obs.last_time + HOUR) * 1000
        log_telemetry(obs.sensor.name, "Yuklanmoqda", f"{len(ids)} kadr | {grid.width}x{grid.height}", obs.obs_time)

        if obs.sensor == SensorKind.SENTINEL2:

            def build() -> Any:
                ee = _ee()
                col = (
                    ee.ImageCollection(D.S2_COLLECTION)
                    .filterDate(t0, t1)
                    .filter(ee.Filter.inList("system:index", ids))
                    .linkCollection(ee.ImageCollection(D.S2_CLOUD_SCORE_PLUS_COLLECTION), [D.CLOUD_SCORE_BAND])
                )

                def prep(img: Any) -> Any:
                    refl = img.select(D.S2_REFLECTANCE_BANDS).resample("bilinear").unmask(0).toUint16()
                    has_cs = img.bandNames().contains(D.CLOUD_SCORE_BAND)
                    cs = ee.Image(
                        ee.Algorithms.If(
                            has_cs,
                            img.select([D.CLOUD_SCORE_BAND]).resample("bilinear"),
                            ee.Image.constant(0).rename(D.CLOUD_SCORE_BAND).updateMask(0),
                        )
                    )
                    cs = cs.multiply(C.CLOUD_SCORE_UINT_SCALE).unmask(CS_MISSING_UINT16).toUint16()
                    scl = img.select(D.S2_QA_BANDS).unmask(0).toUint16()  # sinf bandi — eng yaqin qo'shni
                    # Har bir kadr o'z izi bilan niqoblanadi, keyin mozaika qilinadi
                    return refl.addBands(cs).addBands(scl).updateMask(img.select("B4").mask())

                return col.map(prep).mosaic().unmask(0).toUint16()

            raw = await self._compute_pixels(build, grid, ctx, "sentinel2_download", D.S2_COLLECTION, 0, np.uint16)
            # mozaika tashqarisida cs_cdf ham 0 bo'ladi — reflektans bo'yicha baribir NaN
            data = convert_s2(raw)

        elif obs.sensor == SensorKind.SENTINEL1:

            def build() -> Any:
                ee = _ee()
                col = ee.ImageCollection(D.S1_COLLECTION).filterDate(t0, t1).filter(
                    ee.Filter.inList("system:index", ids)
                )
                return (
                    col.map(lambda img: img.select(D.S1_BANDS).resample("bilinear"))
                    .mosaic()
                    .unmask(C.NODATA_FLOAT)
                    .toFloat()
                )

            raw = await self._compute_pixels(
                build, grid, ctx, "sentinel1_download", D.S1_COLLECTION, C.NODATA_FLOAT, np.float32
            )
            data = convert_float_product(raw)

        elif obs.sensor == SensorKind.LANDSAT:
            by_col: dict[str, list[str]] = {}
            for sc in obs.scenes:
                by_col.setdefault(sc.dataset, []).append(sc.scene_id)

            def build() -> Any:
                ee = _ee()
                parts = []
                for cid, cids in by_col.items():
                    col = ee.ImageCollection(cid).filterDate(t0, t1).filter(ee.Filter.inList("system:index", cids))
                    parts.append(
                        col.map(
                            lambda img: img.select(D.LANDSAT_SR_BANDS + D.LANDSAT_THERMAL_BANDS)
                            .resample("bilinear")
                            .addBands(img.select(D.LANDSAT_QA_BANDS))
                            .toUint16()
                        )
                    )
                merged = parts[0]
                for p in parts[1:]:
                    merged = merged.merge(p)
                return merged.mosaic().unmask(0).toUint16()

            raw = await self._compute_pixels(build, grid, ctx, "landsat_download", ",".join(by_col), 0, np.uint16)
            data = convert_landsat(raw)
        else:
            raise ValueError(f"Kuzatuv sensori qoʻllab-quvvatlanmaydi: {obs.sensor}")

        log_telemetry(obs.sensor.name, "Qabul qilindi", f"bandlar: {', '.join(sorted(data))}", obs.obs_time)
        return data

    async def download_static(
        self, product: StaticProduct, grid: Grid, s: RunSettings, ctx: CallContext
    ) -> dict[str, np.ndarray]:
        if product.sensor == SensorKind.DEM:

            def build() -> Any:
                ee = _ee()
                col = ee.ImageCollection(D.DEM_COLLECTION).filter(ee.Filter.inList("system:index", product.item_ids))
                proj = col.first().select(D.DEM_BAND).projection()
                return (
                    col.select(D.DEM_BAND)
                    .mosaic()
                    .setDefaultProjection(proj)
                    .resample("bilinear")
                    .unmask(C.NODATA_FLOAT)
                    .toFloat()
                )

            purpose = "dem_download"
        elif product.sensor == SensorKind.SMAP:

            def build() -> Any:
                ee = _ee()
                img = ee.Image(f"{D.SMAP_COLLECTION}/{product.item_ids[0]}")
                return img.select(D.SMAP_BANDS).resample("bilinear").unmask(C.NODATA_FLOAT).toFloat()

            purpose = "smap_download"
        else:
            raise ValueError(f"Statik mahsulot qoʻllab-quvvatlanmaydi: {product.sensor}")

        raw = await self._compute_pixels(build, grid, ctx, purpose, product.dataset, C.NODATA_FLOAT, np.float32)
        data = convert_float_product(raw)
        log_telemetry(product.sensor.name, "Qabul qilindi", f"bandlar: {', '.join(sorted(data))}", product.acq_time)
        return data

    async def download_dem_context(self, grid: Grid, ctx: CallContext) -> dict[str, np.ndarray]:
        """3D atrof ko'rinishi uchun kengaytirilgan to'rdagi Copernicus DEM (plitkalar nomidagi 1° katak bo'yicha)."""
        (s_lat, w_lon), (n_lat, e_lon) = grid.bounds_latlon()
        rect = {"type": "Polygon", "coordinates": [[[w_lon, s_lat], [e_lon, s_lat], [e_lon, n_lat], [w_lon, n_lat], [w_lon, s_lat]]]}

        def ids_build() -> Any:
            ee = _ee()
            return ee.ImageCollection(D.DEM_COLLECTION).filterBounds(self._geom(rect)).aggregate_array("system:index")

        ids = await self._info(ids_build, ctx, "listTiles", "dem_context_discovery", D.DEM_COLLECTION)
        tiles = dem_tiles_for_aoi([str(x) for x in ids or []], rect)
        if not tiles:
            return {}

        def build() -> Any:
            ee = _ee()
            col = ee.ImageCollection(D.DEM_COLLECTION).filter(ee.Filter.inList("system:index", tiles))
            proj = col.first().select(D.DEM_BAND).projection()
            return col.select(D.DEM_BAND).mosaic().setDefaultProjection(proj).resample("bilinear").unmask(C.NODATA_FLOAT).toFloat()

        raw = await self._compute_pixels(build, grid, ctx, "dem_context_download", D.DEM_COLLECTION, C.NODATA_FLOAT, np.float32)
        return convert_float_product(raw)

    # ------------------------------------------------------------------
    # 6-bosqich: ob-havo (AOI bo'yicha o'rtacha, min, max)
    # ------------------------------------------------------------------
    async def fetch_weather(
        self, aoi: dict[str, Any], area_km2: float, now: int, s: RunSettings, ctx: CallContext
    ) -> WeatherBundle:
        scale = reduce_scale_m(area_km2)
        past_start = now - s.weather_past_days * DAY
        horizon_h = s.weather_forecast_days * 24

        def reducer() -> Any:
            ee = _ee()
            return ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)

        def stats_fc(col: Any, make_img: Any, extra: dict[str, str]) -> Any:
            ee = _ee()
            geom = self._geom(aoi)

            def to_feat(img: Any) -> Any:
                stats = make_img(img).reduceRegion(reducer=reducer(), geometry=geom, scale=scale, maxPixels=1e9)
                props = {"ts": img.get("system:time_start")}
                props.update({k: img.get(v) for k, v in extra.items()})
                return ee.Feature(None, stats).set(props)

            return ee.FeatureCollection(col.map(to_feat))

        def era5_build() -> Any:
            ee = _ee()
            col = ee.ImageCollection(D.ERA5_LAND_HOURLY).filterDate(past_start * 1000, now * 1000)

            def mk(i: Any) -> Any:
                u = i.select("u_component_of_wind_10m").rename("u")
                v = i.select("v_component_of_wind_10m").rename("v")
                return ee.Image.cat([
                    i.select("temperature_2m").subtract(C.KELVIN_OFFSET).rename("t"),
                    i.select("dewpoint_temperature_2m").subtract(C.KELVIN_OFFSET).rename("d"),
                    i.select("total_precipitation_hourly").multiply(C.ERA5_PRECIP_M_TO_MM).rename("p"),
                    u.hypot(v).rename("w"),
                    u,
                    v,
                    i.select("volumetric_soil_water_layer_1").rename("sm"),
                ])

            return stats_fc(col, mk, {})

        def gfs_img(i: Any, with_precip: bool) -> Any:
            ee = _ee()
            u = i.select("u_component_of_wind_10m_above_ground").rename("u")
            v = i.select("v_component_of_wind_10m_above_ground").rename("v")
            bands = [
                i.select("temperature_2m_above_ground").rename("t"),
                i.select("dew_point_temperature_2m_above_ground").rename("d"),
                i.select("relative_humidity_2m_above_ground").rename("rh"),
                u.hypot(v).rename("w"),
                u,
                v,
                i.select("total_cloud_cover_entire_atmosphere").rename("cc"),
            ]
            if with_precip:
                bands.append(i.select(D.GFS_PRECIP_BAND).rename("p"))
            return ee.Image.cat(bands)

        def gfs_analysis_build() -> Any:
            ee = _ee()
            col = (
                ee.ImageCollection(D.GFS_0P25)
                .filterDate(past_start * 1000, now * 1000)
                .filter(ee.Filter.eq("forecast_hours", 0))
            )
            return stats_fc(col, lambda i: gfs_img(i, False), {"issued": "creation_time"})

        def gfs_runs_build() -> Any:
            ee = _ee()
            col = (
                ee.ImageCollection(D.GFS_0P25)
                .filterDate((now - 2 * DAY) * 1000, (now + HOUR) * 1000)
                .filter(ee.Filter.gt("forecast_hours", 0))
            )
            return col.reduceColumns(
                ee.Reducer.max().setOutputs(["max_fh"]).group(groupField=0, groupName="run"),
                ["creation_time", "forecast_hours"],
            )

        def chirps_build() -> Any:
            ee = _ee()
            col = ee.ImageCollection(D.CHIRPS_DAILY).filterDate((past_start - past_start % DAY) * 1000, now * 1000)
            return stats_fc(col, lambda i: i.select(D.CHIRPS_BAND).rename("p"), {})

        def smap_series_build() -> Any:
            ee = _ee()
            col = ee.ImageCollection(D.SMAP_COLLECTION).filterDate((now - s.lookback_days * DAY) * 1000, now * 1000)
            geom = self._geom(aoi)

            def to_feat(img: Any) -> Any:
                st = img.select(D.SMAP_BANDS).reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=geom, scale=scale, maxPixels=1e9
                )
                return ee.Feature(None, st).set({"ts": img.get("system:time_start")})

            return ee.FeatureCollection(col.map(to_feat))

        era5_fc, gfs_an_fc, runs, chirps_fc, smap_fc = await asyncio.gather(
            self._info(era5_build, ctx, "reduceRegion", "weather_past", D.ERA5_LAND_HOURLY),
            self._info(gfs_analysis_build, ctx, "reduceRegion", "weather_recent", D.GFS_0P25),
            self._info(gfs_runs_build, ctx, "reduceColumns", "weather_forecast_runs", D.GFS_0P25),
            self._info(chirps_build, ctx, "reduceRegion", "weather_daily_rain", D.CHIRPS_DAILY),
            self._info(smap_series_build, ctx, "reduceRegion", "soil_moisture_series", D.SMAP_COLLECTION),
        )

        def props(fc: Any) -> list[dict[str, Any]]:
            return [f.get("properties", {}) for f in (fc or {}).get("features", [])]

        notes: list[str] = []
        hourly: list[dict[str, Any]] = []

        # ERA5-Land (o'tmish, soatlik)
        era5_last: int | None = None
        for p in props(era5_fc):
            ts = int(p["ts"]) // 1000
            if p.get("t_mean") is None:
                continue
            era5_last = ts if era5_last is None else max(era5_last, ts)
            hourly.append(_wx_record(WeatherSource.ERA5, ts, HOUR, p, is_forecast=0))

        # GFS analiz (ERA5 hali qamramagan so'nggi soatlar, forecast_hours = 0)
        gap_start = era5_last if era5_last is not None else past_start
        for p in props(gfs_an_fc):
            ts = int(p["ts"]) // 1000
            if ts <= gap_start or p.get("t_mean") is None:
                continue
            rec = _wx_record(WeatherSource.GFS_ANALYSIS, ts, 0, p, is_forecast=0)
            rec["issued_ts"] = int(p["issued"]) // 1000 if p.get("issued") else ts
            hourly.append(rec)

        # GFS prognoz: so'nggi to'liq run
        gfs_run_ts: int | None = None
        groups = (runs or {}).get("groups", [])
        candidates = sorted(
            [(int(g["run"]) // 1000, int(g.get("max_fh") or 0)) for g in groups if g.get("run") is not None],
            reverse=True,
        )
        chosen: tuple[int, int] | None = None
        for run_ts, max_fh in candidates:
            need = math.ceil((now - run_ts) / HOUR) + horizon_h
            if max_fh >= need:
                chosen = (run_ts, need)
                break
        if chosen is None and candidates:
            run_ts, max_fh = candidates[0]
            chosen = (run_ts, max_fh)
            notes.append("GFS prognozining eng soʻnggi run'i toʻliq yuklanmagan; prognoz qisqaroq.")
        if chosen is not None:
            gfs_run_ts, need_fh = chosen

            def gfs_fc_build() -> Any:
                ee = _ee()
                col = (
                    ee.ImageCollection(D.GFS_0P25)
                    .filter(ee.Filter.eq("creation_time", gfs_run_ts * 1000))
                    .filter(ee.Filter.gt("forecast_hours", 0))
                    .filter(ee.Filter.lte("forecast_hours", need_fh))
                )
                return stats_fc(
                    col, lambda i: gfs_img(i, True), {"fh": "forecast_hours", "ft": "forecast_time"}
                )

            fc = await self._info(gfs_fc_build, ctx, "reduceRegion", "weather_forecast", D.GFS_0P25)
            rows = props(fc)
            by_fh = {int(p["fh"]): p for p in rows if p.get("fh") is not None}
            incs = gfs_precip_increments([(fh, by_fh[fh].get("p_mean")) for fh in by_fh])
            for fh, span_h, inc in incs:
                p = by_fh[fh]
                valid_ts = int(p["ft"]) // 1000 if p.get("ft") else gfs_run_ts + fh * HOUR
                if valid_ts <= now or p.get("t_mean") is None:
                    continue
                rec = _wx_record(WeatherSource.GFS_FORECAST, valid_ts, span_h * HOUR, p, is_forecast=1)
                rec["issued_ts"] = gfs_run_ts
                # Oraliq yog'in faqat o'rtacha qiymatlar farqidan aniq; min/max uchun farq olinmaydi
                rec["precip_mm"] = inc
                rec["precip_min_mm"] = None
                rec["precip_max_mm"] = None
                hourly.append(rec)
        else:
            notes.append("GFS prognozi topilmadi.")

        chirps: list[dict[str, Any]] = []
        for p in props(chirps_fc):
            if p.get("p_mean") is None and p.get("p") is None:
                continue
            chirps.append(
                {
                    "source": int(WeatherSource.CHIRPS),
                    "ts": int(p["ts"]) // 1000,
                    "period_s": DAY,
                    "precip_mm": _f(p.get("p_mean", p.get("p"))),
                    "precip_min_mm": _f(p.get("p_min")),
                    "precip_max_mm": _f(p.get("p_max")),
                }
            )

        smap_series = [
            {"ts": int(p["ts"]) // 1000, "sm_surface": _f(p.get("sm_surface")), "sm_rootzone": _f(p.get("sm_rootzone"))}
            for p in props(smap_fc)
            if p.get("sm_surface") is not None
        ]
        smap_series.sort(key=lambda r: r["ts"])
        hourly.sort(key=lambda r: r["ts"])
        chirps.sort(key=lambda r: r["ts"])
        log_telemetry("Ob-havo", "Qabul qilindi", f"{len(hourly)} soatlik, {len(chirps)} kunlik yozuv")
        return WeatherBundle(
            hourly=hourly,
            chirps_daily=chirps,
            smap_series=smap_series,
            gfs_run_ts=gfs_run_ts,
            era5_last_ts=era5_last,
            notes=notes,
        )


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def _wx_record(source: WeatherSource, ts: int, period_s: int, p: dict[str, Any], is_forecast: int) -> dict[str, Any]:
    """reduceRegion natijasidan yagona ob-havo yozuvini tuzadi (yo'q qiymatlar None)."""
    return {
        "source": int(source),
        "ts": ts,
        "period_s": period_s,
        "issued_ts": None,
        "is_forecast": is_forecast,
        "temp_c": _f(p.get("t_mean")),
        "temp_min_c": _f(p.get("t_min")),
        "temp_max_c": _f(p.get("t_max")),
        "dewpoint_c": _f(p.get("d_mean")),
        "rh_pct": _f(p.get("rh_mean")),
        "precip_mm": _f(p.get("p_mean")) if period_s else None,
        "precip_min_mm": _f(p.get("p_min")) if period_s else None,
        "precip_max_mm": _f(p.get("p_max")) if period_s else None,
        "wind_speed_ms": _f(p.get("w_mean")),
        "wind_min_ms": _f(p.get("w_min")),
        "wind_max_ms": _f(p.get("w_max")),
        "wind_deg": wind_dir_deg(_f(p.get("u_mean")), _f(p.get("v_mean"))),
        "cloud_pct": _f(p.get("cc_mean")),
        "soil_moisture": _f(p.get("sm_mean")),
    }
