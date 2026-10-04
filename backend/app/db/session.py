"""Ma'lumotlar bazasi sessiyasi va initsializatsiyasi (aiosqlite WAL rejimida)."""

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.db.models import Base, SettingsModel

# aiosqlite ulanish satri
DATABASE_URL = f"sqlite+aiosqlite:///{settings.sqlite_db_path}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


# SQLite da PRAGMA foreign_keys = ON va journal_mode = WAL o'rnatish
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.close()


async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Ma'lumotlar bazasi jadvallarini yaratadi va birlamchi sozlamalarni kiritadi."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Standart sozlamalar qatori mavjudligini tekshirish
    async with async_session_maker() as session:
        result = await session.execute(text("SELECT id FROM settings WHERE id = 1;"))
        row = result.first()
        if not row:
            initial_settings = SettingsModel(
                id=1,
                lookback_days=settings.lookback_days,
                weather_past_days=settings.weather_past_days,
                weather_forecast_days=settings.weather_forecast_days,
                max_scene_cloud_pct=settings.max_scene_cloud_pct,
                cloud_score_threshold=settings.cloud_score_threshold,
                s1_orbit_pass=settings.s1_orbit_pass,
                analysis_resolution_m=settings.analysis_resolution_m,
                max_aoi_km2=settings.max_aoi_km2,
                gee_request_timeout_s=settings.gee_request_timeout_s,
                gee_max_retries=settings.gee_max_retries,
                gee_max_concurrency=settings.gee_max_concurrency,
                ai_provider=settings.ai_provider,
                ai_model=settings.ai_model,
                ai_history_size=settings.ai_history_size,
            )
            session.add(initial_settings)
            await session.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI marshrutlari uchun asinxron DB sessiyasini taqdim etuvchi generator."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
