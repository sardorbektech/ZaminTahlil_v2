"""Vaqt bilan ishlash yordamchi funksiyalari.

Barcha vaqtlar ma'lumotlar bazasida UTC epoch soniyalari (INTEGER) sifatida saqlanadi.
Foydalanuvchiga esa Asia/Tashkent (UTC+5, yozgi vaqtsiz) mintaqasida ko'rsatiladi.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.core.constants import NO_DATA_UZ

try:
    TASHKENT_TZ: Any = ZoneInfo("Asia/Tashkent")
except Exception:
    # Windows'da tzdata o'rnatilmagan bo'lishi mumkin; Toshkentda yozgi vaqt yo'q, UTC+5 aniq
    TASHKENT_TZ = timezone(timedelta(hours=5))

LOCAL_FORMAT = "%d.%m.%Y %H:%M"


def now_ts() -> int:
    """Joriy UTC vaqtini epoch soniyalarida qaytaradi."""
    return int(datetime.now(UTC).timestamp())


def fmt_local(ts: int | float | None) -> str:
    """UTC epoch soniyasini Asia/Tashkent vaqtida 'DD.MM.YYYY HH:MM' formatiga o'tkazadi.

    Args:
        ts: UTC epoch soniyasi.

    Returns:
        Formatlangan sana-vaqt satri yoki qiymat bo'lmasa 'maʼlumot yoʻq'.
    """
    if ts is None:
        return NO_DATA_UZ
    dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(TASHKENT_TZ)
    return dt.strftime(LOCAL_FORMAT)


def fmt_local_date(ts: int | float | None) -> str:
    """UTC epoch soniyasini faqat 'DD.MM.YYYY' formatida qaytaradi."""
    if ts is None:
        return NO_DATA_UZ
    dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(TASHKENT_TZ)
    return dt.strftime("%d.%m.%Y")


def ts_fields(prefix: str, ts: int | float | None) -> dict[str, Any]:
    """API javoblari uchun `{prefix}_ts` va `{prefix}_local` juftligini qaytaradi."""
    return {
        f"{prefix}_ts": int(ts) if ts is not None else None,
        f"{prefix}_local": fmt_local(ts),
    }


def utc_day_start(ts: int) -> int:
    """Berilgan vaqt tushgan UTC kunning boshini (00:00) qaytaradi."""
    return ts - (ts % 86400)


TASHKENT_OFFSET_S = 5 * 3600  # Asia/Tashkent — doimiy UTC+5


def local_day_start(ts: int) -> int:
    """Berilgan vaqt tushgan Toshkent kunining boshini (mahalliy 00:00) UTC epochda qaytaradi."""
    return ts - ((ts + TASHKENT_OFFSET_S) % 86400)
