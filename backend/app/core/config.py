"""Ilova konfiguratsiyasi va muhit o'zgaruvchilari (pydantic-settings).

Maxfiy qiymatlar (GEE kalit fayllari, AI kalitlari) faqat `.env` faylidan o'qiladi
va hech qachon brauzerga uzatilmaydi.
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core import constants as C

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Testlar ma'lumot katalogini ZT_DATA_DIR orqali vaqtinchalik joyga yo'naltiradi
DATA_DIR = Path(os.environ.get("ZT_DATA_DIR", str(BASE_DIR / "data")))
RUNS_DIR = DATA_DIR / "runs"
LOGS_DIR = DATA_DIR / "logs"
API_CALLS_LOG_DIR = LOGS_DIR / "api_calls"
APP_LOG_DIR = LOGS_DIR / "app"


class Settings(BaseSettings):
    """Muhit sozlamalari: maxfiy kalitlar va DB'dagi sozlamalar uchun boshlang'ich qiymatlar."""

    # GEE sozlamalari
    gee_project_primary: str = ""
    gee_key_file_primary: str = ""
    gee_project_secondary: str = ""
    gee_key_file_secondary: str = ""

    # AI sozlamalari
    ai_provider: str = C.DEFAULT_AI_PROVIDER
    ai_model: str = C.DEFAULT_AI_MODEL
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ai_history_size: int = C.DEFAULT_AI_HISTORY_SIZE
    ai_request_timeout_s: int = 180

    # Quvur sozlamalari (DB'dagi `settings` qatori uchun boshlang'ich qiymatlar)
    lookback_days: int = C.DEFAULT_LOOKBACK_DAYS
    weather_past_days: int = C.DEFAULT_WEATHER_PAST_DAYS
    weather_forecast_days: int = C.DEFAULT_WEATHER_FORECAST_DAYS
    max_scene_cloud_pct: float = C.DEFAULT_MAX_SCENE_CLOUD_PCT
    cloud_score_threshold: float = C.DEFAULT_CLOUD_SCORE_THRESHOLD
    s1_orbit_pass: str = C.DEFAULT_S1_ORBIT_PASS
    analysis_resolution_m: float = C.DEFAULT_ANALYSIS_RESOLUTION_M
    max_aoi_km2: float = C.DEFAULT_MAX_AOI_KM2
    gee_request_timeout_s: int = C.DEFAULT_GEE_REQUEST_TIMEOUT_S
    gee_max_retries: int = C.DEFAULT_GEE_MAX_RETRIES
    gee_max_concurrency: int = C.DEFAULT_GEE_MAX_CONCURRENCY

    # Terminalga telemetriya chiqarish (standart: o'chiq, loglar faqat faylga yoziladi)
    log_to_console: bool = False

    # Bazaga ulanish
    sqlite_db_path: str = str(DATA_DIR / "zamintahil.sqlite")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolve_path(self, value: str) -> Path:
        """Nisbiy yo'lni loyiha ildiziga nisbatan absolyut yo'lga aylantiradi."""
        p = Path(value)
        return p if p.is_absolute() else (BASE_DIR / p)


settings = Settings()

# Kerakli kataloglar avtomatik yaratilishini ta'minlash
for _d in (DATA_DIR, RUNS_DIR, API_CALLS_LOG_DIR, APP_LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
