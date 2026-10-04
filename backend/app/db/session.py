"""Ma'lumotlar bazasi sessiyasi va initsializatsiyasi (aiosqlite, WAL rejimi, foreign keys).

Sxema versiyasi `PRAGMA user_version` da saqlanadi.
- Baza fayli yo'q yoki bo'sh bo'lsa — jadvallar noldan yaratiladi (faylni qo'lda o'chirish xavfsiz).
- v4 dan eski sxema (saqlanadigan maydonlar va foydalanuvchilar qo'shilishidan oldingi) qayta yaratiladi.
- v4 va undan keyingilar uchun MIGRATIONS ro'yxatidagi SQL ketma-ket qo'llanadi — ma'lumot yo'qolmaydi.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
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

SCHEMA_VERSION = 4
FIRST_MIGRATABLE_VERSION = 4  # bundan eski sxemalar qayta yaratiladi

# {versiya: [SQL, ...]} — (versiya − 1) dan shu versiyaga o'tish. Masalan:
# 5: ["ALTER TABLE runs ADD COLUMN note TEXT"],
MIGRATIONS: dict[int, list[str]] = {}

LEGACY_TABLES = (
    "chat_messages", "layer_stats", "class_areas", "weather", "reports", "layers", "scenes", "runs", "users", "settings",
)


def _drop_stale_wal(db_path: str) -> None:
    """Asosiy baza fayli qo'lda o'chirilgan bo'lsa, qolgan -wal/-shm fayllarini ham o'chiradi.

    Aks holda SQLite yo'q bazaga tegishli eski WAL jurnalini yangi bo'sh bazaga qo'llashga urinadi.
    """
    if db_path == ":memory:" or Path(db_path).exists():
        return
    for suffix in ("-wal", "-shm", "-journal"):
        Path(db_path + suffix).unlink(missing_ok=True)


def _make_engine(url: str) -> AsyncEngine:
    _drop_stale_wal(url.split("///", 1)[-1])
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


async def _create_fresh(conn: Any) -> None:
    for tbl in LEGACY_TABLES:
        await conn.execute(text(f"DROP TABLE IF EXISTS {tbl};"))
    await conn.run_sync(Base.metadata.create_all)
    await conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION};"))
    # Yangi baza: run ID lari jurnaldagi va diskdagi eski ID lar bilan to'qnashmasin
    last_id = max_logged_run_id()
    if last_id:
        await conn.execute(text("INSERT INTO sqlite_sequence(name, seq) VALUES ('runs', :seq)"), {"seq": last_id})


async def init_db() -> None:
    """Jadvallarni yaratadi yoki migratsiya qiladi va sozlamalar qatorini kiritadi."""
    async with engine.begin() as conn:
        version = (await conn.execute(text("PRAGMA user_version;"))).scalar() or 0
        if version < FIRST_MIGRATABLE_VERSION:
            if version != 0:
                logger.warning(f"DB sxemasi juda eski (v{version}); qayta yaratilmoqda.")
            await _create_fresh(conn)
        elif version < SCHEMA_VERSION:
            for v in range(version + 1, SCHEMA_VERSION + 1):
                for sql in MIGRATIONS.get(v, []):
                    await conn.execute(text(sql))
                await conn.execute(text(f"PRAGMA user_version = {v};"))
                logger.info(f"DB migratsiyasi: v{v - 1} → v{v}")
        else:
            # Yangi qo'shilgan jadvallar (masalan, kelajakdagi) mavjud bo'lmasa yaratiladi
            await conn.run_sync(Base.metadata.create_all)

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
