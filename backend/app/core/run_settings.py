"""Foydalanuvchi sozlamalari modeli (DB'dagi yagona `settings` qatori).

Pydantic chegaralari SIMPLE.md §11 dagi oraliqlarga mos keladi.
Har bir run boshlanganda sozlamalar nusxasi (snapshot) olinadi va run davomida o'zgarmaydi.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.core import constants as C


class RunSettings(BaseModel):
    """Run uchun amaldagi sozlamalar."""

    model_config = ConfigDict(extra="forbid")

    lookback_days: int = Field(C.DEFAULT_LOOKBACK_DAYS, ge=C.LOOKBACK_DAYS_RANGE[0], le=C.LOOKBACK_DAYS_RANGE[1])
    weather_past_days: int = Field(C.DEFAULT_WEATHER_PAST_DAYS, ge=C.WEATHER_DAYS_RANGE[0], le=C.WEATHER_DAYS_RANGE[1])
    weather_forecast_days: int = Field(
        C.DEFAULT_WEATHER_FORECAST_DAYS, ge=C.WEATHER_DAYS_RANGE[0], le=C.WEATHER_DAYS_RANGE[1]
    )
    max_scene_cloud_pct: float = Field(C.DEFAULT_MAX_SCENE_CLOUD_PCT, ge=C.CLOUD_PCT_RANGE[0], le=C.CLOUD_PCT_RANGE[1])
    cloud_score_threshold: float = Field(
        C.DEFAULT_CLOUD_SCORE_THRESHOLD, ge=C.CLOUD_SCORE_RANGE[0], le=C.CLOUD_SCORE_RANGE[1]
    )
    s1_orbit_pass: Literal["BOTH", "ASCENDING", "DESCENDING"] = C.DEFAULT_S1_ORBIT_PASS
    analysis_resolution_m: float = Field(
        C.DEFAULT_ANALYSIS_RESOLUTION_M, ge=C.RESOLUTION_M_RANGE[0], le=C.RESOLUTION_M_RANGE[1]
    )
    max_aoi_km2: float = Field(C.DEFAULT_MAX_AOI_KM2, ge=C.MAX_AOI_KM2_RANGE[0], le=C.MAX_AOI_KM2_RANGE[1])
    gee_request_timeout_s: int = Field(
        C.DEFAULT_GEE_REQUEST_TIMEOUT_S, ge=C.GEE_TIMEOUT_RANGE[0], le=C.GEE_TIMEOUT_RANGE[1]
    )
    gee_max_retries: int = Field(C.DEFAULT_GEE_MAX_RETRIES, ge=C.GEE_RETRIES_RANGE[0], le=C.GEE_RETRIES_RANGE[1])
    gee_max_concurrency: int = Field(
        C.DEFAULT_GEE_MAX_CONCURRENCY, ge=C.GEE_CONCURRENCY_RANGE[0], le=C.GEE_CONCURRENCY_RANGE[1]
    )
    ai_provider: Literal["openrouter", "openai", "ollama"] = C.DEFAULT_AI_PROVIDER
    ai_model: str = Field(C.DEFAULT_AI_MODEL, min_length=1, max_length=200)
    ai_history_size: int = Field(C.DEFAULT_AI_HISTORY_SIZE, ge=C.AI_HISTORY_RANGE[0], le=C.AI_HISTORY_RANGE[1])
    landcover_analyzer: str = Field(C.DEFAULT_LANDCOVER_ANALYZER, min_length=1, max_length=64)


class RunSettingsUpdate(BaseModel):
    """PUT /settings uchun qisman yangilash modeli."""

    model_config = ConfigDict(extra="forbid")

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
    landcover_analyzer: str | None = None


SETTINGS_FIELDS = tuple(RunSettings.model_fields.keys())
