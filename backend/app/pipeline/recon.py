"""10 bosqichli asinxron rekognossirovka quvuri moduli.

SSE progress bildirishnomalari, bekor qilishni tekshirish,
tahlil, render va saqlash jarayonlari.
"""

import asyncio
import json
from typing import Any

import numpy as np
from sqlalchemy import select

from backend.app.ai.report_generator import generate_recon_report
from backend.app.analysis.interface import AnalyzerInput
from backend.app.analysis.quality import cross_check_ndvi
from backend.app.analysis.registry import get_analyzer
from backend.app.core.config import RUNS_DIR, settings
from backend.app.core.constants import CLASS_LABELS_UZ
from backend.app.core.errors import ConflictError
from backend.app.core.telemetry import log_step, logger
from backend.app.core.time import now_ts
from backend.app.db.enums import JobStatus, LayerKind, QualityFlag, SensorKind
from backend.app.db.models import (
    ClassAreaModel,
    LayerModel,
    LayerStatsModel,
    ReportModel,
    RunModel,
    SceneModel,
    WeatherModel,
)
from backend.app.db.session import async_session_maker
from backend.app.gee.datasets import S1_BANDS, S2_BANDS
from backend.app.gee.gateway import gateway
from backend.app.pipeline.cancellation import (
    is_cancellation_requested,
    register_active_run,
    unregister_active_run,
)
from backend.app.pipeline.fingerprint import compute_recon_fingerprint
from backend.app.pipeline.grid import compute_grid_dimensions, validate_aoi
from backend.app.pipeline.render import array_to_rgba_png
from backend.app.weather.impact import analyze_weather_impact

# SSE hodisalar navbati (run_id -> list of subscribers)
_event_subscribers: dict[int, list[asyncio.Queue]] = {}
_active_run_id: int | None = None


def get_active_run_id() -> int | None:
    """Ayni paytda ishlayotgan vazifa ID sini qaytaradi."""
    return _active_run_id


async def emit_recon_event(run_id: int, stage: int, message: str, data: dict[str, Any] | None = None) -> None:
    """SSE orqali mijozlarga jonli xabarlarni tarqatadi."""
    queues = _event_subscribers.get(run_id, [])
    payload = {
        "run_id": run_id,
        "stage": stage,
        "total_stages": 10,
        "message_uz": message,
        "data": data or {},
    }
    for q in queues:
        await q.put(payload)


def subscribe_run_events(run_id: int) -> asyncio.Queue:
    """Berilgan run_id uchun SSE oqimiga obuna bo'lish."""
    q: asyncio.Queue = asyncio.Queue()
    if run_id not in _event_subscribers:
        _event_subscribers[run_id] = []
    _event_subscribers[run_id].append(q)
    return q


def unsubscribe_run_events(run_id: int, q: asyncio.Queue) -> None:
    """SSE oqimidan obunani bekor qilish."""
    if run_id in _event_subscribers and q in _event_subscribers[run_id]:
        _event_subscribers[run_id].remove(q)


async def execute_reconnaissance_pipeline(aoi_geojson: dict[str, Any]) -> int:
    """Asosiy rekognossirovka jarayonini boshlaydi va run_id qaytaradi."""
    global _active_run_id

    if _active_run_id is not None:
        raise ConflictError()

    # 1. Validate AOI
    log_step(1, 10, "Hudud geometriyasi va maydoni tekshirilmoqda")
    area_km2 = validate_aoi(aoi_geojson, max_area_km2=settings.max_aoi_km2)

    # Bazada dastlabki run yaratish
    async with async_session_maker() as session:
        new_run = RunModel(
            fingerprint=b"",  # Bosqich 4 da to'ldiriladi
            status=JobStatus.RUNNING,
            aoi_geojson=json.dumps(aoi_geojson),
            area_km2=round(area_km2, 2),
            created_at=now_ts(),
        )
        session.add(new_run)
        await session.commit()
        await session.refresh(new_run)
        run_id = new_run.id

    _active_run_id = run_id
    task = asyncio.current_task()
    if task:
        register_active_run(run_id, task)

    try:
        await _run_pipeline_steps(run_id, aoi_geojson, area_km2)
        return run_id
    finally:
        _active_run_id = None
        unregister_active_run(run_id)


async def _run_pipeline_steps(run_id: int, aoi_geojson: dict[str, Any], area_km2: float) -> None:
    """10 ta bosqichni ketma-ket bajaruvchi ichki funksiya."""
    run_folder = RUNS_DIR / str(run_id)
    run_folder.mkdir(parents=True, exist_ok=True)

    await emit_recon_event(run_id, 1, "Hudud geometriyasi tasdiqlandi", {"area_km2": area_km2})

    # 2. Grid hisoblash
    log_step(2, 10, "EPSG:3857 koordinata toʻri shakllantirilmoqda")
    width, height, pixel_size, bbox = compute_grid_dimensions(
        aoi_geojson, resolution_m=settings.analysis_resolution_m
    )
    await emit_recon_event(run_id, 2, f"Toʻr oʻlchami: {width}x{height} piksel")

    if is_cancellation_requested(run_id):
        return

    # 3. Scene discovery
    log_step(3, 10, "Sunʼiy yoʻldosh kadrlari (scenes) qidirilmoqda")
    scenes = await gateway.discover_scenes(aoi_geojson, lookback_days=settings.lookback_days, run_id=run_id)
    scene_ids = [s["scene_id"] for s in scenes]
    await emit_recon_event(run_id, 3, f"{len(scenes)} ta sunʼiy yoʻldosh kadri aniqlandi", {"scene_count": len(scenes)})

    if is_cancellation_requested(run_id):
        return

    # 4. Fingerprint
    log_step(4, 10, "Barmoq izi (fingerprint) tekshirilmoqda")
    fp = compute_recon_fingerprint(aoi_geojson, scene_ids)

    # Mavjud tugallangan run bilan taqqoslash
    async with async_session_maker() as session:
        dup_query = await session.execute(
            select(RunModel).where(
                RunModel.fingerprint == fp,
                RunModel.status == JobStatus.COMPLETED,
                RunModel.id != run_id,
            )
        )
        existing_run = dup_query.scalars().first()
        if existing_run:
            logger.info(f"Yangi sun'iy yo'ldosh ma'lumoti yo'q. Avvalgi vazifa: #{existing_run.id}")
            await emit_recon_event(
                run_id, 4, "Yangi sunʼiy yoʻldosh maʼlumoti yoʻq", {"existing_run_id": existing_run.id}
            )
            # Joriy runni yakunlash
            curr_run = await session.get(RunModel, run_id)
            if curr_run:
                curr_run.status = JobStatus.COMPLETED
                curr_run.completed_at = now_ts()
                curr_run.fingerprint = fp
                await session.commit()
            return

        # Fingerprintni bazaga yangilash
        curr_run = await session.get(RunModel, run_id)
        if curr_run:
            curr_run.fingerprint = fp
            await session.commit()

    if is_cancellation_requested(run_id):
        return

    # 5. Download rasters
    log_step(5, 10, "Spektral va SAR qatlamlari yuklanmoqda")
    await emit_recon_event(run_id, 5, "Sentinel-2, Sentinel-1, Landsat va DEM massivlari olinmoqda")

    # Sentinel-2
    s2_acq = scenes[0]["acq_time"] if scenes else now_ts()
    s2_arrays = await gateway.download_raster("sentinel2", S2_BANDS, width, height, s2_acq, run_id)

    # Sentinel-1
    s1_acq = scenes[1]["acq_time"] if len(scenes) > 1 else now_ts()
    s1_arrays = await gateway.download_raster("sentinel1", S1_BANDS, width, height, s1_acq, run_id)

    # DEM
    dem_arrays = await gateway.download_raster("dem", ["DEM"], width, height, None, run_id)

    # Landsat (termal)
    landsat_arrays = await gateway.download_raster("landsat", ["ST_B10", "SR_B4", "SR_B5"], width, height, None, run_id)

    # SMAP (tuproq namligi)
    smap_arrays = await gateway.download_raster("smap", ["sm_surface", "sm_rootzone"], width, height, None, run_id)

    if is_cancellation_requested(run_id):
        return

    # 6. Weather
    log_step(6, 10, "Ob-havo va reanaliz maʼlumotlari olinmoqda")
    weather_series = await gateway.fetch_weather_series(
        past_days=settings.weather_past_days,
        forecast_days=settings.weather_forecast_days,
        run_id=run_id,
    )
    await emit_recon_event(run_id, 6, "ERA5-Land va GFS ob-havo maʼlumotlari yuklandi")

    if is_cancellation_requested(run_id):
        return

    # 7. Analysis
    log_step(7, 10, "Formula analizatorlari ishga tushirilmoqda")
    await emit_recon_event(run_id, 7, "Indekslar, SAR, relyef va yer qoplami hisoblanmoqda")

    # Indekslar
    indices_analyzer = get_analyzer("indices")
    indices_res = indices_analyzer.run(AnalyzerInput(arrays=s2_arrays, pixel_size_m=pixel_size))

    # SAR
    sar_analyzer = get_analyzer("sar")
    sar_res = sar_analyzer.run(AnalyzerInput(arrays=s1_arrays, pixel_size_m=pixel_size))

    # Relyef
    terrain_analyzer = get_analyzer("terrain")
    terrain_res = terrain_analyzer.run(AnalyzerInput(arrays=dem_arrays, pixel_size_m=pixel_size))

    # Termal (LST)
    thermal_analyzer = get_analyzer("thermal")
    thermal_res = thermal_analyzer.run(AnalyzerInput(arrays=landsat_arrays, pixel_size_m=pixel_size))

    # RGB tekstura
    rgb_analyzer = get_analyzer("rgb")
    rgb_res = rgb_analyzer.run(AnalyzerInput(arrays=s2_arrays, pixel_size_m=pixel_size))

    # Yer qoplami klassifikatsiyasi
    landcover_input_arrays = {
        **indices_res.layers,
        **sar_res.layers,
        **terrain_res.layers,
        **rgb_res.layers,
        "soil_moisture": smap_arrays.get("sm_surface"),
    }
    landcover_analyzer = get_analyzer("landcover")
    landcover_res = landcover_analyzer.run(
        AnalyzerInput(
            arrays=landcover_input_arrays,
            pixel_size_m=pixel_size,
            extra={"scl": s2_arrays.get("SCL"), "cloud_mask": s2_arrays.get("cs_cdf", 0) < settings.cloud_score_threshold},
        )
    )

    # Sifat nazorati va Landsat NDVI cross-check
    ls_ndvi = (landsat_arrays["SR_B5"] - landsat_arrays["SR_B4"]) / (landsat_arrays["SR_B5"] + landsat_arrays["SR_B4"] + 1e-6)
    cross_check_info = cross_check_ndvi(indices_res.layers["ndvi"], ls_ndvi, time_diff_days=2.0)

    # Ob-havo ta'siri qoidalari
    weather_impact_list = analyze_weather_impact(
        weather_records=weather_series,
        has_depressions=bool(np.any(terrain_res.layers["depressions"] > 0)),
    )

    if is_cancellation_requested(run_id):
        return

    # 8. Render PNGs and save .npz
    log_step(8, 10, "PNG qatlamlari vizualizatsiya qilinmoqda")
    await emit_recon_event(run_id, 8, "Shaffof PNG qatlamlari va .npz massivlari yaratilmoqda")

    all_layers: dict[str, np.ndarray] = {
        **indices_res.layers,
        **sar_res.layers,
        **terrain_res.layers,
        **thermal_res.layers,
        **rgb_res.layers,
        **landcover_res.layers,
    }

    # Barcha massivlarni bitta .npz ga saqlash
    npz_path = run_folder / "rasters.npz"
    np.savez_compressed(npz_path, **all_layers)

    # PNG fayllarini generatsiya qilish
    png_paths: dict[str, str] = {}
    for name, arr in all_layers.items():
        png_file = run_folder / f"{name}.png"
        array_to_rgba_png(arr, kind=name, output_path=png_file)
        png_paths[name] = str(png_file)

    if is_cancellation_requested(run_id):
        return

    # 9. Persist to DB
    log_step(9, 10, "Natijalar maʼlumotlar bazasiga yozilmoqda")
    await emit_recon_event(run_id, 9, "Baza yozuvlari saqlanmoqda")

    async with async_session_maker() as session:
        # Scenes saqlash
        for sc in scenes:
            session.add(
                SceneModel(
                    run_id=run_id,
                    scene_id=sc["scene_id"],
                    sensor=sc["sensor"],
                    acq_time=sc["acq_time"],
                    cloud_pct=sc["cloud_pct"],
                )
            )

        # Layers va Stats saqlash
        all_stats = {
            **indices_res.stats,
            **sar_res.stats,
            **terrain_res.stats,
            **thermal_res.stats,
            **rgb_res.stats,
            **landcover_res.stats,
        }

        layer_kind_map = {
            "ndvi": (LayerKind.NDVI, SensorKind.SENTINEL2),
            "ndwi": (LayerKind.NDWI, SensorKind.SENTINEL2),
            "mndwi": (LayerKind.MNDWI, SensorKind.SENTINEL2),
            "evi": (LayerKind.EVI, SensorKind.SENTINEL2),
            "ndre": (LayerKind.NDRE, SensorKind.SENTINEL2),
            "ndmi": (LayerKind.NDMI, SensorKind.SENTINEL2),
            "nbr": (LayerKind.NBR, SensorKind.SENTINEL2),
            "ndbi": (LayerKind.NDBI, SensorKind.SENTINEL2),
            "bsi": (LayerKind.BSI, SensorKind.SENTINEL2),
            "vv": (LayerKind.SAR_VV, SensorKind.SENTINEL1),
            "vh": (LayerKind.SAR_VH, SensorKind.SENTINEL1),
            "rvi": (LayerKind.SAR_RVI, SensorKind.SENTINEL1),
            "water_mask": (LayerKind.SAR_WATER, SensorKind.SENTINEL1),
            "elevation": (LayerKind.ELEVATION, SensorKind.DEM),
            "slope": (LayerKind.SLOPE, SensorKind.DEM),
            "aspect": (LayerKind.ASPECT, SensorKind.DEM),
            "hillshade": (LayerKind.HILLSHADE, SensorKind.DEM),
            "lst": (LayerKind.LST, SensorKind.LANDSAT),
            "landcover": (LayerKind.LANDCOVER, SensorKind.SENTINEL2),
            "confidence": (LayerKind.CONFIDENCE, SensorKind.SENTINEL2),
        }

        for l_name, l_path in png_paths.items():
            k_enum, s_enum = layer_kind_map.get(l_name, (LayerKind.UNKNOWN, SensorKind.UNKNOWN))
            st = all_stats.get(l_name, {})
            l_model = LayerModel(
                run_id=run_id,
                kind=k_enum,
                sensor=s_enum,
                acq_time=s2_acq,
                file_path=l_path,
                min_val=st.get("min"),
                max_val=st.get("max"),
                valid_pct=100.0,
                quality_flag=QualityFlag.GOOD,
            )
            session.add(l_model)
            await session.flush()

            session.add(
                LayerStatsModel(
                    layer_id=l_model.id,
                    mean_val=st.get("mean"),
                    std_val=st.get("std"),
                    median_val=st.get("median"),
                    p10=st.get("p10"),
                    p90=st.get("p90"),
                )
            )

        # Yer qoplami sinflari maydonlari (Class areas)
        lc_arr = landcover_res.layers["landcover"].astype(int)
        total_px = float(lc_arr.size)
        px_area_m2 = (pixel_size) ** 2
        for c_code, c_label in CLASS_LABELS_UZ.items():
            c_cnt = float(np.sum(lc_arr == c_code))
            pct = (c_cnt / total_px) * 100.0 if total_px > 0 else 0.0
            if pct > 0.0 or c_code == 0:
                session.add(
                    ClassAreaModel(
                        run_id=run_id,
                        acq_time=s2_acq,
                        class_code=c_code,
                        area_m2=c_cnt * px_area_m2,
                        pct=round(pct, 2),
                    )
                )

        # Weather saqlash
        for w in weather_series:
            session.add(
                WeatherModel(
                    run_id=run_id,
                    source=w["source"],
                    ts=w["ts"],
                    temp_c=w.get("temp_c"),
                    dewpoint_c=w.get("dewpoint_c"),
                    precip_mm=w.get("precip_mm"),
                    wind_speed_ms=w.get("wind_speed_ms"),
                    wind_deg=w.get("wind_deg"),
                    soil_moisture=w.get("soil_moisture"),
                    is_forecast=w.get("is_forecast", 0),
                )
            )

        # Runni yakunlash
        run_obj = await session.get(RunModel, run_id)
        if run_obj:
            run_obj.status = JobStatus.COMPLETED
            run_obj.completed_at = now_ts()

        await session.commit()

    if is_cancellation_requested(run_id):
        return

    # 10. AI Report
    log_step(10, 10, "AI tahliliy hisoboti yaratilmoqda")
    await emit_recon_event(run_id, 10, "Sunʼiy intellekt orqali yakuniy xulosa tayyorlanmoqda")

    summary_for_ai = {
        "run_id": run_id,
        "area_km2": area_km2,
        "created_at": now_ts(),
        "scenes": scenes,
        "classes": [{"code": c, "label": CLASS_LABELS_UZ.get(c, "")} for c in np.unique(lc_arr)],
        "layer_stats": all_stats,
        "cross_check": cross_check_info,
        "weather_impact": weather_impact_list,
    }

    try:
        report_md = await generate_recon_report(summary_for_ai, run_id=run_id)
        async with async_session_maker() as session:
            session.add(
                ReportModel(
                    run_id=run_id,
                    fingerprint=fp,
                    content_md=report_md,
                    created_at=now_ts(),
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"AI hisoboti tuzishda xatolik (quvur baribir yakunlandi): {e}")

    await emit_recon_event(run_id, 10, "Rekognossirovka toʻliq yakunlandi", {"status": "completed"})
    logger.info(f"Vazifa #{run_id} muvaffaqiyatli yakunlandi!")
