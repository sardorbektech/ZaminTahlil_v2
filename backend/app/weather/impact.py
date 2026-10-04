"""Ob-havoning hududga ta'siri: raqamlar va sanalar bilan qoidaviy o'zbekcha xulosalar (SIMPLE.md §7.5).

Har bir xulosa faqat mavjud o'lchangan/prognoz qiymatlarga tayanadi; ma'lumot yo'q bo'lsa xulosa chiqmaydi.
"""

from collections import defaultdict
from typing import Any

from backend.app.core import constants as C
from backend.app.core.time import fmt_local, fmt_local_date, local_day_start
from backend.app.db.enums import WEATHER_SOURCE_KEYS, WeatherSource


def _src(code: int) -> str:
    return WEATHER_SOURCE_KEYS.get(WeatherSource(code), "unknown")


def _sum_precip(records: list[dict[str, Any]]) -> tuple[float | None, list[str]]:
    vals = [r["precip_mm"] for r in records if r.get("precip_mm") is not None]
    if not vals:
        return None, []
    return float(sum(vals)), sorted({_src(r["source"]) for r in records if r.get("precip_mm") is not None})


def daily_precip(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Soatlik/oraliq yog'inni Toshkent kalendar kunlari bo'yicha yig'adi (manba bilan).

    Yozuv vaqti oraliq oxiri hisoblanadi; kun = mahalliy 00:00–24:00.
    """
    acc: dict[tuple[int, int], float] = defaultdict(float)
    for r in records:
        if r.get("precip_mm") is None:
            continue
        acc[(local_day_start(r["ts"]), r["source"])] += float(r["precip_mm"])
    return [
        {"day_ts": d, "source": _src(s), "precip_mm": round(v, 2)}
        for (d, s), v in sorted(acc.items())
    ]


def _first(rec: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if rec.get(k) is not None:
            return float(rec[k])
    return None


def _extreme(records: list[dict[str, Any]], key: str, fn: Any) -> dict[str, Any] | None:
    vals = [r for r in records if r.get(key) is not None]
    if not vals:
        return None
    return fn(vals, key=lambda r: r[key])


def analyze_weather_impact(
    weather_records: list[dict[str, Any]],
    chirps_daily: list[dict[str, Any]] | None = None,
    depression_pct: float | None = None,
    soil_moisture_trend: dict[str, Any] | None = None,
    vv_changes: list[dict[str, Any]] | None = None,
    ndvi_changes: list[dict[str, Any]] | None = None,
    lst_observations: list[dict[str, Any]] | None = None,
    has_depressions: bool | None = None,
) -> list[dict[str, Any]]:
    """Ob-havo ta'siri xulosalari ro'yxati.

    Qoidalar:
      1. O'tgan yog'in yig'indisi ↔ tuproq namligi (SMAP) va SAR VV o'zgarishi.
      2. Havo harorati ↔ Landsat LST (bir soat ichidagi havo harorati bilan taqqoslash).
      3. Harorat/yog'in ↔ NDVI o'zgarishi.
      4. Prognoz yog'ini ≥ 15 mm va pastqamliklar bor → botqoqlanish xavfi.
      5. Kunlik prognoz yog'ini ≥ 20 mm → kuchli yomg'ir.
      6. Harorat ≤ 0 °C → qorasovuq; ≥ 38 °C → jazirama.
      7. Shamol ≥ 12 m/s → kuchli shamol.
    """
    out: list[dict[str, Any]] = []
    past = [r for r in weather_records if not r.get("is_forecast")]
    fc = [r for r in weather_records if r.get("is_forecast")]

    # 1. O'tgan yog'in va namlik / SAR
    past_rain, past_src = _sum_precip(past)
    if chirps_daily:
        chirps_total = sum(d["precip_mm"] for d in chirps_daily if d.get("precip_mm") is not None)
    else:
        chirps_total = None
    if past_rain is not None:
        t0, t1 = min(r["ts"] for r in past), max(r["ts"] for r in past)
        period = f"{fmt_local(t0)} – {fmt_local(t1)}"
        parts = [f"{period} oraligʻida jami {past_rain:.1f} mm yogʻin ({', '.join(past_src)})."]
        if chirps_total is not None:
            parts.append(f"CHIRPS kunlik maʼlumoti boʻyicha: {chirps_total:.1f} mm.")
        sev = "info"
        cat = "precip_past"
        if past_rain >= C.WX_HEAVY_RAIN_PAST_MM:
            sev = "warning"
        elif past_rain < C.WX_DRY_PAST_MM:
            cat = "dry_period"
            parts.append("Davr deyarli quruq oʻtgan.")
        if soil_moisture_trend and soil_moisture_trend.get("available"):
            d = soil_moisture_trend["delta"]
            trend_word = "oshgan" if d > C.WX_SM_CHANGE_SIGNIFICANT else "kamaygan" if d < -C.WX_SM_CHANGE_SIGNIFICANT else "deyarli oʻzgarmagan"
            parts.append(
                f"SMAP sirt namligi {fmt_local(soil_moisture_trend['first_ts'])} dagi "
                f"{soil_moisture_trend['first']:.3f} dan {fmt_local(soil_moisture_trend['last_ts'])} dagi "
                f"{soil_moisture_trend['last']:.3f} m³/m³ gacha {trend_word} ({d:+.3f})."
            )
        for ch in vv_changes or []:
            if ch.get("mean_delta") is None:
                continue
            md = ch["mean_delta"]
            if abs(md) >= C.WX_VV_CHANGE_SIGNIFICANT_DB:
                parts.append(
                    f"Sentinel-1 VV oʻrtacha {md:+.2f} dB oʻzgargan ({fmt_local(ch['prev_ts'])} → "
                    f"{fmt_local(ch['ts'])}); bu yuza namligi yoki oʻsimlik holati oʻzgarishiga mos."
                )
        out.append({"category": cat, "severity": sev, "message_uz": " ".join(parts),
                    "values": {"past_precip_mm": round(past_rain, 2), "chirps_precip_mm": chirps_total},
                    "sources": past_src + (["chirps"] if chirps_total is not None else [])})

    elif past:
        t0, t1 = min(r["ts"] for r in past), max(r["ts"] for r in past)
        msg = f"{fmt_local(t0)} – {fmt_local(t1)} oraligʻidagi yogʻin: {C.NO_DATA_UZ}"
        msg += f" (CHIRPS boʻyicha {chirps_total:.1f} mm)." if chirps_total is not None else " (ERA5-Land hali bu kunlarni qamramagan, GFS analizida yogʻin yoʻq, CHIRPS eʼlon qilinmagan)."
        out.append({"category": "precip_past_missing", "severity": "info", "message_uz": msg,
                    "values": {"past_precip_mm": None, "chirps_precip_mm": chirps_total},
                    "sources": ["chirps"] if chirps_total is not None else []})

    # 2. Havo harorati va LST
    for obs in lst_observations or []:
        if obs.get("mean") is None:
            continue
        near = [r for r in past if r.get("temp_c") is not None and abs(r["ts"] - obs["ts"]) <= 3600]
        if not near:
            continue
        rec = min(near, key=lambda r: abs(r["ts"] - obs["ts"]))
        diff = obs["mean"] - rec["temp_c"]
        msg = (
            f"Landsat sirt harorati {fmt_local(obs['ts'])} da oʻrtacha {obs['mean']:.1f} °C, "
            f"havo harorati {rec['temp_c']:.1f} °C ({_src(rec['source'])}, {fmt_local(rec['ts'])}); farq {diff:+.1f} °C."
        )
        if diff >= C.WX_LST_AIR_DIFF_SIGNIFICANT_C:
            msg += " Yuza havodan sezilarli issiq — quruq yoki ochiq yuzalar ustunligi ehtimoli."
        out.append({"category": "lst_vs_air", "severity": "info", "message_uz": msg,
                    "values": {"lst_c": obs["mean"], "air_c": rec["temp_c"], "diff_c": round(diff, 2)},
                    "sources": ["landsat", _src(rec["source"])]})

    # 3. NDVI o'zgarishi va ob-havo
    for ch in ndvi_changes or []:
        md = ch.get("mean_delta")
        if md is None or abs(md) < C.WX_NDVI_CHANGE_SIGNIFICANT:
            continue
        between = [r for r in past if ch["prev_ts"] <= r["ts"] <= ch["ts"]]
        rain, _ = _sum_precip(between)
        tmax = _extreme(between, "temp_max_c", max)
        ctx = []
        if rain is not None:
            ctx.append(f"shu oraliqda {rain:.1f} mm yogʻin")
        if tmax is not None:
            ctx.append(f"maksimal harorat {tmax['temp_max_c']:.1f} °C")
        ctx_s = f" ({', '.join(ctx)})" if ctx else " (oraliq uchun ob-havo maʼlumoti yoʻq)"
        word = "oshdi" if md > 0 else "pasaydi"
        out.append({"category": "ndvi_change", "severity": "info" if md > 0 else "warning",
                    "message_uz": f"NDVI {fmt_local(ch['prev_ts'])} → {fmt_local(ch['ts'])} oraligʻida oʻrtacha {md:+.3f} ga {word}{ctx_s}.",
                    "values": {"delta_ndvi": md, "precip_mm": rain}, "sources": ["sentinel2"]})

    # 4–5. Prognoz yog'ini va botqoqlanish
    fc_rain, fc_src = _sum_precip(fc)
    low_areas = depression_pct if depression_pct is not None else (100.0 if has_depressions else None)
    if fc_rain is not None:
        t0, t1 = min(r["ts"] for r in fc), max(r["ts"] for r in fc)
        msg = f"{fmt_local(t0)} – {fmt_local(t1)} prognozi: jami {fc_rain:.1f} mm yogʻin ({', '.join(fc_src)})."
        sev = "info"
        cat = "precip_forecast"
        if fc_rain >= C.WX_WATERLOG_FORECAST_MM and low_areas is not None and low_areas > 0:
            cat, sev = "waterlogging_risk", "warning"
            msg += f" Pastqam joylar hududning {low_areas:.1f}% ini tashkil etadi — u yerlarda suv toʻplanishi va botqoqlanish xavfi bor."
        out.append({"category": cat, "severity": sev, "message_uz": msg,
                    "values": {"forecast_precip_mm": round(fc_rain, 2), "low_area_pct": low_areas}, "sources": fc_src})
        for d in daily_precip(fc):
            if d["precip_mm"] >= C.WX_DAILY_HEAVY_RAIN_MM:
                out.append({"category": "heavy_rain", "severity": "warning",
                            "message_uz": f"{fmt_local_date(d['day_ts'])} kuni {d['precip_mm']:.1f} mm kuchli yogʻin kutilmoqda ({d['source']}).",
                            "values": d, "sources": [d["source"]]})

    # 6. Qorasovuq va jazirama (o'tmish va prognoz alohida)
    for label, recs in (("kuzatildi", past), ("kutilmoqda", fc)):
        tmin = _extreme(recs, "temp_min_c", min) or _extreme(recs, "temp_c", min)
        if tmin is not None:
            v = _first(tmin, "temp_min_c", "temp_c")
            if v is not None and v <= C.WX_FROST_C:
                out.append({"category": "frost", "severity": "danger",
                            "message_uz": f"Qorasovuq {label}: {fmt_local(tmin['ts'])} da harorat {v:.1f} °C ({_src(tmin['source'])}).",
                            "values": {"temp_c": v, "ts": tmin["ts"]}, "sources": [_src(tmin["source"])]})
        tmax = _extreme(recs, "temp_max_c", max) or _extreme(recs, "temp_c", max)
        if tmax is not None:
            v = _first(tmax, "temp_max_c", "temp_c")
            if v is not None and v >= C.WX_HEAT_C:
                out.append({"category": "heat", "severity": "warning",
                            "message_uz": f"Jazirama {label}: {fmt_local(tmax['ts'])} da harorat {v:.1f} °C ({_src(tmax['source'])}).",
                            "values": {"temp_c": v, "ts": tmax["ts"]}, "sources": [_src(tmax["source"])]})

        # 7. Kuchli shamol
        wmax = _extreme(recs, "wind_max_ms", max) or _extreme(recs, "wind_speed_ms", max)
        if wmax is not None:
            v = _first(wmax, "wind_max_ms", "wind_speed_ms")
            if v is not None and v >= C.WX_STRONG_WIND_MS:
                out.append({"category": "strong_wind", "severity": "warning",
                            "message_uz": f"Kuchli shamol {label}: {fmt_local(wmax['ts'])} da {v:.1f} m/s ({_src(wmax['source'])}).",
                            "values": {"wind_ms": v, "ts": wmax["ts"]}, "sources": [_src(wmax["source"])]})

    if not weather_records:
        out.append({"category": "no_data", "severity": "info",
                    "message_uz": f"Ob-havo: {C.NO_DATA_UZ}.", "values": {}, "sources": []})
    return out
