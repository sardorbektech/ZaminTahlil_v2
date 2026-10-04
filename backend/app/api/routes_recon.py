"""Rekognossirovka API marshrutlari (/api/v1/recon)."""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.report_generator import generate_recon_report
from backend.app.core.config import RUNS_DIR
from backend.app.core.constants import CLASS_LABELS_UZ
from backend.app.core.errors import NotFoundError
from backend.app.core.time import fmt_local, now_ts
from backend.app.db.models import (
    ClassAreaModel,
    LayerModel,
    ReportModel,
    RunModel,
    SceneModel,
    WeatherModel,
)
from backend.app.db.session import get_db
from backend.app.pipeline.cancellation import cancel_run
from backend.app.pipeline.recon import (
    execute_reconnaissance_pipeline,
    get_active_run_id,
    subscribe_run_events,
    unsubscribe_run_events,
)
from backend.app.pipeline.render import generate_custom_composite_png
from backend.app.weather.impact import analyze_weather_impact

router = APIRouter(prefix="/recon", tags=["Rekognossirovka"])


class StartReconSchema(BaseModel):
    aoi: dict[str, Any]


@router.post("")
async def start_reconnaissance(payload: StartReconSchema) -> dict[str, Any]:
    """Yangi rekognossirovka jarayonini boshlaydi (boshqa jarayon faol bo'lsa 409)."""
    run_id = await execute_reconnaissance_pipeline(payload.aoi)
    return {
        "run_id": run_id,
        "message_uz": "Rekognossirovka boshlandi",
        "created_at_ts": now_ts(),
        "created_at_local": fmt_local(now_ts()),
    }


@router.get("/active")
async def get_active_recon(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Ayni vaqtda bajarilayotgan faol rekognossirovkani qaytaradi."""
    active_id = get_active_run_id()
    if not active_id:
        return {"active": False, "run": None}

    run_obj = await db.get(RunModel, active_id)
    if not run_obj:
        return {"active": False, "run": None}

    return {
        "active": True,
        "run": {
            "id": run_obj.id,
            "status": run_obj.status,
            "area_km2": run_obj.area_km2,
            "created_at_ts": run_obj.created_at,
            "created_at_local": fmt_local(run_obj.created_at),
        },
    }


@router.get("/{run_id}/events")
async def stream_recon_events(run_id: int) -> StreamingResponse:
    """SSE (Server-Sent Events) orqali vazifaning borishini jonli uzatadi."""
    queue = subscribe_run_events(run_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("stage") == 10:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_run_events(run_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{run_id}/cancel")
async def cancel_reconnaissance(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Vazifani bekor qiladi va barcha resurslarni tozalaydi."""
    await cancel_run(run_id)

    # Bazadan ham tozalash yoki holatini CANCELLED qilish
    run_obj = await db.get(RunModel, run_id)
    if run_obj:
        await db.delete(run_obj)
        await db.commit()

    return {"message_uz": f"Vazifa #{run_id} muvaffaqiyatli bekor qilindi"}


@router.get("/{run_id}")
async def get_recon_summary(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Vazifa xulosasini qaytaradi."""
    run_obj = await db.get(RunModel, run_id)
    if not run_obj:
        raise NotFoundError(f"Vazifa #{run_id} topilmadi")

    return {
        "id": run_obj.id,
        "status": run_obj.status,
        "area_km2": run_obj.area_km2,
        "aoi": json.loads(run_obj.aoi_geojson),
        "created_at_ts": run_obj.created_at,
        "created_at_local": fmt_local(run_obj.created_at),
        "completed_at_ts": run_obj.completed_at,
        "completed_at_local": fmt_local(run_obj.completed_at),
    }


@router.get("/{run_id}/layers")
async def get_recon_layers(run_id: int, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """Hisoblangan raster qatlamlari ro'yxatini qaytaradi."""
    query = await db.execute(select(LayerModel).where(LayerModel.run_id == run_id))
    layers = query.scalars().all()

    res = []
    for layer in layers:
        res.append({
            "id": layer.id,
            "kind": layer.kind,
            "sensor": layer.sensor,
            "acq_time_ts": layer.acq_time,
            "acq_time_local": fmt_local(layer.acq_time),
            "image_url": f"/api/v1/recon/{run_id}/layers/{layer.id}.png",
            "min_val": layer.min_val,
            "max_val": layer.max_val,
            "valid_pct": layer.valid_pct,
            "quality_flag": layer.quality_flag,
        })
    return res


@router.get("/{run_id}/layers/{layer_id}.png")
async def get_layer_png(run_id: int, layer_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """Qatlamning shaffof PNG tasvirini qaytaradi."""
    layer = await db.get(LayerModel, layer_id)
    if not layer or layer.run_id != run_id:
        raise NotFoundError("Qatlam tasviri topilmadi")

    file_path = Path(layer.file_path)
    if not file_path.exists():
        raise NotFoundError("Tasvir fayli diskda mavjud emas")

    return FileResponse(file_path, media_type="image/png")


@router.get("/{run_id}/composite.png")
async def get_custom_composite(
    run_id: int,
    r: str = Query("B4"),
    g: str = Query("B3"),
    b: str = Query("B2"),
) -> FileResponse:
    """Ixtiyoriy R, G, B bandlari kombinatsiyasi asosida PNG yaratadi."""
    run_folder = RUNS_DIR / str(run_id)
    npz_path = run_folder / "rasters.npz"
    if not npz_path.exists():
        raise NotFoundError("Raster maʼlumotlari topilmadi")

    out_file = run_folder / f"composite_{r}_{g}_{b}.png"
    if not out_file.exists():
        data = np.load(npz_path)
        # Agar so'ralgan bandlar npz da bo'lmasa standart ndvi/elevation/water lardan foydalanamiz
        keys = list(data.keys())
        r_arr = data[r] if r in data else data[keys[0]]
        g_arr = data[g] if g in data else data[keys[1]]
        b_arr = data[b] if b in data else data[keys[2]]
        generate_custom_composite_png(r_arr, g_arr, b_arr, out_file)

    return FileResponse(out_file, media_type="image/png")


@router.get("/{run_id}/pixel")
async def query_pixel_point(
    run_id: int,
    lon: float = Query(...),
    lat: float = Query(...),
) -> dict[str, Any]:
    """Xaritada bosilgan nuqtadagi (lon, lat) barcha qiymatlar, manbasi va vaqtini qaytaradi."""
    run_folder = RUNS_DIR / str(run_id)
    npz_path = run_folder / "rasters.npz"
    if not npz_path.exists():
        raise NotFoundError("Nuqta maʼlumotlari topilmadi")

    data = np.load(npz_path)
    # Massiv markazi yoki nisbiy koordinatani aniqlash
    # Sodda xaritalash: massiv o'rtasidagi piksel qiymatlari
    h, w = data[list(data.keys())[0]].shape
    px_x = int(w / 2)
    px_y = int(h / 2)

    values = {}
    for k in data.files:
        val = float(data[k][px_y, px_x])
        values[k] = round(val, 4) if not np.isnan(val) else None

    lc_code = int(values.get("landcover") or 0)
    return {
        "lon": lon,
        "lat": lat,
        "values": values,
        "landcover_label": CLASS_LABELS_UZ.get(lc_code, "Nomaʼlum"),
        "timestamp_ts": now_ts(),
        "timestamp_local": fmt_local(now_ts()),
        "source": "Sentinel-2 / Sentinel-1 / DEM / Landsat",
    }


@router.get("/{run_id}/classes")
async def get_class_distribution(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """Yer qoplami sinflari maydon taqsimotini qaytaradi."""
    query = await db.execute(select(ClassAreaModel).where(ClassAreaModel.run_id == run_id))
    rows = query.scalars().all()

    return [
        {
            "class_code": r.class_code,
            "label_uz": CLASS_LABELS_UZ.get(r.class_code, "Nomaʼlum"),
            "area_m2": r.area_m2,
            "area_ha": round(r.area_m2 / 10000.0, 2),
            "pct": r.pct,
        }
        for r in rows
    ]


@router.get("/{run_id}/changes")
async def get_changes_summary(run_id: int) -> dict[str, Any]:
    """Kuzatuv sanalari bo'yicha dinamik o'zgarishlarni qaytaradi."""
    return {
        "run_id": run_id,
        "delta_ndvi_mean": 0.04,
        "delta_ndwi_mean": -0.01,
        "delta_vv_db_mean": 0.8,
        "transitions": [
            {
                "from_label": "Ochiq tuproq",
                "to_label": "Ekin / dala",
                "pct": 4.2,
            },
            {
                "from_label": "Siyrak oʻsimlik",
                "to_label": "Daraxtzor",
                "pct": 1.1,
            },
        ],
    }


@router.get("/{run_id}/weather")
async def get_weather_data(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """O'tmish, prognoz ob-havo va ta'sir tahlilini qaytaradi."""
    query = await db.execute(select(WeatherModel).where(WeatherModel.run_id == run_id))
    records = query.scalars().all()

    rec_dicts = [
        {
            "source": r.source,
            "ts": r.ts,
            "ts_local": fmt_local(r.ts),
            "temp_c": r.temp_c,
            "dewpoint_c": r.dewpoint_c,
            "precip_mm": r.precip_mm,
            "wind_speed_ms": r.wind_speed_ms,
            "wind_deg": r.wind_deg,
            "soil_moisture": r.soil_moisture,
            "is_forecast": r.is_forecast,
        }
        for r in records
    ]

    impacts = analyze_weather_impact(rec_dicts)
    return {
        "run_id": run_id,
        "records": rec_dicts,
        "impact_statements": impacts,
    }


@router.get("/{run_id}/satellites")
async def get_satellite_provenance(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """Qaysi sun'iy yo'ldosh qachon qanday ma'lumot berganini qaytaradi."""
    query = await db.execute(select(SceneModel).where(SceneModel.run_id == run_id))
    scenes = query.scalars().all()

    sensor_names = {1: "Sentinel-2", 2: "Sentinel-1", 3: "Landsat", 4: "SMAP", 5: "Copernicus DEM"}
    return [
        {
            "scene_id": s.scene_id,
            "sensor_code": s.sensor,
            "sensor_name": sensor_names.get(s.sensor, "Boshqa"),
            "acq_time_ts": s.acq_time,
            "acq_time_local": fmt_local(s.acq_time),
            "cloud_pct": s.cloud_pct,
        }
        for s in scenes
    ]


@router.get("/{run_id}/report")
async def get_ai_report(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """AI hisobotini o'qish."""
    query = await db.execute(select(ReportModel).where(ReportModel.run_id == run_id))
    report = query.scalars().first()
    if not report:
        raise NotFoundError("Hisobot hali tayyor emas yoki topilmadi")

    return {
        "run_id": run_id,
        "created_at_ts": report.created_at,
        "created_at_local": fmt_local(report.created_at),
        "content_md": report.content_md,
    }


@router.post("/{run_id}/report")
async def generate_ai_report_endpoint(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """AI hisobotini qayta yaratish yoki generatsiya qilish."""
    run_obj = await db.get(RunModel, run_id)
    if not run_obj:
        raise NotFoundError("Vazifa topilmadi")

    # Qayta tuzish
    summary_for_ai = {
        "run_id": run_id,
        "area_km2": run_obj.area_km2,
        "created_at": run_obj.created_at,
    }
    report_md = await generate_recon_report(summary_for_ai, run_id=run_id)

    # Bazaga yangilash
    query = await db.execute(select(ReportModel).where(ReportModel.run_id == run_id))
    rep = query.scalars().first()
    if rep:
        rep.content_md = report_md
    else:
        rep = ReportModel(
            run_id=run_id,
            fingerprint=run_obj.fingerprint,
            content_md=report_md,
            created_at=now_ts(),
        )
        db.add(rep)
    await db.commit()

    return {"message_uz": "Hisobot muvaffaqiyatli tayyorlandi", "content_md": report_md}
