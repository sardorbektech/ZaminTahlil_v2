"""Ilova loglari: faqat data/logs/app/ katalogidagi fayllarga yoziladi.

SIMPLE.md §14 bo'yicha terminalga hech narsa chop etilmaydi. Ishlab chiqish paytida
qaysi sensor, qaysi sana va qaysi bandlar kelayotganini terminalda ko'rish kerak bo'lsa,
`.env` da `LOG_TO_CONSOLE=true` yoqiladi (docs/DECISIONS.md, 1-qaror).
API chaqiruvlari jurnali (usage/tracker.py) hech qachon terminalga chiqmaydi.
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from backend.app.core.config import APP_LOG_DIR, settings
from backend.app.core.time import fmt_local, now_ts

logger = logging.getLogger("zamintahil")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    _file_handler = TimedRotatingFileHandler(
        APP_LOG_DIR / "app.log", when="midnight", backupCount=30, encoding="utf-8", utc=True
    )
    _file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    )
    logger.addHandler(_file_handler)

    if settings.log_to_console:
        _console = logging.StreamHandler(sys.stderr)
        _console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(_console)


def log_telemetry(sensor: str, event: str, details: str, ts: int | None = None) -> None:
    """Sun'iy yo'ldosh yoki ma'lumot hodisasini log fayliga yozadi.

    Args:
        sensor: Manba nomi (Sentinel-2, Sentinel-1, Landsat, SMAP, DEM, Ob-havo).
        event: Hodisa turi (Yuklanmoqda, Qabul qilindi, Xatolik).
        details: Tafsilotlar (scene ID, bandlar, o'lcham).
        ts: Ma'lumotning olingan vaqti (UTC epoch); bo'lmasa joriy vaqt.
    """
    time_str = fmt_local(ts if ts is not None else now_ts())
    logger.info(f"[{sensor.upper()}] {event} | {details} | Sana: {time_str}")


def log_step(step_num: int, total_steps: int, title: str, details: str = "") -> None:
    """Quvur bosqichini log fayliga yozadi."""
    det_str = f" - {details}" if details else ""
    logger.info(f"[BOSQICH {step_num}/{total_steps}] {title}{det_str}")
