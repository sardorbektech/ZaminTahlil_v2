"""Sozlamalar API marshruti (/api/v1/settings)."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import SettingsModel
from backend.app.db.session import get_db

router = APIRouter(prefix="/settings", tags=["Sozlamalar"])


class SettingsUpdateSchema(BaseModel):
    lookback_days: int | None = None
    weather_past_days: int | None = None
    weather_forecast_days: int | None = None
    max_scene_cloud_pct: float | None = None
    cloud_score_threshold: float | None = None
    s1_orbit_pass: str | None = None
    analysis_resolution_m: float | None = None
    max_aoi_km2: float | None = None
    gee_request_timeout_s: int | None = None
    gee_max_retries: int | None = None
    gee_max_concurrency: int | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_history_size: int | None = None


@router.get("")
async def get_system_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Tizim sozlamalarini qaytaradi."""
    settings_obj = await db.get(SettingsModel, 1)
    if not settings_obj:
        return {}
    return {
        "lookback_days": settings_obj.lookback_days,
        "weather_past_days": settings_obj.weather_past_days,
        "weather_forecast_days": settings_obj.weather_forecast_days,
        "max_scene_cloud_pct": settings_obj.max_scene_cloud_pct,
        "cloud_score_threshold": settings_obj.cloud_score_threshold,
        "s1_orbit_pass": settings_obj.s1_orbit_pass,
        "analysis_resolution_m": settings_obj.analysis_resolution_m,
        "max_aoi_km2": settings_obj.max_aoi_km2,
        "gee_request_timeout_s": settings_obj.gee_request_timeout_s,
        "gee_max_retries": settings_obj.gee_max_retries,
        "gee_max_concurrency": settings_obj.gee_max_concurrency,
        "ai_provider": settings_obj.ai_provider,
        "ai_model": settings_obj.ai_model,
        "ai_history_size": settings_obj.ai_history_size,
    }


@router.put("")
async def update_system_settings(
    payload: SettingsUpdateSchema, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Tizim sozlamalarini yangilaydi."""
    settings_obj = await db.get(SettingsModel, 1)
    if not settings_obj:
        settings_obj = SettingsModel(id=1)
        db.add(settings_obj)

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if v is not None:
            setattr(settings_obj, k, v)

    await db.commit()
    return {"message_uz": "Sozlamalar muvaffaqiyatli yangilandi"}
