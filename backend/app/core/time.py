"""Vaqt bilan ishlash yordamchi funksiyalari.

Barcha vaqtlar ma'lumotlar bazasida UTC epoch soniyalari (INTEGER) sifatida saqlanadi.
Foydalanuvchiga esa Asia/Tashkent (UTC+5) vaqt mintaqasida ko'rsatiladi.
"""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
except Exception:
    TASHKENT_TZ = timezone(timedelta(hours=5))


def now_ts() -> int:
    """Joriy UTC vaqtini epoch soniyalarida qaytaradi."""
    return int(datetime.now(UTC).timestamp())


def fmt_local(ts: int | float | None) -> str:
    """UTC epoch soniyasini Asia/Tashkent vaqtida 'DD.MM.YYYY HH:MM' formatiga o'tkazadi.

    Args:
        ts: UTC epoch soniyasi.

    Returns:
        Formatlangan sana-vaqt satri yoki mavjud bo'lmasa 'maʼlumot yoʻq'.
    """
    if ts is None:
        return "maʼlumot yoʻq"
    dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(TASHKENT_TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


def fmt_local_date(ts: int | float | None) -> str:
    """UTC epoch soniyasini faqat 'DD.MM.YYYY' formatida qaytaradi."""
    if ts is None:
        return "maʼlumot yoʻq"
    dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(TASHKENT_TZ)
    return dt.strftime("%d.%m.%Y")
