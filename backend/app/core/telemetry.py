"""Tizim telemetriyasi, loglash va terminalga jonli xabarlar chiqarish moduli.

Foydalanuvchining talabiga ko'ra har bir jarayon, qaysi sun'iy yo'ldoshdan
qanday ma'lumotlar kelayotgani terminalda to'liq ko'rsatiladi.
Shuningdek, to'liq loglar data/logs/app/app.log fayliga yoziladi.
"""

import logging
import sys
from datetime import UTC, datetime

from backend.app.core.config import APP_LOG_DIR
from backend.app.core.time import fmt_local

# Asosiy logger
logger = logging.getLogger("zamintahil")
logger.setLevel(logging.INFO)

# Faylga yozuvchi handler
log_file = APP_LOG_DIR / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Terminalga chiqaruvchi handler (foydalanuvchi talabi)
console_handler = logging.StreamHandler(sys.stdout)
console_formatter = logging.Formatter("%(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)


def log_telemetry(sensor: str, event: str, details: str, ts: int | None = None) -> None:
    """Sun'iy yo'ldosh yoki tizim hodisasini terminal va logga yozadi.

    Args:
        sensor: Sun'iy yo'ldosh nomi (Sentinel-2, Sentinel-1, Landsat, SMAP, DEM, Weather).
        event: Hodisa turi (Yuklanmoqda, Qabul qilindi, Tahlil qilinmoqda, Xatolik).
        details: Qo'shimcha tafsilotlar (Scene ID, bandlar, maydon).
        ts: Ma'lumotning olingan vaqti (UTC epoch).
    """
    time_str = fmt_local(ts) if ts else fmt_local(int(datetime.now(UTC).timestamp()))
    msg = f"🛰️ [{sensor.upper()}] | {event.upper()} | {details} | Sana: {time_str}"
    logger.info(msg)


def log_step(step_num: int, total_steps: int, title: str, details: str = "") -> None:
    """Quvur bosqichini terminalga chiroyli chop etadi."""
    det_str = f" - {details}" if details else ""
    msg = f"⏳ [BOSQICH {step_num}/{total_steps}] {title}{det_str}"
    logger.info(msg)
