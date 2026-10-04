"""Saqlash muddati (retention).

- Yakunlangan run'lar — foydalanuvchining saqlangan maydonlari: avtomatik o'chirilmaydi,
  faqat foydalanuvchi o'zi o'chiradi (DELETE /recon/{id}). docs/DECISIONS.md, 20-qaror.
- Xato bilan tugagan run'lar 24 soatdan keyin o'chiriladi.
- DB da yozuvi yo'q kataloglar (masalan, baza fayli qo'lda o'chirilgan bo'lsa) o'chiriladi.
- 30 kundan eski API jurnallari o'chiriladi.
Server ishga tushganda va har 10 daqiqada bajariladi. Faol run hech qachon o'chirilmaydi.
"""

import asyncio

from sqlalchemy import select

from backend.app.core import config
from backend.app.core.constants import RETENTION_INTERVAL_S, RETENTION_MAX_AGE_S
from backend.app.core.telemetry import logger
from backend.app.core.time import now_ts
from backend.app.db import session as db
from backend.app.db.enums import JobStatus
from backend.app.db.models import RunModel
from backend.app.pipeline.jobs import job_manager
from backend.app.pipeline.storage import delete_run_dir
from backend.app.usage.tracker import purge_old_logs


async def purge_expired_runs(max_age_seconds: int = RETENTION_MAX_AGE_S, now: int | None = None) -> int:
    """`max_age_seconds` dan eski run'larni (fayllari va DB qatorlari bilan) o'chiradi."""
    cutoff = (now if now is not None else now_ts()) - max_age_seconds
    active = job_manager.active_run_id()
    deleted = 0
    async with db.session_scope() as s:
        old = (await s.execute(
            select(RunModel).where(RunModel.created_at < cutoff, RunModel.status == JobStatus.FAILED)
        )).scalars().all()
        for r in old:
            if r.id == active:
                continue
            delete_run_dir(r.id)
            await s.delete(r)
            deleted += 1
        if deleted:
            await s.commit()
        known = {rid for (rid,) in (await s.execute(select(RunModel.id))).all()}

    # DB da yozuvi qolmagan eski kataloglar (masalan, server to'satdan to'xtagan bo'lsa)
    if config.RUNS_DIR.exists():
        for d in config.RUNS_DIR.iterdir():
            if not d.is_dir() or not d.name.isdigit():
                continue
            rid = int(d.name)
            if rid not in known and rid != active:
                delete_run_dir(rid)
    if deleted:
        logger.info(f"Retention: {deleted} ta eski run oʻchirildi")
    return deleted


async def remove_runs_without_files() -> int:
    """Natija fayllari (summary.json) yo'qolgan yakunlangan run'larni bazadan o'chiradi (kataloglar qo'lda o'chirilsa)."""
    from backend.app.pipeline.storage import summary_path

    n = 0
    async with db.session_scope() as s:
        done = (await s.execute(select(RunModel).where(RunModel.status == JobStatus.COMPLETED))).scalars().all()
        for r in done:
            if not summary_path(r.id).exists():
                await s.delete(r)
                n += 1
        if n:
            await s.commit()
            logger.warning(f"Fayllari yoʻq {n} ta maydon bazadan oʻchirildi")
    return n


async def mark_interrupted_runs() -> int:
    """Server qayta ishga tushganda RUNNING holatida qolib ketgan run'larni o'chiradi."""
    n = 0
    async with db.session_scope() as s:
        stale = (await s.execute(select(RunModel).where(RunModel.status == JobStatus.RUNNING))).scalars().all()
        for r in stale:
            delete_run_dir(r.id)
            await s.delete(r)
            n += 1
        if n:
            await s.commit()
    return n


async def run_retention_once() -> None:
    await purge_expired_runs()
    purge_old_logs()


async def start_retention_worker(interval_s: int = RETENTION_INTERVAL_S) -> None:
    """Davriy tozalash: darhol, so'ng har `interval_s` soniyada."""
    while True:
        try:
            await run_retention_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Retention xatoligi: {e}")
        await asyncio.sleep(interval_s)
