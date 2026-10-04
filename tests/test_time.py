"""Vaqt funksiyalari va Asia/Tashkent mintaqasini tekshirish testlari."""

from backend.app.core.time import fmt_local, fmt_local_date, now_ts


def test_time_formatting():
    # 0 epoch (1970-01-01 00:00:00 UTC) -> Toshkentda UTC+5: 01.01.1970 05:00
    formatted = fmt_local(0)
    assert formatted == "01.01.1970 05:00"

    # None qiymat berilsa "maʼlumot yoʻq"
    assert fmt_local(None) == "maʼlumot yoʻq"
    assert fmt_local_date(None) == "maʼlumot yoʻq"

    # Hozirgi vaqt musbat butun son
    ts = now_ts()
    assert isinstance(ts, int)
    assert ts > 1700000000
