"""Vaqt formatlash: UTC epoch → Asia/Tashkent 'DD.MM.YYYY HH:MM'."""

from datetime import UTC, datetime

from backend.app.core.time import fmt_local, fmt_local_date, local_day_start, now_ts, ts_fields


def _utc(*a: int) -> int:
    return int(datetime(*a, tzinfo=UTC).timestamp())


def test_fmt_local_tashkent_offset():
    assert fmt_local(0) == "01.01.1970 05:00"
    assert fmt_local(1790489869) == "27.09.2026 11:17"  # 06:17:49 UTC
    assert fmt_local(_utc(2026, 9, 27, 0, 30)) == "27.09.2026 05:30"
    assert fmt_local(_utc(2026, 9, 26, 19, 30)) == "27.09.2026 00:30"  # kun almashadi


def test_missing_values():
    assert fmt_local(None) == "maʼlumot yoʻq"
    assert fmt_local_date(None) == "maʼlumot yoʻq"
    assert ts_fields("acq_time", None) == {"acq_time_ts": None, "acq_time_local": "maʼlumot yoʻq"}


def test_ts_fields_and_local_day():
    f = ts_fields("t", 0)
    assert f == {"t_ts": 0, "t_local": "01.01.1970 05:00"}
    day = local_day_start(_utc(2026, 9, 26, 19, 30))  # mahalliy 27.09 00:30
    assert fmt_local(day) == "27.09.2026 00:00"
    assert isinstance(now_ts(), int)
