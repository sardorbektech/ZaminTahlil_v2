"""24 soatdan eski ma'lumotlarni avtomatik tozalash moduli (Retention).

Server ishga tushganda va har 10 daqiqada data/runs/ va SQLite bazasidan
24 soatdan eski bo'lgan yozuvlarni tozalaydi.
"""

import asyncio
import shutil

from sqlalchemy import select

from backend.app.core.config import RUNS_DIR
from backend.app.core.telemetry import logger
from backend.app.core.time import now_ts
from backend.app.db.models import RunModel
from backend.app.db.session import async_session_maker


async def purge_expired_runs(max_age_seconds: int = 86400) -> int:
    """24 soatdan (86400 soniya) eski vazifalarni o'chiradi."""
    cutoff_ts = now_ts() - max_age_seconds
    deleted_count = 0

    async with async_session_maker() as session:
        query = await session.execute(select(RunModel).where(RunModel.created_at < cutoff_ts))
        old_runs = query.scalars().all()

        for r in old_runs:
            run_id = r.id
            folder = RUNS_DIR / str(run_id)
            if folder.exists():
                try:
                    shutil.rmtree(folder, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Run #{run_id} fayllarini o'chirishda xato: {e}")

            await session.delete(r)
            deleted_count += 1

        if deleted_count > 0:
            await session.commit()
            logger.info(f"Retention: {deleted_count} ta 24 soatdan eski vazifa tozalandi.")

    return deleted_count


async def start_retention_worker() -> None:
    """Davriy tozalash vazifasi (har 10 daqiqada)."""
    # 1. Startup tozalashi
    try:
        await purge_expired_runs()
    except Exception as e:
        logger.warning(f"Startup retention xatoligi: {e}")

    # 2. Har 10 daqiqada (600 soniya)
    while True:
        try:
            await asyncio.sleep(600)
            await purge_expired_runs()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Retention davriy xatolik: {e}")
