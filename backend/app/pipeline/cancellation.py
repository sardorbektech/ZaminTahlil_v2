"""Vazifani bekor qilish (cancellation) va resurslarni zudlik bilan tozalash moduli."""

import asyncio
import gc
import shutil

from backend.app.core.config import RUNS_DIR
from backend.app.core.telemetry import logger

_active_tasks: dict[int, asyncio.Task] = {}
_cancellation_events: dict[int, asyncio.Event] = {}


def register_active_run(run_id: int, task: asyncio.Task) -> None:
    """Faol vazifa va uning bekor qilish hodisasini ro'yxatga oladi."""
    _active_tasks[run_id] = task
    _cancellation_events[run_id] = asyncio.Event()


def unregister_active_run(run_id: int) -> None:
    """Vazifa tugagach ro'yxatdan chiqaradi."""
    _active_tasks.pop(run_id, None)
    _cancellation_events.pop(run_id, None)


def is_cancellation_requested(run_id: int) -> bool:
    """Bekor qilish so'ralganligini tekshiradi."""
    event = _cancellation_events.get(run_id)
    return event.is_set() if event else False


async def cancel_run(run_id: int) -> bool:
    """Vazifani bekor qiladi, fayllarni tozalaydi va xotirani bo'shatadi (~2 soniyada)."""
    logger.info(f"Vazifa #{run_id} bekor qilinmoqda...")

    event = _cancellation_events.get(run_id)
    if event:
        event.set()

    task = _active_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (asyncio.CancelledError, TimeoutError, Exception):
            pass

    # Vaqtinchalik fayllarni o'chirish
    run_folder = RUNS_DIR / str(run_id)
    if run_folder.exists():
        try:
            shutil.rmtree(run_folder, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Fayllarni tozalashda xatolik: {e}")

    # Xotirani zudlik bilan tozalash
    gc.collect()

    unregister_active_run(run_id)
    logger.info(f"Vazifa #{run_id} to'liq bekor qilindi va resurslar bo'shatildi.")
    return True
