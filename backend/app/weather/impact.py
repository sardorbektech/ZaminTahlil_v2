"""Ob-havo ta'sirini tahlil qilish moduli.

Raqamli ko'rsatkichlar va sanalar bilan o'zbek tilidagi qoidali xulosalar:
yog'in vs namlik, harorat vs LST/NDVI, botqoqlanish xavfi, qorasovuq, jazirama, kuchli shamol.
"""

from typing import Any

from backend.app.core.time import fmt_local


def analyze_weather_impact(
    weather_records: list[dict[str, Any]],
    soil_moisture_trend: float | None = None,
    delta_ndvi: float | None = None,
    has_depressions: bool = False,
) -> list[dict[str, Any]]:
    """Ob-havoning hududga ta'sirini baholovchi qoidali xulosalar ro'yxatini shakllantiradi."""
    statements: list[dict[str, Any]] = []

    if not weather_records:
        return statements

    past_records = [r for r in weather_records if r.get("is_forecast") == 0]
    forecast_records = [r for r in weather_records if r.get("is_forecast") == 1]

    # 1. Yog'ingarchilik va namlik ta'siri
    total_past_rain = sum(r.get("precip_mm", 0.0) or 0.0 for r in past_records)
    if total_past_rain > 10.0:
        statements.append({
            "category": "precip_moisture",
            "severity": "info",
            "message_uz": (
                f"Soʻnggi kunlarda jami {total_past_rain:.1f} mm yogʻin kuzatildi. "
                "Bu tuproq namligini oshirib, SAR orqaga qaytish signalida oʻz aksini topgan."
            ),
        })
    elif total_past_rain < 1.0 and len(past_records) >= 24:
        statements.append({
            "category": "drought_risk",
            "severity": "warning",
            "message_uz": (
                "Kuzatilgan davrda yogʻingarchilik deyarli boʻlmadi (jami < 1 mm). "
                "Tuproqning yuqori qatlami quruq holatda saqlanmoqda."
            ),
        })

    # 2. Pastqamliklarda suv to'planish (waterlogging) xavfi
    total_forecast_rain = sum(r.get("precip_mm", 0.0) or 0.0 for r in forecast_records)
    if total_forecast_rain > 15.0 and has_depressions:
        statements.append({
            "category": "waterlogging_risk",
            "severity": "warning",
            "message_uz": (
                f"Kelgusi 5 kunda kutilayotgan {total_forecast_rain:.1f} mm yogʻin sababli "
                "relyefning pastqam (depressiya) qismlarida suv toʻplanishi va botqoqlanish xavfi mavjud."
            ),
        })

    # 3. Harorat va qorasovuq / jazirama
    min_temp = min((r.get("temp_c") for r in weather_records if r.get("temp_c") is not None), default=20.0)
    max_temp = max((r.get("temp_c") for r in weather_records if r.get("temp_c") is not None), default=25.0)

    if min_temp <= 0.0:
        frost_rec = next((r for r in weather_records if (r.get("temp_c") or 10.0) <= 0.0), None)
        f_date = fmt_local(frost_rec["ts"]) if frost_rec else "kutilayotgan davr"
        statements.append({
            "category": "frost_risk",
            "severity": "danger",
            "message_uz": f"Qorasovuq xavfi: minimal harorat {min_temp:.1f} °C ga tushishi qayd etildi ({f_date}).",
        })
    elif max_temp >= 38.0:
        statements.append({
            "category": "heat_stress",
            "severity": "warning",
            "message_uz": f"Yuqori harorat (maksimal {max_temp:.1f} °C) oʻsimliklarda termal stress keltirib chiqarishi mumkin.",
        })

    # 4. Kuchli shamol xavfi
    max_wind = max((r.get("wind_speed_ms") or 0.0 for r in weather_records), default=0.0)
    if max_wind >= 12.0:
        statements.append({
            "category": "wind_hazard",
            "severity": "warning",
            "message_uz": f"Kuchli shamol tezligi ({max_wind:.1f} m/s) tuproq eroziyasi va chang toʻzonlari xavfini oshiradi.",
        })

    # 5. O'simlik holati va vegetatsiya o'zgarishi
    if delta_ndvi is not None:
        if delta_ndvi > 0.08:
            statements.append({
                "category": "vegetation_growth",
                "severity": "success",
                "message_uz": f"NDVI oʻsishi (+{delta_ndvi:.3f}) qulay ob-havo sharoitida faol vegetatsiyani koʻrsatadi.",
            })
        elif delta_ndvi < -0.08:
            statements.append({
                "category": "vegetation_decline",
                "severity": "warning",
                "message_uz": f"NDVI pasayishi ({delta_ndvi:.3f}) namlik yetishmasligi yoki hosil yigʻib olinganidan dalolat beradi.",
            })

    return statements
