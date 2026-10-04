"""10 bosqichli rekognossirovka quvuri (SIMPLE.md §6).

1 AOI tekshiruvi → 2 to'r → 3 kadrlarni topish → 4 barmoq izi → 5 yuklash → 6 ob-havo →
7 tahlil → 8 render → 9 saqlash → 10 AI hisobot.

Har bir tashqi chaqiruv gateway orqali o'tadi; bekor qilish asyncio.CancelledError orqali
har bir await nuqtasida darhol ishlaydi (tozalashni JobManager bajaradi).
"""

import asyncio
import gc
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import select

from backend.app.ai.report_generator import generate_report_for_run
from backend.app.analysis.analyzers import calc_stats
from backend.app.analysis.interface import AnalyzerInput, producer_of
from backend.app.analysis.quality import cross_check_ndvi, evaluate_layer_quality
from backend.app.analysis.registry import analyzers_for, get_analyzer
from backend.app.core import constants as C
from backend.app.core.errors import AppError, GEENotConfiguredError
from backend.app.core.run_settings import RunSettings
from backend.app.core.telemetry import log_step, logger
from backend.app.core.time import fmt_local, fmt_local_date, now_ts, ts_fields, utc_day_start
from backend.app.db import session as db
from backend.app.db.enums import (
    SENSOR_NAMES_UZ,
    JobStatus,
    QualityFlag,
    SensorKind,
    WeatherSource,
)
from backend.app.db.models import (
    ClassAreaModel,
    LayerModel,
    LayerStatsModel,
    RunModel,
    SceneModel,
    WeatherModel,
)
from backend.app.gee import datasets as D
from backend.app.gee.gateway import CallContext, GEEGateway
from backend.app.gee.types import (
    DataSource,
    Discovery,
    Observation,
    SceneInfo,
    StaticProduct,
    WeatherBundle,
)
from backend.app.pipeline import storage as st
from backend.app.pipeline.fingerprint import compute_recon_fingerprint
from backend.app.pipeline.grid import Grid, build_grid, rasterize_aoi
from backend.app.pipeline.jobs import Job, delete_run_records
from backend.app.pipeline.render import (
    LAYER_SPECS,
    render_composite_png,
    render_layer_png,
)
from backend.app.weather.impact import analyze_weather_impact, daily_precip

SAR_PAIR_MAX_DAYS = 3.0  # S2 tasnifi uchun S1 kuzatuvi shu kun ichida bo'lsa ishlatiladi
CHANGE_LAYERS_S2 = ["ndvi", "ndwi", "ndmi", "nbr"]

BANDS_PROVIDED = {
    SensorKind.SENTINEL2: D.S2_BANDS + [D.CLOUD_SCORE_BAND],
    SensorKind.SENTINEL1: D.S1_BANDS,
    SensorKind.LANDSAT: D.LANDSAT_BANDS,
    SensorKind.DEM: [D.DEM_BAND],
    SensorKind.SMAP: D.SMAP_BANDS,
}


def group_observations(scenes: list[SceneInfo]) -> list[Observation]:
    """Bir sensorning bir UTC kundagi kadrlarini bitta kuzatuvga (mozaikaga) birlashtiradi."""
    groups: dict[tuple[SensorKind, int], list[SceneInfo]] = {}
    for sc in scenes:
        groups.setdefault((sc.sensor, utc_day_start(sc.acq_time)), []).append(sc)
    obs = [
        Observation(sensor=k[0], obs_time=min(s.acq_time for s in v), scenes=sorted(v, key=lambda s: s.acq_time))
        for k, v in groups.items()
    ]
    return sorted(obs, key=lambda o: (o.sensor, o.obs_time))


@dataclass
class LayerRecord:
    """Saqlanadigan qatlam haqida to'liq ma'lumot."""

    name: str
    acq_time: int
    sensor: SensorKind
    dataset: str
    scene_ids: list[str]
    derived_key: str
    stats: dict[str, Any]
    valid_pct: float
    cloud_masked_pct: float | None
    quality_flag: QualityFlag
    prev_time: int | None = None
    producer: str = "rules:formula:rules-1.0"
    png: str = ""
    vmin: float | None = None
    vmax: float | None = None


@dataclass
class PipelineState:
    """Bosqichlar orasidagi holat (katta massivlar diskda, xotirada faqat kichik qismlar)."""

    grid: Grid | None = None
    aoi_mask: np.ndarray | None = None
    discovery: Discovery | None = None
    observations: list[Observation] = field(default_factory=list)
    fingerprint: bytes | None = None
    downloaded: dict[str, dict[str, Any]] = field(default_factory=dict)  # key -> meta
    weather: WeatherBundle | None = None
    layers: list[LayerRecord] = field(default_factory=list)
    class_areas: list[dict[str, Any]] = field(default_factory=list)
    changes: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {"sentinel2": [], "sentinel1": []})
    cross_checks: list[dict[str, Any]] = field(default_factory=list)
    obs_quality: list[dict[str, Any]] = field(default_factory=list)
    soil_trend: dict[str, Any] = field(default_factory=dict)
    impacts: list[dict[str, Any]] = field(default_factory=list)


class ReconPipeline:
    """Bitta run uchun quvur."""

    def __init__(
        self,
        job: Job,
        aoi: dict[str, Any],
        area_km2: float,
        run_settings: RunSettings,
        source: DataSource,
        gateway: GEEGateway | None = None,
        now: int | None = None,
        user_id: int = 0,
    ) -> None:
        self.job = job
        self.run_id = job.run_id
        self.aoi = aoi
        self.area_km2 = area_km2
        self.s = run_settings
        self.source = source
        self.gw = gateway
        self.now = now or now_ts()
        self.state = PipelineState()
        self.ctx = CallContext(run_id=self.run_id, on_event=self._on_gateway_event)
        self.user_id = user_id
        self.producers: dict[str, str] = {}  # qatlam nomi -> "usul:analizator:versiya"
        self.model_notes: list[str] = []

    def _run(self, name: str, data: AnalyzerInput) -> Any:
        """Analizatorni registrdan nomi bilan oladi, bajaradi va qatlamlar muallifini yozib qo'yadi."""
        an = get_analyzer(name)
        out = an.run(data)
        for lname in out.layers:
            self.producers[lname] = producer_of(an)
        return out

    # ------------------------------------------------------------------
    async def _on_gateway_event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "failover":
            self.job.emit("failover", "Zaxira GEE loyihasiga oʻtildi", data=data)
            async with db.session_scope() as s:
                run = await s.get(RunModel, self.run_id)
                if run is not None:
                    run.failover = 1
                    await s.commit()

    def _progress(self, stage: int, message: str, frac: float = 0.0, data: dict[str, Any] | None = None) -> None:
        # Bosqichlar og'irligi: yuklash va tahlil eng uzun
        weights = {1: 0.01, 2: 0.01, 3: 0.04, 4: 0.01, 5: 0.40, 6: 0.08, 7: 0.25, 8: 0.10, 9: 0.04, 10: 0.06}
        base = sum(w for k, w in weights.items() if k < stage)
        self.job.emit("progress", message, stage=stage, progress=base + weights[stage] * frac, data=data)

    # ------------------------------------------------------------------
    async def run(self) -> None:
        try:
            if self.gw is not None:
                self.gw.configure(self.s)
            if not self.source.is_configured():
                raise GEENotConfiguredError()
            self._progress(1, "Hudud tasdiqlandi", 1.0, {"area_km2": round(self.area_km2, 4)})
            await self._stage_grid()
            await self._stage_discovery()
            if await self._stage_fingerprint():
                return
            await self._stage_download()
            await self._stage_weather()
            await self._stage_analysis()
            await self._stage_render()
            await self._stage_persist()
            await self._stage_report()
            self.job.emit("done", "Rekognossirovka yakunlandi", stage=10, progress=1.0, data={"run_id": self.run_id})
            logger.info(f"Run #{self.run_id} yakunlandi")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._fail(e)
        finally:
            self.state = PipelineState()
            gc.collect()

    async def _fail(self, e: Exception) -> None:
        code = e.code if isinstance(e, AppError) else "PIPELINE_ERROR"
        msg = e.message_uz if isinstance(e, AppError) else f"Kutilmagan xatolik: {str(e)[:300]}"
        logger.exception(f"Run #{self.run_id} xato bilan tugadi: {e}")
        st.delete_run_dir(self.run_id)
        async with db.session_scope() as s:
            run = await s.get(RunModel, self.run_id)
            if run is not None:
                run.status = JobStatus.FAILED
                run.error_code, run.error_message = code, msg
                run.completed_at = now_ts()
                await s.commit()
        self.job.emit("error", msg, data={"code": code})

    # ------------------------------------------------------------------
    # 2. To'r
    # ------------------------------------------------------------------
    async def _stage_grid(self) -> None:
        log_step(2, 10, "EPSG:3857 toʻri")
        grid = build_grid(self.aoi, self.s.analysis_resolution_m)
        mask = rasterize_aoi(self.aoi, grid)
        if not mask.any():
            mask[grid.height // 2, grid.width // 2] = True  # juda kichik AOI: kamida bitta piksel
        self.state.grid, self.state.aoi_mask = grid, mask
        async with db.session_scope() as s:
            run = await s.get(RunModel, self.run_id)
            if run is not None:
                run.grid_json = grid.to_json()
                await s.commit()
        self._progress(2, f"Toʻr: {grid.width}×{grid.height} piksel, {grid.res_m:g} m", 1.0, {"grid": grid.to_dict()})

    # ------------------------------------------------------------------
    # 3. Kadrlarni topish
    # ------------------------------------------------------------------
    async def _stage_discovery(self) -> None:
        log_step(3, 10, "Kadrlarni qidirish")
        self._progress(3, "Sunʼiy yoʻldosh kadrlari qidirilmoqda")
        start = self.now - self.s.lookback_days * 86400
        disc = await self.source.discover(self.aoi, start, self.now, self.s, self.ctx)
        self.state.discovery = disc
        self.state.observations = group_observations(disc.scenes)
        counts: dict[str, int] = {}
        for o in self.state.observations:
            counts[SENSOR_NAMES_UZ[o.sensor]] = counts.get(SENSOR_NAMES_UZ[o.sensor], 0) + 1
        self._progress(
            3,
            f"{len(disc.scenes)} ta kadr, {len(self.state.observations)} ta kuzatuv topildi",
            1.0,
            {"scene_count": len(disc.scenes), "observations": counts},
        )

    # ------------------------------------------------------------------
    # 4. Barmoq izi va takrorlanishni tekshirish
    # ------------------------------------------------------------------
    async def _stage_fingerprint(self) -> bool:
        """True qaytarsa — yangi ma'lumot yo'q, mavjud run ko'rsatiladi va quvur to'xtaydi."""
        log_step(4, 10, "Barmoq izi")
        assert self.state.discovery is not None
        ids = [f"{sc.dataset}/{sc.scene_id}" for sc in self.state.discovery.scenes]
        # Foydalanuvchi ham barmoq iziga kiradi: har kim o'z maydonlarini va hisobotlarini oladi
        fp = compute_recon_fingerprint(self.aoi, ids + [f"__user__:{self.user_id}"])
        self.state.fingerprint = fp
        async with db.session_scope() as s:
            existing = (
                await s.execute(
                    select(RunModel)
                    .where(
                        RunModel.fingerprint == fp,
                        RunModel.status == JobStatus.COMPLETED,
                        RunModel.id != self.run_id,
                        RunModel.user_id == self.user_id,
                    )
                    .order_by(RunModel.id.desc())
                )
            ).scalars().first()
            if existing is None:
                run = await s.get(RunModel, self.run_id)
                if run is not None:
                    run.fingerprint = fp
                    await s.commit()
        if existing is not None:
            existing_id = existing.id
            st.delete_run_dir(self.run_id)
            await delete_run_records(self.run_id)
            self.job.emit(
                "duplicate",
                "Yangi sunʼiy yoʻldosh maʼlumoti yoʻq",
                stage=4,
                progress=1.0,
                data={"existing_run_id": existing_id},
            )
            return True
        self._progress(4, "Yangi maʼlumot: tahlil davom etadi", 1.0, {"fingerprint": fp.hex()})
        return False

    # ------------------------------------------------------------------
    # 5. Yuklash
    # ------------------------------------------------------------------
    async def _stage_download(self) -> None:
        log_step(5, 10, "Yuklash")
        assert self.state.grid is not None and self.state.discovery is not None
        grid, disc = self.state.grid, self.state.discovery
        items: list[tuple[str, Any]] = []
        if disc.dem is not None:
            items.append(("dem", disc.dem))
        if disc.smap is not None:
            items.append(("smap", disc.smap))
        items += [(o.key, o) for o in self.state.observations]
        if not items:
            self._progress(5, "Yuklanadigan maʼlumot yoʻq", 1.0)
            return
        for i, (key, item) in enumerate(items):
            label = SENSOR_NAMES_UZ[item.sensor]
            t = item.obs_time if isinstance(item, Observation) else item.acq_time
            self._progress(5, f"{label}: {fmt_local(t)} yuklanmoqda", i / len(items))
            if isinstance(item, Observation):
                arrays = await self.source.download_observation(item, grid, self.s, self.ctx)
            else:
                arrays = await self.source.download_static(item, grid, self.s, self.ctx)
            await asyncio.to_thread(st.save_arrays, st.raw_path(self.run_id, key), arrays)
            nbytes = int(sum(a.nbytes for a in arrays.values()))
            self.state.downloaded[key] = {"bands": sorted(arrays), "bytes": nbytes}
            del arrays
            self._progress(5, f"{label}: {fmt_local(t)} qabul qilindi", (i + 1) / len(items))

    # ------------------------------------------------------------------
    # 6. Ob-havo
    # ------------------------------------------------------------------
    async def _stage_weather(self) -> None:
        log_step(6, 10, "Ob-havo")
        self._progress(6, "Ob-havo maʼlumotlari olinmoqda (ERA5-Land, GFS, CHIRPS)")
        self.state.weather = await self.source.fetch_weather(self.aoi, self.area_km2, self.now, self.s, self.ctx)
        w = self.state.weather
        self._progress(
            6,
            f"Ob-havo: {len(w.hourly)} ta soatlik, {len(w.chirps_daily)} ta kunlik yozuv",
            1.0,
        )

    # ------------------------------------------------------------------
    # 7. Tahlil
    # ------------------------------------------------------------------
    def _add_layers(
        self,
        layers: dict[str, np.ndarray],
        stats: dict[str, dict[str, Any]],
        acq_time: int,
        sensor: SensorKind,
        dataset: str,
        scene_ids: list[str],
        derived_key: str,
        cloud_mask: np.ndarray | None = None,
        prev_time: int | None = None,
    ) -> None:
        mask = self.state.aoi_mask
        for name, arr in layers.items():
            if name not in LAYER_SPECS:
                continue
            # Yer qoplamida "noma'lum" (0) sinf yaroqli piksel hisoblanmaydi
            q_arr = np.where(arr == C.CLASS_UNKNOWN, np.nan, arr) if name == "landcover" else arr
            q = evaluate_layer_quality(q_arr, mask, cloud_mask)
            self.state.layers.append(
                LayerRecord(
                    name=name,
                    acq_time=acq_time,
                    sensor=LAYER_SPECS[name].sensor if LAYER_SPECS[name].sensor != SensorKind.DERIVED else sensor,
                    dataset=dataset,
                    scene_ids=scene_ids,
                    derived_key=derived_key,
                    stats=stats.get(name) or {},
                    valid_pct=q["valid_pct"],
                    cloud_masked_pct=q["cloud_masked_pct"],
                    quality_flag=q["quality_flag"],
                    prev_time=prev_time,
                    producer=self.producers.get(name, "rules:formula:rules-1.0"),
                )
            )

    def _mask_aoi(self, arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        m = self.state.aoi_mask
        assert m is not None
        out = {}
        for k, v in arrays.items():
            a = v.astype(np.float32, copy=True)
            a[~m] = np.nan
            out[k] = a
        return out

    def _analyze_all(self) -> None:
        """Sinxron tahlil (thread'da bajariladi). Har bir kuzatuv diskdan o'qiladi va diskka yoziladi."""
        assert self.state.grid is not None and self.state.aoi_mask is not None
        grid, aoi = self.state.grid, self.state.aoi_mask
        disc = self.state.discovery
        assert disc is not None
        px = grid.res_m
        row_area = grid.row_pixel_area_m2()

        # Relyef
        terrain: dict[str, np.ndarray] = {}
        if "dem" in self.state.downloaded and disc.dem is not None:
            raw = st.load_arrays(st.raw_path(self.run_id, "dem"))
            out = self._run("terrain", AnalyzerInput(arrays=raw, pixel_size_m=px, aoi_mask=aoi))
            layers = self._mask_aoi(out.layers)
            st.save_arrays(st.derived_path(self.run_id, "dem"), layers)
            self._add_layers(layers, out.stats, disc.dem.acq_time, SensorKind.DEM, disc.dem.dataset,
                             disc.dem.item_ids, "dem")
            terrain = {"depressions": layers["depressions"]}

        # SMAP
        smap_layer: np.ndarray | None = None
        series = self.state.weather.smap_series if self.state.weather else []
        sm_an = get_analyzer("soil_moisture")
        if "smap" in self.state.downloaded and disc.smap is not None:
            raw = st.load_arrays(st.raw_path(self.run_id, "smap"))
            out = sm_an.run(AnalyzerInput(arrays=raw, pixel_size_m=px, aoi_mask=aoi, extra={"series": series}))
            layers = self._mask_aoi(out.layers)
            st.save_arrays(st.derived_path(self.run_id, "smap"), layers)
            self._add_layers(layers, out.stats, disc.smap.acq_time, SensorKind.SMAP, disc.smap.dataset,
                             disc.smap.item_ids, "smap")
            smap_layer = layers["sm_surface"]
            self.state.soil_trend = out.metadata.get("trend", {})
        elif series:
            dummy = {"sm_surface": np.full((1, 1), np.nan, np.float32), "sm_rootzone": np.full((1, 1), np.nan, np.float32)}
            self.state.soil_trend = sm_an.run(AnalyzerInput(arrays=dummy, extra={"series": series})).metadata.get("trend", {})

        # Sentinel-1
        s1_obs = [o for o in self.state.observations if o.sensor == SensorKind.SENTINEL1]
        prev_s1: tuple[Observation, np.ndarray] | None = None
        for o in s1_obs:
            raw = st.load_arrays(st.raw_path(self.run_id, o.key))
            out = self._run("sar", AnalyzerInput(arrays=raw, pixel_size_m=px, aoi_mask=aoi))
            layers = self._mask_aoi(out.layers)
            if prev_s1 is not None:
                ch = self._run("change",
                    AnalyzerInput(arrays={"vv": layers["vv"]}, aoi_mask=aoi,
                                  extra={"previous": {"vv": prev_s1[1]}, "names": ["vv"]})
                )
                layers.update(ch.layers)
                self._add_layers(ch.layers, ch.stats, o.obs_time, SensorKind.SENTINEL1, D.S1_COLLECTION,
                                 o.scene_ids, o.key, prev_time=prev_s1[0].obs_time)
                self.state.changes["sentinel1"].append({
                    "prev_ts": prev_s1[0].obs_time, "ts": o.obs_time,
                    "mean_delta": ch.stats["delta_vv"]["mean"], "stats": ch.stats["delta_vv"],
                })
            st.save_arrays(st.derived_path(self.run_id, o.key), layers)
            self._add_layers({k: v for k, v in layers.items() if k != "delta_vv"}, out.stats, o.obs_time,
                             SensorKind.SENTINEL1, D.S1_COLLECTION, o.scene_ids, o.key)
            self._record_obs_quality(o, layers["vv"], None)
            prev_s1 = (o, layers["vv"])
            del raw, out
        del prev_s1

        # Landsat
        ls_obs = [o for o in self.state.observations if o.sensor == SensorKind.LANDSAT]
        landsat_ndvi: list[tuple[Observation, np.ndarray]] = []
        for o in ls_obs:
            raw = st.load_arrays(st.raw_path(self.run_id, o.key))
            out = self._run("thermal", AnalyzerInput(arrays=raw, pixel_size_m=px, aoi_mask=aoi))
            layers = self._mask_aoi(out.layers)
            cloud = out.metadata.get("cloud_mask")
            st.save_arrays(st.derived_path(self.run_id, o.key), layers)
            self._add_layers(layers, out.stats, o.obs_time, SensorKind.LANDSAT, ",".join(o.datasets),
                             o.scene_ids, o.key, cloud_mask=cloud)
            self._record_obs_quality(o, layers["lst"], cloud)
            landsat_ndvi.append((o, layers["landsat_ndvi"]))
            del raw, out

        # Sentinel-2
        s2_obs = [o for o in self.state.observations if o.sensor == SensorKind.SENTINEL2]
        prev: dict[str, Any] | None = None
        for o in s2_obs:
            raw = st.load_arrays(st.raw_path(self.run_id, o.key))
            cs = raw.get(D.CLOUD_SCORE_BAND)
            scl = raw.get("SCL")
            cloud = np.zeros(aoi.shape, dtype=bool)
            if cs is not None:
                with np.errstate(invalid="ignore"):
                    cloud |= cs < self.s.cloud_score_threshold
            if scl is not None:
                cloud |= np.isin(np.nan_to_num(scl, nan=0), C.SCL_CLOUD_CLASSES)
            nodata = np.isnan(raw["B4"]) | np.isnan(raw["B8"])
            if scl is not None:
                nodata |= np.isin(np.nan_to_num(scl, nan=0), C.SCL_INVALID_CLASSES)
            cloud &= ~nodata
            refl = {b: raw[b] for b in D.S2_REFLECTANCE_BANDS}
            masked = {b: np.where(cloud | nodata, np.nan, v).astype(np.float32) for b, v in refl.items()}

            idx = self._run("indices", AnalyzerInput(arrays=masked, pixel_size_m=px, aoi_mask=aoi))
            rgbf = self._run("rgb", AnalyzerInput(arrays=masked, pixel_size_m=px, aoi_mask=aoi))
            layers = self._mask_aoi({**idx.layers, **rgbf.layers})
            stats = {**idx.stats, **rgbf.stats}

            # Landcover kirishlari: eng yaqin S1 (≤ 3 kun), relyef, SMAP
            lc_in: dict[str, np.ndarray] = {k: layers[k] for k in ("ndvi", "ndwi", "mndwi", "ndmi", "bsi", "ndbi", "nbr", "texture")}
            near_s1 = min(s1_obs, key=lambda x: abs(x.obs_time - o.obs_time), default=None)
            sar_used = None
            if near_s1 is not None and abs(near_s1.obs_time - o.obs_time) <= SAR_PAIR_MAX_DAYS * 86400:
                s1d = st.load_arrays(st.derived_path(self.run_id, near_s1.key), ["vv", "vh"])
                lc_in.update(s1d)
                sar_used = near_s1.obs_time
            if "depressions" in terrain:
                lc_in["depressions"] = terrain["depressions"]
            if smap_layer is not None:
                lc_in["sm_surface"] = smap_layer
            extra: dict[str, Any] = {"cloud_mask": cloud | nodata, "scl": scl}
            if prev is not None:
                extra["delta_nbr"] = layers["nbr"] - prev["nbr"]
            # Yer qoplami sloti: qoidaviy (standart) yoki sozlamada tanlangan ML/CV modeli
            lc_inputs = {**masked, **{k: v for k, v in layers.items()}, **lc_in}
            lc = self._run(self.s.landcover_analyzer, AnalyzerInput(arrays=lc_inputs, pixel_size_m=px, aoi_mask=aoi, extra=extra))
            if "confidence" not in lc.layers:
                lc.layers["confidence"] = lc.confidence if lc.confidence is not None else np.full(aoi.shape, np.nan, np.float32)
                self.producers["confidence"] = self.producers.get("landcover", "")
            layers.update(lc.layers)
            stats.update(lc.stats)
            stats.setdefault("confidence", calc_stats(lc.layers["confidence"], aoi))
            classes = lc.metadata.get("classes")
            if classes is None:
                classes = np.nan_to_num(lc.layers["landcover"], nan=0).astype(np.uint8)
            self._record_class_areas(o.obs_time, classes, lc.layers["confidence"], row_area, sar_used)

            # Qo'shimcha ML/CV qatlamlari (registrdagi slot="extra" analizatorlar)
            for model in analyzers_for("s2_observation", "extra"):
                try:
                    mo = self._run(model.name, AnalyzerInput(arrays=lc_inputs, pixel_size_m=px, aoi_mask=aoi, extra=extra))
                except KeyError as e:
                    self.model_notes.append(f"{model.name}: kirish maʼlumoti yoʻq ({e})")
                    continue
                layers.update(self._mask_aoi(mo.layers))
                stats.update(mo.stats)

            # O'zgarishlar (oldingi haqiqiy S2 kuzatuvga nisbatan)
            if prev is not None:
                ch = self._run("change",
                    AnalyzerInput(
                        arrays={k: layers[k] for k in CHANGE_LAYERS_S2},
                        aoi_mask=aoi,
                        extra={"previous": prev, "names": CHANGE_LAYERS_S2,
                               "classes": classes, "prev_classes": prev["classes"]},
                    )
                )
                layers.update(ch.layers)
                self._add_layers(ch.layers, ch.stats, o.obs_time, SensorKind.SENTINEL2, D.S2_COLLECTION,
                                 o.scene_ids, o.key, prev_time=prev["ts"])
                self.state.changes["sentinel2"].append({
                    "prev_ts": prev["ts"],
                    "ts": o.obs_time,
                    **{f"delta_{n}": ch.stats.get(f"delta_{n}") for n in CHANGE_LAYERS_S2},
                    "transitions": ch.metadata.get("transitions"),
                })

            # Kesishgan tekshiruv (Landsat ≤ 3 kun)
            for lo, lndvi in landsat_ndvi:
                dt_days = (lo.obs_time - o.obs_time) / 86400.0
                if abs(dt_days) <= C.CROSS_CHECK_MAX_DAYS:
                    cc = cross_check_ndvi(layers["ndvi"], lndvi, dt_days, aoi)
                    cc.update({"s2_ts": o.obs_time, "landsat_ts": lo.obs_time})
                    self.state.cross_checks.append(cc)

            # RGB uchun bulut bilan niqoblanmagan aks ettirish saqlanadi (faqat no-data niqobi)
            rgb_store = self._mask_aoi({b: np.where(nodata, np.nan, v) for b, v in refl.items()})
            qa_store = {k: raw[k] for k in ("SCL", D.CLOUD_SCORE_BAND) if k in raw}
            st.save_arrays(st.raw_path(self.run_id, o.key), {**rgb_store, **self._mask_aoi(qa_store)})
            st.save_arrays(st.derived_path(self.run_id, o.key), layers)
            self._add_layers({k: v for k, v in layers.items() if not k.startswith("delta_") and k != "class_change"},
                             stats, o.obs_time, SensorKind.SENTINEL2, D.S2_COLLECTION, o.scene_ids, o.key, cloud_mask=cloud)
            # RGB qatlamlari (PNG render bosqichida yaratiladi)
            for name in ("rgb", "false_color"):
                q = evaluate_layer_quality(rgb_store["B4"], aoi, cloud)
                self.state.layers.append(LayerRecord(
                    name=name, acq_time=o.obs_time, sensor=SensorKind.SENTINEL2, dataset=D.S2_COLLECTION,
                    scene_ids=o.scene_ids, derived_key=o.key, stats={}, valid_pct=q["valid_pct"],
                    cloud_masked_pct=q["cloud_masked_pct"], quality_flag=q["quality_flag"],
                ))
            self._record_obs_quality(o, layers["ndvi"], cloud)
            prev = {**{k: layers[k] for k in CHANGE_LAYERS_S2}, "classes": classes, "ts": o.obs_time}
            del raw, masked, refl, idx, rgbf, lc, lc_in, layers, rgb_store
            gc.collect()
        del prev, landsat_ndvi

    def _record_obs_quality(self, o: Observation, arr: np.ndarray, cloud: np.ndarray | None) -> None:
        q = evaluate_layer_quality(arr, self.state.aoi_mask, cloud)
        self.state.obs_quality.append({
            "key": o.key,
            "sensor": SENSOR_NAMES_UZ[o.sensor],
            **ts_fields("obs_time", o.obs_time),
            "scene_ids": o.scene_ids,
            "scene_times_local": [fmt_local(sc.acq_time) for sc in o.scenes],
            "metadata_cloud_pct": [sc.cloud_pct for sc in o.scenes],
            "valid_pct": q["valid_pct"],
            "cloud_masked_pct": q["cloud_masked_pct"],
            "quality_flag": QualityFlag(q["quality_flag"]).name,
            "low_confidence": q["is_low_confidence"],
        })

    def _record_class_areas(
        self, ts: int, classes: np.ndarray, conf: np.ndarray, row_area: np.ndarray, sar_ts: int | None
    ) -> None:
        aoi = self.state.aoi_mask
        assert aoi is not None
        area_grid = np.broadcast_to(row_area[:, None], classes.shape)
        total_area = float(area_grid[aoi].sum())
        rows = []
        for code, label in C.CLASS_LABELS_UZ.items():
            m = aoi & (classes == code)
            n = int(m.sum())
            if n == 0:
                continue
            a = float(area_grid[m].sum())
            mc = conf[m]
            mc = mc[~np.isnan(mc)]
            rows.append({
                "class_code": code,
                "label_uz": label,
                "pixel_count": n,
                "area_m2": a,
                "pct": round(a / total_area * 100.0, 2) if total_area > 0 else 0.0,
                "mean_confidence": round(float(mc.mean()), 3) if mc.size else None,
            })
        known = sum(r["pct"] for r in rows if r["class_code"] != C.CLASS_UNKNOWN)
        self.state.class_areas.append({
            "acq_time": ts,
            "classes": rows,
            "classified_pct": round(known, 2),
            "low_confidence": known < C.LOW_VALID_PIXEL_PCT_THRESHOLD,
            "sar_obs_time": sar_ts,
        })

    async def _stage_analysis(self) -> None:
        log_step(7, 10, "Tahlil")
        self._progress(7, "Indekslar, SAR, relyef, LST va yer qoplami hisoblanmoqda")
        await asyncio.to_thread(self._analyze_all)

        # Ob-havo ta'siri
        w = self.state.weather or WeatherBundle([], [], [])
        dep = next((lr for lr in self.state.layers if lr.name == "depressions"), None)
        dep_pct = dep.stats.get("mean") * 100.0 if dep and dep.stats.get("mean") is not None else None
        lst_obs = [{"ts": lr.acq_time, "mean": lr.stats.get("mean")} for lr in self.state.layers if lr.name == "lst"]
        ndvi_changes = [
            {"prev_ts": c["prev_ts"], "ts": c["ts"], "mean_delta": (c.get("delta_ndvi") or {}).get("mean")}
            for c in self.state.changes["sentinel2"]
        ]
        self.state.impacts = analyze_weather_impact(
            w.hourly,
            chirps_daily=w.chirps_daily,
            depression_pct=dep_pct,
            soil_moisture_trend=self.state.soil_trend,
            vv_changes=self.state.changes["sentinel1"],
            ndvi_changes=ndvi_changes,
            lst_observations=lst_obs,
        )
        self._progress(7, f"{len(self.state.layers)} ta qatlam hisoblandi", 1.0)

    # ------------------------------------------------------------------
    # 8. Render
    # ------------------------------------------------------------------
    def _render_all(self) -> None:
        by_key: dict[str, list[LayerRecord]] = {}
        for lr in self.state.layers:
            by_key.setdefault(lr.derived_key, []).append(lr)
        for key, recs in by_key.items():
            derived = st.load_arrays(st.derived_path(self.run_id, key))
            raw = None
            for lr in recs:
                out = st.png_path(self.run_id, lr.name, lr.acq_time)
                if lr.name in ("rgb", "false_color"):
                    if raw is None:
                        raw = st.load_arrays(st.raw_path(self.run_id, key), ["B2", "B3", "B4", "B8"])
                    spec = LAYER_SPECS[lr.name]
                    bands = ("B4", "B3", "B2") if lr.name == "rgb" else ("B8", "B4", "B3")
                    lr.vmin, lr.vmax = render_composite_png(
                        raw[bands[0]], raw[bands[1]], raw[bands[2]], out, (spec.vmin or 0.0, spec.vmax or 0.3)
                    )
                else:
                    lr.vmin, lr.vmax = render_layer_png(lr.name, derived[lr.name], out)
                lr.png = str(out)
            del derived, raw

    async def _stage_render(self) -> None:
        log_step(8, 10, "Render")
        self._progress(8, "Shaffof PNG qatlamlar yaratilmoqda")
        await asyncio.to_thread(self._render_all)
        self._progress(8, "PNG qatlamlar tayyor", 1.0)

    # ------------------------------------------------------------------
    # 9. Saqlash
    # ------------------------------------------------------------------
    def build_summary(self) -> dict[str, Any]:
        """Barcha raqamli natijalar: API, AI va hisobot uchun yagona manba."""
        disc = self.state.discovery
        grid = self.state.grid
        assert disc is not None and grid is not None
        w = self.state.weather or WeatherBundle([], [], [])

        sources = []
        for sensor in (SensorKind.SENTINEL2, SensorKind.SENTINEL1, SensorKind.LANDSAT):
            obs = [o for o in self.state.observations if o.sensor == sensor]
            sources.append({
                "sensor": SENSOR_NAMES_UZ[sensor],
                "datasets": sorted({d for o in obs for d in o.datasets}),
                "bands": BANDS_PROVIDED[sensor],
                "observation_count": len(obs),
                "observations": [ts_fields("obs_time", o.obs_time) | {"scene_ids": o.scene_ids} for o in obs],
                "status": "ok" if obs else C.NO_DATA_UZ,
            })
        for prod, sensor in ((disc.dem, SensorKind.DEM), (disc.smap, SensorKind.SMAP)):
            sources.append({
                "sensor": SENSOR_NAMES_UZ[sensor],
                "datasets": [prod.dataset] if prod else [],
                "bands": BANDS_PROVIDED[sensor],
                "observation_count": 1 if prod else 0,
                "observations": [ts_fields("acq_time", prod.acq_time) | {"items": prod.item_ids[:20]}] if prod else [],
                "time_range_local": [fmt_local(t) for t in prod.time_range] if prod and prod.time_range else None,
                "status": "ok" if prod else C.NO_DATA_UZ,
            })

        stats_by_date: dict[str, list[dict[str, Any]]] = {}
        for lr in self.state.layers:
            if lr.name in ("rgb", "false_color"):
                continue
            s = lr.stats or {}
            stats_by_date.setdefault(lr.name, []).append({
                **ts_fields("acq_time", lr.acq_time),
                **({"prev_time_local": fmt_local(lr.prev_time)} if lr.prev_time else {}),
                "mean": _r(s.get("mean")), "min": _r(s.get("min")), "max": _r(s.get("max")),
                "p10": _r(s.get("p10")), "p90": _r(s.get("p90")),
                "valid_pct": lr.valid_pct,
                "cloud_masked_pct": lr.cloud_masked_pct,
                "quality_flag": QualityFlag(lr.quality_flag).name,
                "low_confidence": lr.quality_flag in (QualityFlag.LOW_CONFIDENCE, QualityFlag.NO_DATA),
                "unit": LAYER_SPECS[lr.name].unit,
            })

        terrain = {
            n: stats_by_date[n][0] for n in ("elevation", "slope", "tri", "tpi", "depressions") if n in stats_by_date
        }
        if "depressions" in terrain and terrain["depressions"]["mean"] is not None:
            terrain["low_area_pct"] = round(terrain["depressions"]["mean"] * 100.0, 2)

        class_areas = [
            {
                **ts_fields("acq_time", ca["acq_time"]),
                "classified_pct": ca["classified_pct"],
                "low_confidence": ca["low_confidence"],
                "sar_obs_time_local": fmt_local(ca["sar_obs_time"]) if ca["sar_obs_time"] else None,
                "classes": [
                    {
                        "class_code": c["class_code"],
                        "label_uz": c["label_uz"],
                        "area_ha": round(c["area_m2"] / 10000.0, 3),
                        "pct": c["pct"],
                        "mean_confidence": c["mean_confidence"],
                    }
                    for c in ca["classes"]
                ],
            }
            for ca in self.state.class_areas
        ]

        def ch_s2(c: dict[str, Any]) -> dict[str, Any]:
            return {
                **ts_fields("prev_time", c["prev_ts"]),
                **ts_fields("time", c["ts"]),
                **{k: {kk: _r(vv) for kk, vv in (c.get(k) or {}).items() if kk in ("mean", "min", "max", "count")}
                   for k in (f"delta_{n}" for n in CHANGE_LAYERS_S2)},
                "transitions": c.get("transitions"),
            }

        changes = {
            "sentinel2": [ch_s2(c) for c in self.state.changes["sentinel2"]],
            "sentinel1": [
                {**ts_fields("prev_time", c["prev_ts"]), **ts_fields("time", c["ts"]),
                 "delta_vv_db": {k: _r(v) for k, v in c["stats"].items() if k in ("mean", "min", "max", "count")}}
                for c in self.state.changes["sentinel1"]
            ],
            "soil_moisture": _trend_out(self.state.soil_trend),
            "note_uz": "Oʻzgarishlar faqat ketma-ket haqiqiy kuzatuvlar orasida hisoblangan; interpolatsiya yoʻq.",
        }

        weather = _weather_summary(w, self.now)
        quality_flags = [
            {"layer": lr.name, **ts_fields("acq_time", lr.acq_time), "valid_pct": lr.valid_pct,
             "flag": QualityFlag(lr.quality_flag).name,
             "message_uz": C.LOW_CONFIDENCE_UZ if lr.quality_flag == QualityFlag.LOW_CONFIDENCE else
             (C.NO_DATA_UZ if lr.quality_flag == QualityFlag.NO_DATA else "bulut koʻp")}
            for lr in self.state.layers if lr.quality_flag != QualityFlag.GOOD
        ]
        return {
            "run": {
                "id": self.run_id,
                "area_km2": round(self.area_km2, 4),
                **ts_fields("created_at", self.now),
                "lookback_days": self.s.lookback_days,
                "resolution_m": grid.res_m,
                "grid": {"width": grid.width, "height": grid.height, "bounds_latlon": grid.bounds_latlon()},
                "aoi_bbox_latlon": grid.bounds_latlon(),
            },
            "sources": sources,
            "observations": self.state.obs_quality,
            "class_areas": class_areas,
            "stats_by_date": stats_by_date,
            "terrain": terrain,
            "soil_moisture": {
                "product": ts_fields("acq_time", disc.smap.acq_time) | {"dataset": disc.smap.dataset} if disc.smap else None,
                "surface": stats_by_date.get("sm_surface", [None])[0],
                "rootzone": stats_by_date.get("sm_rootzone", [None])[0],
                "trend": _trend_out(self.state.soil_trend),
            },
            "changes": changes,
            "cross_check": [
                {k: v for k, v in cc.items() if k not in ("s2_ts", "landsat_ts")}
                | ts_fields("s2_time", cc["s2_ts"]) | ts_fields("landsat_time", cc["landsat_ts"])
                for cc in self.state.cross_checks
            ],
            "weather": weather,
            "weather_impact": self.state.impacts,
            "analyzers": {
                "landcover": self.s.landcover_analyzer,
                "producers": dict(sorted(set(self.producers.items()))),
                "notes_uz": self.model_notes,
            },
            "quality_flags": quality_flags,
        }

    async def _stage_persist(self) -> None:
        log_step(9, 10, "Saqlash")
        self._progress(9, "Natijalar saqlanmoqda")
        assert self.state.discovery is not None
        summary = self.build_summary()
        await asyncio.to_thread(st.save_json, st.summary_path(self.run_id), summary)
        obs_by_scene = {sc.scene_id: o.obs_time for o in self.state.observations for sc in o.scenes}
        w = self.state.weather or WeatherBundle([], [], [])
        async with db.session_scope() as s:
            for sc in self.state.discovery.scenes:
                s.add(SceneModel(
                    run_id=self.run_id, scene_id=sc.scene_id, sensor=int(sc.sensor), platform=sc.platform,
                    dataset=sc.dataset, acq_time=sc.acq_time, obs_time=obs_by_scene.get(sc.scene_id, sc.acq_time),
                    cloud_pct=sc.cloud_pct, orbit_pass=sc.orbit_pass, used=1,
                ))
            for lr in self.state.layers:
                spec = LAYER_SPECS[lr.name]
                lm = LayerModel(
                    run_id=self.run_id, name=lr.name, kind=int(spec.kind), sensor=int(lr.sensor),
                    dataset=lr.dataset, acq_time=lr.acq_time, prev_time=lr.prev_time,
                    scene_ids=json.dumps(lr.scene_ids), file_path=lr.png, unit=spec.unit,
                    min_val=lr.vmin, max_val=lr.vmax, valid_pct=lr.valid_pct,
                    cloud_masked_pct=lr.cloud_masked_pct, quality_flag=int(lr.quality_flag), producer=lr.producer,
                )
                s.add(lm)
                if lr.stats:
                    lm.stats = LayerStatsModel(
                        count=int(lr.stats.get("count") or 0), mean_val=lr.stats.get("mean"),
                        std_val=lr.stats.get("std"), median_val=lr.stats.get("median"),
                        p10=lr.stats.get("p10"), p90=lr.stats.get("p90"),
                    )
            for ca in self.state.class_areas:
                for c in ca["classes"]:
                    s.add(ClassAreaModel(
                        run_id=self.run_id, acq_time=ca["acq_time"], class_code=c["class_code"],
                        pixel_count=c["pixel_count"], area_m2=c["area_m2"], pct=c["pct"],
                        mean_confidence=c["mean_confidence"],
                    ))
            for r in w.hourly + w.chirps_daily:
                s.add(WeatherModel(run_id=self.run_id, **{k: r.get(k) for k in _WEATHER_COLS if k in r},
                                   is_forecast=int(r.get("is_forecast") or 0)))
            run = await s.get(RunModel, self.run_id)
            if run is not None:
                run.status = JobStatus.COMPLETED
                run.completed_at = now_ts()
                run.fingerprint = self.state.fingerprint
            await s.commit()
        self._progress(9, "Natijalar saqlandi", 1.0)

    # ------------------------------------------------------------------
    # 10. AI hisobot (xato bo'lsa ham run muvaffaqiyatli)
    # ------------------------------------------------------------------
    async def _stage_report(self) -> None:
        log_step(10, 10, "AI hisobot")
        self._progress(10, "AI hisoboti tayyorlanmoqda")
        summary = st.load_json(st.summary_path(self.run_id))
        try:
            async with db.session_scope() as s:
                run = await s.get(RunModel, self.run_id)
                assert run is not None
                await generate_report_for_run(s, run, summary, self.s)
            self._progress(10, "AI hisoboti tayyor", 1.0)
        except AppError as e:
            self.job.emit("warning", f"AI hisobotini tuzib boʻlmadi: {e.message_uz}", data={"code": e.code})


_WEATHER_COLS = (
    "source", "ts", "period_s", "issued_ts", "temp_c", "temp_min_c", "temp_max_c", "dewpoint_c", "rh_pct",
    "precip_mm", "precip_min_mm", "precip_max_mm", "wind_speed_ms", "wind_min_ms", "wind_max_ms", "wind_deg",
    "cloud_pct", "soil_moisture",
)


def _r(v: Any, nd: int = 4) -> Any:
    return round(float(v), nd) if isinstance(v, int | float) and v is not None else v


def _trend_out(t: dict[str, Any]) -> dict[str, Any]:
    if not t or not t.get("available"):
        return {"available": False, "message_uz": C.NO_DATA_UZ}
    return {
        "available": True,
        **ts_fields("first_time", t["first_ts"]),
        **ts_fields("last_time", t["last_ts"]),
        "first_m3m3": _r(t["first"]),
        "last_m3m3": _r(t["last"]),
        "delta_m3m3": _r(t["delta"]),
        "slope_per_day": _r(t.get("slope_per_day"), 5),
        "n": t["n"],
        "source": D.SMAP_COLLECTION,
    }


def _weather_summary(w: WeatherBundle, now: int) -> dict[str, Any]:
    """Ob-havo xulosasi: o'tmish va prognoz bo'yicha yig'indilar va ekstremumlar (manba bilan)."""
    def block(recs: list[dict[str, Any]]) -> dict[str, Any]:
        if not recs:
            return {"available": False, "message_uz": C.NO_DATA_UZ}
        def ext(key: str, fn: Any) -> dict[str, Any] | None:
            vals = [r for r in recs if r.get(key) is not None]
            if not vals:
                return None
            r = fn(vals, key=lambda x: x[key])
            return {"value": _r(r[key], 2), **ts_fields("time", r["ts"]), "source": _src_key(r["source"])}
        precip = [r["precip_mm"] for r in recs if r.get("precip_mm") is not None]
        return {
            "available": True,
            **ts_fields("from", min(r["ts"] for r in recs)),
            **ts_fields("to", max(r["ts"] for r in recs)),
            "sources": sorted({_src_key(r["source"]) for r in recs}),
            "records": len(recs),
            "precip_total_mm": round(sum(precip), 2) if precip else None,
            "temp_min_c": ext("temp_min_c", min) or ext("temp_c", min),
            "temp_max_c": ext("temp_max_c", max) or ext("temp_c", max),
            "wind_max_ms": ext("wind_max_ms", max) or ext("wind_speed_ms", max),
            "daily_precip": [
                {**ts_fields("day", d["day_ts"]), "day_local": fmt_local_date(d["day_ts"]), "source": d["source"],
                 "precip_mm": d["precip_mm"]}
                for d in daily_precip(recs)
            ],
        }
    past = [r for r in w.hourly if not r.get("is_forecast")]
    fc = [r for r in w.hourly if r.get("is_forecast")]
    return {
        "past": block(past),
        "forecast": block(fc) | ({**ts_fields("gfs_run", w.gfs_run_ts)} if w.gfs_run_ts else {}),
        "chirps_daily": [
            {**ts_fields("day", d["ts"]), "day_local": fmt_local_date(d["ts"]), "precip_mm": _r(d["precip_mm"], 2),
             "source": "chirps"} for d in w.chirps_daily
        ],
        "era5_last": ts_fields("time", w.era5_last_ts),
        "notes_uz": w.notes,
    }


def _src_key(code: int) -> str:
    from backend.app.db.enums import WEATHER_SOURCE_KEYS

    return WEATHER_SOURCE_KEYS.get(WeatherSource(code), "unknown")


def make_runner(
    aoi: dict[str, Any],
    area_km2: float,
    run_settings: RunSettings,
    source: DataSource,
    gateway: GEEGateway | None,
    user_id: int = 0,
) -> Any:
    """JobManager uchun runner funksiyasi."""

    async def _runner(job: Job) -> None:
        await ReconPipeline(job, aoi, area_km2, run_settings, source, gateway, user_id=user_id).run()

    return _runner


async def create_run_row(
    aoi: dict[str, Any], area_km2: float, run_settings: RunSettings, user_id: int, name: str = ""
) -> int:
    """Yangi run (saqlanadigan maydon) qatorini RUNNING holatida yaratadi."""
    async with db.session_scope() as s:
        run = RunModel(
            status=JobStatus.RUNNING,
            user_id=user_id,
            name=name.strip()[:120] or f"Maydon {fmt_local(now_ts())}",
            aoi_geojson=json.dumps(aoi),
            area_km2=round(area_km2, 6),
            settings_json=run_settings.model_dump_json(),
            created_at=now_ts(),
        )
        s.add(run)
        await s.commit()
        return run.id


__all__ = [
    "ReconPipeline",
    "create_run_row",
    "group_observations",
    "make_runner",
    "StaticProduct",
]
