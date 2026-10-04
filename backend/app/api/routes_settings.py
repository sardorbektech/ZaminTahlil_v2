"""Sozlamalar API (/api/v1/settings). Maxfiy qiymatlar hech qachon qaytarilmaydi."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.client import ai_client
from backend.app.core import constants as C
from backend.app.core.errors import ConflictError, ValidationAppError
from backend.app.core.run_settings import SETTINGS_FIELDS, RunSettings, RunSettingsUpdate
from backend.app.db.models import SettingsModel
from backend.app.db.session import get_db, load_run_settings
from backend.app.gee.auth import PRIMARY, SECONDARY, is_role_configured
from backend.app.pipeline.jobs import job_manager

router = APIRouter(prefix="/settings", tags=["Sozlamalar"])

FIELD_LABELS_UZ = {
    "lookback_days": "Kuzatuv davri (kun)",
    "weather_past_days": "Oʻtgan ob-havo (kun)",
    "weather_forecast_days": "Prognoz (kun)",
    "max_scene_cloud_pct": "Kadr bulutliligi chegarasi (%)",
    "cloud_score_threshold": "Cloud Score+ chegarasi",
    "s1_orbit_pass": "Sentinel-1 orbita yoʻnalishi",
    "analysis_resolution_m": "Tahlil aniqligi (m)",
    "max_aoi_km2": "Maksimal hudud (km²)",
    "gee_request_timeout_s": "GEE soʻrov muddati (s)",
    "gee_max_retries": "GEE qayta urinishlar",
    "gee_max_concurrency": "GEE parallel soʻrovlar",
    "ai_provider": "AI provayderi",
    "ai_model": "AI modeli",
    "ai_history_size": "AI xabarlar tarixi",
}


def _out(s: RunSettings) -> dict[str, Any]:
    return {
        "settings": s.model_dump(),
        "labels_uz": FIELD_LABELS_UZ,
        "limits": {
            "lookback_days": C.LOOKBACK_DAYS_RANGE,
            "weather_past_days": C.WEATHER_DAYS_RANGE,
            "weather_forecast_days": C.WEATHER_DAYS_RANGE,
            "max_scene_cloud_pct": C.CLOUD_PCT_RANGE,
            "cloud_score_threshold": C.CLOUD_SCORE_RANGE,
            "analysis_resolution_m": C.RESOLUTION_M_RANGE,
            "max_aoi_km2": C.MAX_AOI_KM2_RANGE,
            "gee_request_timeout_s": C.GEE_TIMEOUT_RANGE,
            "gee_max_retries": C.GEE_RETRIES_RANGE,
            "gee_max_concurrency": C.GEE_CONCURRENCY_RANGE,
            "ai_history_size": C.AI_HISTORY_RANGE,
        },
        "choices": {"s1_orbit_pass": C.S1_ORBIT_PASS_VALUES, "ai_provider": C.AI_PROVIDERS},
        "configured": {
            "gee_primary": is_role_configured(PRIMARY),
            "gee_secondary": is_role_configured(SECONDARY),
            **{f"ai_{k}": p.is_configured() for k, p in ai_client.providers.items()},
        },
    }


@router.get("")
async def get_system_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Joriy sozlamalar, ruxsat etilgan oraliqlar va qaysi xizmatlar sozlanganligi (kalitlarsiz)."""
    return _out(await load_run_settings(db))


@router.put("")
async def update_system_settings(payload: RunSettingsUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Sozlamalarni qisman yangilaydi (tekshiruv bilan). Vazifa bajarilayotganda — 409."""
    if job_manager.active_run_id() is not None:
        raise ConflictError("Vazifa bajarilayotganda sozlamalarni oʻzgartirib boʻlmaydi.")
    current = await load_run_settings(db)
    merged = {**current.model_dump(), **payload.model_dump(exclude_unset=True, exclude_none=True)}
    try:
        new = RunSettings(**merged)
    except ValidationError as e:
        field = str(e.errors()[0]["loc"][0]) if e.errors() else ""
        raise ValidationAppError(
            f"Notoʻgʻri qiymat: {FIELD_LABELS_UZ.get(field, field)}", code="INVALID_SETTINGS"
        ) from e
    row = await db.get(SettingsModel, 1)
    if row is None:
        row = SettingsModel(id=1, **new.model_dump())
        db.add(row)
    else:
        for k in SETTINGS_FIELDS:
            setattr(row, k, getattr(new, k))
    await db.commit()
    return {"message_uz": "Sozlamalar saqlandi", **_out(new)}
