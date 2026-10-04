"""Rekognossirovka API marshrutlari (/api/v1/recon).

Javoblardagi har bir vaqt `*_ts` (UTC epoch) va `*_local` (DD.MM.YYYY HH:MM, Toshkent) ko'rinishida.
Xatolar {code, message_uz} shaklida.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.report_generator import generate_report_for_run
from backend.app.core import constants as C
from backend.app.core.errors import (
    ConflictError,
    GEENotConfiguredError,
    NotFoundError,
    ValidationAppError,
)
from backend.app.core.run_settings import RunSettings
from backend.app.core.time import fmt_local, ts_fields
from backend.app.db.enums import (
    SENSOR_NAMES_UZ,
    WEATHER_SOURCE_KEYS,
    JobStatus,
    QualityFlag,
    ReportStatus,
    SensorKind,
    WeatherSource,
)
from backend.app.db.models import (
    ClassAreaModel,
    LayerModel,
    ReportModel,
    RunModel,
    SceneModel,
    WeatherModel,
)
from backend.app.db.session import get_db, load_run_settings
from backend.app.gee import datasets as D
from backend.app.pipeline import storage as st
from backend.app.pipeline.deps import get_data_source, get_gateway
from backend.app.pipeline.grid import Grid, normalize_aoi, validate_aoi
from backend.app.pipeline.jobs import TERMINAL_EVENTS, job_manager
from backend.app.pipeline.recon import create_run_row, make_runner
from backend.app.pipeline.render import LAYER_SPECS, legend_for, render_composite_png

router = APIRouter(prefix="/recon", tags=["Rekognossirovka"])

STATUS_NAMES = {JobStatus.RUNNING: "running", JobStatus.COMPLETED: "completed", JobStatus.FAILED: "failed"}
COMPOSITE_BANDS = set(D.S2_REFLECTANCE_BANDS)
SSE_KEEPALIVE_S = 15.0


class StartReconSchema(BaseModel):
    aoi: dict[str, Any]


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
async def _get_run(db: AsyncSession, run_id: int) -> RunModel:
    run = await db.get(RunModel, run_id)
    if run is None:
        raise NotFoundError(f"Rekognossirovka #{run_id} topilmadi.")
    return run


async def _get_completed_run(db: AsyncSession, run_id: int) -> RunModel:
    run = await _get_run(db, run_id)
    if run.status != JobStatus.COMPLETED:
        raise ConflictError("Rekognossirovka hali yakunlanmagan.", code="RUN_NOT_READY")
    return run


def _summary(run_id: int) -> dict[str, Any]:
    p = st.summary_path(run_id)
    if not p.exists():
        raise NotFoundError("Natijalar fayli topilmadi.")
    return st.load_json(p)


def _derived_key(layer: LayerModel) -> str:
    if layer.sensor == SensorKind.DEM:
        return "dem"
    if layer.sensor == SensorKind.SMAP:
        return "smap"
    return f"{SensorKind(layer.sensor).name.lower()}_{layer.acq_time}"


def _layer_out(run_id: int, layer: LayerModel) -> dict[str, Any]:
    spec = LAYER_SPECS.get(layer.name)
    stats = layer.stats
    flag = QualityFlag(layer.quality_flag)
    return {
        "id": layer.id,
        "name": layer.name,
        "kind": layer.kind,
        "label_uz": spec.label_uz if spec else layer.name,
        "group_uz": spec.group_uz if spec else "",
        "sensor": SENSOR_NAMES_UZ[SensorKind(layer.sensor)],
        "sensor_code": layer.sensor,
        "dataset": layer.dataset,
        **ts_fields("acq_time", layer.acq_time),
        **(ts_fields("prev_time", layer.prev_time) if layer.prev_time else {}),
        "scene_ids": json.loads(layer.scene_ids),
        "image_url": f"/api/v1/recon/{run_id}/layers/{layer.id}.png",
        "unit": layer.unit,
        "legend": legend_for(layer.name, layer.min_val, layer.max_val) if spec else None,
        "valid_pct": layer.valid_pct,
        "cloud_masked_pct": layer.cloud_masked_pct,
        "quality_flag": flag.name,
        "low_confidence": flag in (QualityFlag.LOW_CONFIDENCE, QualityFlag.NO_DATA),
        "stats": None if stats is None else {
            "count": stats.count, "mean": stats.mean_val, "std": stats.std_val, "median": stats.median_val,
            "p10": stats.p10, "p90": stats.p90, "min": layer.min_val if not spec or spec.mode != "rgb" else None,
        },
    }


# ---------------------------------------------------------------------------
# Vazifani boshqarish
# ---------------------------------------------------------------------------
@router.post("")
async def start_reconnaissance(payload: StartReconSchema, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Yangi rekognossirovkani fonda boshlaydi (faol vazifa bo'lsa 409)."""
    if job_manager.active_run_id() is not None:
        raise ConflictError()
    run_settings = await load_run_settings(db)
    aoi = normalize_aoi(payload.aoi)
    area = validate_aoi(aoi, run_settings.max_aoi_km2)
    source = get_data_source()
    if not source.is_configured():
        raise GEENotConfiguredError()
    job = await job_manager.start(
        lambda: create_run_row(aoi, area, run_settings),
        make_runner(aoi, area, run_settings, source, get_gateway()),
    )
    return {
        "run_id": job.run_id,
        "area_km2": round(area, 4),
        "message_uz": "Rekognossirovka boshlandi",
        "events_url": f"/api/v1/recon/{job.run_id}/events",
    }


@router.get("/active")
async def get_active_recon(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Faol vazifa (sahifa qayta yuklanganda holatni tiklash uchun)."""
    rid = job_manager.active_run_id()
    if rid is None:
        return {"active": False, "run": None}
    run = await db.get(RunModel, rid)
    job = job_manager.get_job(rid)
    return {
        "active": True,
        "run": {
            "id": rid,
            "aoi": json.loads(run.aoi_geojson) if run else None,
            "area_km2": run.area_km2 if run else None,
            **ts_fields("created_at", run.created_at if run else None),
            "stage": job.stage if job else 0,
            "progress": job.progress if job else 0.0,
            "events_url": f"/api/v1/recon/{rid}/events",
        },
    }


@router.get("/{run_id}/events")
async def stream_recon_events(run_id: int, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """SSE: vazifa hodisalari (tarixdan boshlab), yakuniy hodisada oqim yopiladi."""
    job = job_manager.get_job(run_id)
    if job is None:
        run = await _get_run(db, run_id)
        ev_type = "done" if run.status == JobStatus.COMPLETED else "error"
        msg = "Rekognossirovka yakunlangan" if ev_type == "done" else (run.error_message or "Xatolik")
        final = {"seq": 0, "type": ev_type, "run_id": run_id, "stage": 10, "total_stages": 10,
                 "progress": 1.0, "message_uz": msg, "data": {"code": run.error_code}, **ts_fields("ts", run.completed_at)}
        final["ts"] = final.pop("ts_ts")

        async def once() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"

        return StreamingResponse(once(), media_type="text/event-stream")

    queue = job_manager.subscribe(job)

    async def gen() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev["type"] in TERMINAL_EVENTS:
                    break
        finally:
            job_manager.unsubscribe(job, queue)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/{run_id}/cancel")
async def cancel_reconnaissance(run_id: int) -> dict[str, Any]:
    """Vazifani to'xtatadi va barcha resurslarni (fayllar, DB qatorlari, xotira) tozalaydi."""
    ok = await job_manager.cancel(run_id)
    if not ok:
        raise ConflictError("Bu rekognossirovka hozir bajarilmayapti.", code="RUN_NOT_ACTIVE")
    return {"run_id": run_id, "cancelled": True, "message_uz": "Vazifa toʻxtatildi va tozalandi"}


# ---------------------------------------------------------------------------
# Natijalar
# ---------------------------------------------------------------------------
@router.get("/{run_id}")
async def get_recon_summary(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Run xulosasi: holat, hudud, to'r chegaralari, kuzatuv sanalari, hisobot holati."""
    run = await _get_run(db, run_id)
    grid = Grid.from_json(run.grid_json) if run.grid_json else None
    dates: list[dict[str, Any]] = []
    if run.status == JobStatus.COMPLETED:
        rows = (await db.execute(
            select(LayerModel.acq_time, LayerModel.sensor).where(
                LayerModel.run_id == run_id,
                LayerModel.sensor.in_([SensorKind.SENTINEL2, SensorKind.SENTINEL1, SensorKind.LANDSAT]),
            ).distinct()
        )).all()
        seen: dict[int, set[str]] = {}
        for t, sensor in rows:
            seen.setdefault(t, set()).add(SENSOR_NAMES_UZ[SensorKind(sensor)])
        dates = [{**ts_fields("time", t), "sensors": sorted(s)} for t, s in sorted(seen.items())]
    numbers: dict[str, Any] = {}
    if run.status == JobStatus.COMPLETED and st.summary_path(run_id).exists():
        sm = st.load_json(st.summary_path(run_id))
        numbers = {k: sm.get(k) for k in ("terrain", "soil_moisture", "quality_flags")}
    report = None
    if run.fingerprint:
        report = (await db.execute(select(ReportModel).where(ReportModel.fingerprint == run.fingerprint))).scalars().first()
    return {
        "id": run.id,
        "status": STATUS_NAMES.get(JobStatus(run.status), "unknown"),
        "area_km2": run.area_km2,
        "aoi": json.loads(run.aoi_geojson),
        "bounds_latlon": grid.bounds_latlon() if grid else None,
        "resolution_m": grid.res_m if grid else None,
        "grid": {"width": grid.width, "height": grid.height} if grid else None,
        **ts_fields("created_at", run.created_at),
        **ts_fields("completed_at", run.completed_at),
        "fingerprint": run.fingerprint.hex() if run.fingerprint else None,
        "failover": bool(run.failover),
        "error": {"code": run.error_code, "message_uz": run.error_message} if run.error_code else None,
        "observation_dates": dates,
        "settings": json.loads(run.settings_json),
        "report_status": None if report is None else ("ok" if report.status == ReportStatus.OK else "failed"),
        **numbers,
    }


@router.get("/{run_id}/layers")
async def get_recon_layers(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Qatlamlar: har biri vaqt, manba, sifat, afsona va statistika bilan."""
    run = await _get_completed_run(db, run_id)
    from sqlalchemy.orm import selectinload

    layers = (await db.execute(
        select(LayerModel).where(LayerModel.run_id == run_id).options(selectinload(LayerModel.stats))
        .order_by(LayerModel.acq_time, LayerModel.id)
    )).scalars().all()
    grid = Grid.from_json(run.grid_json) if run.grid_json else None
    return {
        "run_id": run_id,
        "bounds_latlon": grid.bounds_latlon() if grid else None,
        "layers": [_layer_out(run_id, lyr) for lyr in layers],
    }


@router.get("/{run_id}/layers/{layer_id}.png")
async def get_layer_png(run_id: int, layer_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """Qatlamning shaffof PNG tasviri."""
    layer = await db.get(LayerModel, layer_id)
    if layer is None or layer.run_id != run_id:
        raise NotFoundError("Qatlam topilmadi.")
    p = Path(layer.file_path)
    if not p.exists():
        raise NotFoundError("Qatlam tasviri diskda yoʻq.")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{run_id}/composite.png")
async def get_custom_composite(
    run_id: int,
    date: int = Query(..., description="Sentinel-2 kuzatuv vaqti (UTC epoch, layers ro'yxatidagi acq_time_ts)"),
    r: str = Query("B4"),
    g: str = Query("B3"),
    b: str = Query("B2"),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Sentinel-2 bandlaridan ixtiyoriy R/G/B kompozit (2–98 persentil cho'zish)."""
    await _get_completed_run(db, run_id)
    for band in (r, g, b):
        if band not in COMPOSITE_BANDS:
            raise ValidationAppError(
                f"Notoʻgʻri band: {band}. Ruxsat etilgan: {', '.join(D.S2_REFLECTANCE_BANDS)}", code="INVALID_BAND"
            )
    raw = st.raw_path(run_id, f"{SensorKind.SENTINEL2.name.lower()}_{date}")
    if not raw.exists():
        raise NotFoundError("Bu sana uchun Sentinel-2 kuzatuvi topilmadi.")
    out = st.composite_dir(run_id) / f"{date}_{r}_{g}_{b}.png"
    if not out.exists():
        arrays = await asyncio.to_thread(st.load_arrays, raw, [r, g, b])
        await asyncio.to_thread(render_composite_png, arrays[r], arrays[g], arrays[b], out, None)
    return FileResponse(out, media_type="image/png")


@router.get("/{run_id}/pixel")
async def query_pixel_point(
    run_id: int,
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-85, le=85),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Nuqtadagi barcha qiymatlar: har biri o'z vaqti, sensori, dataset va kadr ID'lari bilan."""
    run = await _get_completed_run(db, run_id)
    grid = Grid.from_json(run.grid_json or "{}")
    rc = grid.pixel_of(lon, lat)
    if rc is None:
        raise NotFoundError("Nuqta tahlil qilingan hududdan tashqarida.")
    row, col = rc
    layers = (await db.execute(select(LayerModel).where(LayerModel.run_id == run_id))).scalars().all()
    by_key: dict[str, list[LayerModel]] = {}
    for lyr in layers:
        by_key.setdefault(_derived_key(lyr), []).append(lyr)

    groups: list[dict[str, Any]] = []
    for key, lyrs in by_key.items():
        dp = st.derived_path(run_id, key)
        vals = await asyncio.to_thread(st.read_pixel, dp, row, col) if dp.exists() else {}
        raw_vals: dict[str, float | None] = {}
        rp = st.raw_path(run_id, key)
        if lyrs[0].sensor in (SensorKind.SENTINEL2, SensorKind.LANDSAT, SensorKind.SENTINEL1) and rp.exists():
            raw_vals = await asyncio.to_thread(st.read_pixel, rp, row, col)
        first = lyrs[0]
        items = []
        for lyr in sorted(lyrs, key=lambda x: x.name):
            if lyr.name not in vals:
                continue
            v = vals[lyr.name]
            spec = LAYER_SPECS[lyr.name]
            item = {"name": lyr.name, "label_uz": spec.label_uz, "unit": spec.unit, "value": v}
            if lyr.name == "landcover" and v is not None:
                item["class_label_uz"] = C.CLASS_LABELS_UZ.get(int(v), "Nomaʼlum")
            if lyr.prev_time:
                item.update(ts_fields("prev_time", lyr.prev_time))
            items.append(item)
        bands = [{"name": k, "value": v} for k, v in sorted(raw_vals.items())]
        groups.append({
            "sensor": SENSOR_NAMES_UZ[SensorKind(first.sensor)],
            "dataset": first.dataset,
            **ts_fields("acq_time", first.acq_time),
            "scene_ids": json.loads(first.scene_ids),
            "values": items,
            "bands": bands,
        })
    groups.sort(key=lambda g: (g["sensor"], g["acq_time_ts"] or 0))
    return {"lon": lon, "lat": lat, "row": row, "col": col, "groups": groups}


@router.get("/{run_id}/classes")
async def get_class_distribution(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Yer qoplami sinflari maydoni (har bir Sentinel-2 sanasi uchun)."""
    await _get_completed_run(db, run_id)
    rows = (await db.execute(
        select(ClassAreaModel).where(ClassAreaModel.run_id == run_id).order_by(ClassAreaModel.acq_time, ClassAreaModel.class_code)
    )).scalars().all()
    summary = _summary(run_id)
    meta = {ca["acq_time_ts"]: ca for ca in summary.get("class_areas", [])}
    dates: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        dates.setdefault(r.acq_time, []).append({
            "class_code": r.class_code,
            "label_uz": C.CLASS_LABELS_UZ.get(r.class_code, "Nomaʼlum"),
            "color": C.CLASS_COLORS.get(r.class_code),
            "pixel_count": r.pixel_count,
            "area_ha": round(r.area_m2 / 10000.0, 3),
            "pct": r.pct,
            "mean_confidence": r.mean_confidence,
        })
    return {
        "run_id": run_id,
        "source": f"{D.S2_COLLECTION} (+ {D.S1_COLLECTION}, {D.DEM_COLLECTION}, {D.SMAP_COLLECTION})",
        "dates": [
            {
                **ts_fields("acq_time", t),
                "classified_pct": meta.get(t, {}).get("classified_pct"),
                "low_confidence": meta.get(t, {}).get("low_confidence"),
                "sar_obs_time_local": meta.get(t, {}).get("sar_obs_time_local"),
                "classes": cls,
            }
            for t, cls in sorted(dates.items())
        ],
    }


@router.get("/{run_id}/changes")
async def get_changes_summary(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Ketma-ket haqiqiy kuzatuvlar orasidagi o'zgarishlar (ΔNDVI, ΔNDWI, ΔNDMI, ΔVV, Δ namlik, sinf o'tishlari)."""
    await _get_completed_run(db, run_id)
    s = _summary(run_id)
    return {"run_id": run_id, **s.get("changes", {}), "cross_check": s.get("cross_check", [])}


@router.get("/{run_id}/weather")
async def get_weather_data(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """O'tmish va prognoz ob-havo (manba va vaqt bilan), kunlik yog'in va ta'sir xulosalari."""
    await _get_completed_run(db, run_id)
    rows = (await db.execute(select(WeatherModel).where(WeatherModel.run_id == run_id).order_by(WeatherModel.ts))).scalars().all()

    def rec(r: WeatherModel) -> dict[str, Any]:
        return {
            "source": WEATHER_SOURCE_KEYS.get(WeatherSource(r.source), "unknown"),
            **ts_fields("time", r.ts),
            "period_s": r.period_s,
            **(ts_fields("issued", r.issued_ts) if r.issued_ts else {}),
            "temp_c": r.temp_c, "temp_min_c": r.temp_min_c, "temp_max_c": r.temp_max_c,
            "dewpoint_c": r.dewpoint_c, "rh_pct": r.rh_pct,
            "precip_mm": r.precip_mm, "precip_min_mm": r.precip_min_mm, "precip_max_mm": r.precip_max_mm,
            "wind_speed_ms": r.wind_speed_ms, "wind_min_ms": r.wind_min_ms, "wind_max_ms": r.wind_max_ms,
            "wind_deg": r.wind_deg, "cloud_pct": r.cloud_pct, "soil_moisture": r.soil_moisture,
        }

    past = [rec(r) for r in rows if not r.is_forecast and r.source != WeatherSource.CHIRPS]
    fc = [rec(r) for r in rows if r.is_forecast]
    chirps = [rec(r) for r in rows if r.source == WeatherSource.CHIRPS]
    s = _summary(run_id)
    return {
        "run_id": run_id,
        "past": past,
        "forecast": fc,
        "chirps_daily": chirps,
        "summary": s.get("weather", {}),
        "impact": s.get("weather_impact", []),
        "datasets": {"era5": D.ERA5_LAND_HOURLY, "gfs_analysis": D.GFS_0P25, "gfs_forecast": D.GFS_0P25, "chirps": D.CHIRPS_DAILY},
    }


@router.get("/{run_id}/satellites")
async def get_satellite_provenance(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Har bir sun'iy yo'ldosh nima bergani va qachon: kadrlar, kuzatuvlar, bandlar, sifat."""
    await _get_completed_run(db, run_id)
    scenes = (await db.execute(select(SceneModel).where(SceneModel.run_id == run_id).order_by(SceneModel.acq_time))).scalars().all()
    s = _summary(run_id)
    obs_q = {o["key"]: o for o in s.get("observations", [])}
    sensors: list[dict[str, Any]] = []
    for src in s.get("sources", []):
        sensors.append(src)
    scene_rows = [
        {
            "scene_id": sc.scene_id,
            "sensor": SENSOR_NAMES_UZ[SensorKind(sc.sensor)],
            "platform": sc.platform,
            "dataset": sc.dataset,
            **ts_fields("acq_time", sc.acq_time),
            **ts_fields("obs_time", sc.obs_time),
            "cloud_pct": sc.cloud_pct,
            "orbit_pass": sc.orbit_pass,
            "observation_quality": obs_q.get(f"{SensorKind(sc.sensor).name.lower()}_{sc.obs_time}"),
        }
        for sc in scenes
    ]
    return {"run_id": run_id, "sources": sensors, "scenes": scene_rows, "observations": s.get("observations", [])}


# ---------------------------------------------------------------------------
# AI hisobot
# ---------------------------------------------------------------------------
def _report_out(run_id: int, rep: ReportModel) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "report_run_id": rep.run_id,
        "status": "ok" if rep.status == ReportStatus.OK else "failed",
        "provider": rep.provider,
        "model": rep.model,
        "attempts": rep.attempts,
        **ts_fields("created_at", rep.created_at),
        "content_md": rep.content_md,
        "error": rep.error,
    }


@router.get("/{run_id}/report")
async def get_ai_report(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """AI hisobotini o'qish (barmoq izi bo'yicha)."""
    run = await _get_completed_run(db, run_id)
    rep = (await db.execute(select(ReportModel).where(ReportModel.fingerprint == run.fingerprint))).scalars().first()
    if rep is None:
        raise NotFoundError("Hisobot hali tayyorlanmagan.")
    return _report_out(run_id, rep)


@router.post("/{run_id}/report")
async def generate_ai_report_endpoint(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """AI hisobotini yaratish. Barmoq izi uchun muvaffaqiyatli hisobot bo'lsa — 409."""
    if job_manager.active_run_id() is not None:
        raise ConflictError()
    run = await _get_completed_run(db, run_id)
    run_settings: RunSettings = await load_run_settings(db)
    rep = await generate_report_for_run(db, run, _summary(run_id), run_settings)
    return _report_out(run_id, rep)


__all__ = ["router", "fmt_local"]
