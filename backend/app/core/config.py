"""Ilova konfiguratsiyasi va muhit o'zgaruvchilari (pydantic-settings)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
LOGS_DIR = DATA_DIR / "logs"
API_CALLS_LOG_DIR = LOGS_DIR / "api_calls"
APP_LOG_DIR = LOGS_DIR / "app"


class Settings(BaseSettings):
    """Tizimning asosiy sozlamalari modeli."""

    # GEE Sozlamalari
    gee_project_primary: str = ""
    gee_key_file_primary: str = ""
    gee_project_secondary: str = ""
    gee_key_file_secondary: str = ""

    # AI Sozlamalari
    ai_provider: str = "openrouter"
    ai_model: str = "openrouter/free"
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ai_history_size: int = 10

    # Quvur va operatsion sozlamalar
    lookback_days: int = 10
    weather_past_days: int = 5
    weather_forecast_days: int = 5
    max_scene_cloud_pct: float = 40.0
    cloud_score_threshold: float = 0.60
    s1_orbit_pass: str = "BOTH"
    analysis_resolution_m: float = 10.0
    max_aoi_km2: float = 100.0
    gee_request_timeout_s: int = 60
    gee_max_retries: int = 3
    gee_max_concurrency: int = 6

    # Bazaga ulanish
    sqlite_db_path: str = str(DATA_DIR / "zamintahil.sqlite")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Kerakli kataloglar avtomatik yaratilishini ta'minlash
DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
API_CALLS_LOG_DIR.mkdir(parents=True, exist_ok=True)
APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
