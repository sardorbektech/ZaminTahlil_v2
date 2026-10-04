"""Ma'lumotlar bazasi sessiyasi va initsializatsiyasi (aiosqlite, WAL rejimi, foreign keys).

Sxema versiyasi `PRAGMA user_version` da saqlanadi. Run ma'lumotlari 24 soatdan keyin
baribir o'chiriladi, shuning uchun eski sxemali baza qayta yaratiladi (migratsiyasiz).
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import settings
from backend.app.core.run_settings import SETTINGS_FIELDS, RunSettings
from backend.app.core.telemetry import logger
from backend.app.db.models import Base, SettingsModel
from backend.app.usage.tracker import max_logged_run_id

SCHEMA_VERSION = 3


def _make_engine(url: str) -> AsyncEngine:
    eng = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.close()

    return eng


engine = _make_engine(f"sqlite+aiosqlite:///{settings.sqlite_db_path}")
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def configure_engine(url: str) -> None:
    """Boshqa bazaga ulanish (testlar uchun)."""
    global engine, async_session_maker
    engine = _make_engine(url)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def session_scope() -> AsyncSession:
    """Joriy sessiya fabrikasidan yangi sessiya ochadi."""
    return async_session_maker()


async def init_db() -> None:
    """Jadvallarni yaratadi (sxema eskirgan bo'lsa qayta yaratadi) va sozlamalar qatorini kiritadi."""
    async with engine.begin() as conn:
        version = (await conn.execute(text("PRAGMA user_version;"))).scalar() or 0
        if version != SCHEMA_VERSION:
            if version != 0:
                logger.warning(f"DB sxemasi eskirgan (v{version}); qayta yaratilmoqda.")
            await conn.run_sync(Base.metadata.drop_all)
            # Eski versiyadagi jadvallar ham o'chirilishi kerak
            for tbl in ("layer_stats", "class_areas", "weather", "reports", "layers", "scenes", "runs", "settings"):
                await conn.execute(text(f"DROP TABLE IF EXISTS {tbl};"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION};"))
            # Yangi baza: run ID lari jurnaldagi eski ID lar bilan to'qnashmasin
            last_id = max_logged_run_id()
            if last_id:
                await conn.execute(
                    text("INSERT INTO sqlite_sequence(name, seq) VALUES ('runs', :seq)"), {"seq": last_id}
                )

    async with session_scope() as session:
        row = await session.get(SettingsModel, 1)
        if row is None:
            defaults = RunSettings(
                **{k: getattr(settings, k) for k in SETTINGS_FIELDS if hasattr(settings, k)}
            )
            session.add(SettingsModel(id=1, **defaults.model_dump()))
            await session.commit()


async def load_run_settings(session: AsyncSession) -> RunSettings:
    """DB'dagi sozlamalarni tasdiqlangan model sifatida o'qiydi."""
    row = await session.get(SettingsModel, 1)
    if row is None:
        return RunSettings()
    return RunSettings(**{k: getattr(row, k) for k in SETTINGS_FIELDS})


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI marshrutlari uchun asinxron DB sessiyasi."""
    async with session_scope() as session:
        yield session
