"""Ma'lumot sifati nazorati (SIMPLE.md §7.6).

Har bir qatlam va sana uchun: yaroqli piksel %, bulut bilan niqoblangan %, sifat bayrog'i.
Sentinel-2 va Landsat NDVI o'zaro taqqoslanadi (3 kun ichida bo'lsa).
"""

from typing import Any

import numpy as np

from backend.app.core.constants import (
    CROSS_CHECK_MAX_DAYS,
    HIGH_CLOUD_PCT_THRESHOLD,
    LOW_VALID_PIXEL_PCT_THRESHOLD,
)
from backend.app.db.enums import QualityFlag


def quality_flag_for(valid_pct: float, cloud_masked_pct: float | None) -> QualityFlag:
    """Yaroqli va bulutli ulushdan sifat bayrog'ini aniqlaydi.

    Qoidalar: 0% — NO_DATA; < 30% — LOW_CONFIDENCE ("past ishonchlilik");
    bulut ulushi > HIGH_CLOUD_PCT_THRESHOLD — HIGH_CLOUD; aks holda GOOD.
    """
    if valid_pct <= 0.0:
        return QualityFlag.NO_DATA
    if valid_pct < LOW_VALID_PIXEL_PCT_THRESHOLD:
        return QualityFlag.LOW_CONFIDENCE
    if cloud_masked_pct is not None and cloud_masked_pct > HIGH_CLOUD_PCT_THRESHOLD:
        return QualityFlag.HIGH_CLOUD
    return QualityFlag.GOOD


def evaluate_layer_quality(
    arr: np.ndarray,
    aoi_mask: np.ndarray | None = None,
    cloud_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Qatlam sifati: AOI ichidagi yaroqli (NaN bo'lmagan) va bulut bilan niqoblangan piksellar ulushi."""
    region = np.ones(arr.shape, dtype=bool) if aoi_mask is None else aoi_mask.astype(bool)
    total = int(region.sum())
    if total == 0:
        return {
            "valid_pct": 0.0,
            "cloud_masked_pct": None,
            "quality_flag": QualityFlag.NO_DATA,
            "is_low_confidence": True,
        }
    valid_pct = float(np.sum(~np.isnan(arr) & region)) / total * 100.0
    cloud_pct = None
    if cloud_mask is not None:
        cloud_pct = float(np.sum(cloud_mask.astype(bool) & region)) / total * 100.0
    flag = quality_flag_for(valid_pct, cloud_pct)
    return {
        "valid_pct": round(valid_pct, 2),
        "cloud_masked_pct": round(cloud_pct, 2) if cloud_pct is not None else None,
        "quality_flag": flag,
        "is_low_confidence": flag in (QualityFlag.LOW_CONFIDENCE, QualityFlag.NO_DATA),
    }


def cross_check_ndvi(
    s2_ndvi: np.ndarray,
    landsat_ndvi: np.ndarray,
    time_diff_days: float,
    aoi_mask: np.ndarray | None = None,
    max_days: float = CROSS_CHECK_MAX_DAYS,
) -> dict[str, Any]:
    """Sentinel-2 va Landsat NDVI ni umumiy yaroqli piksellarda taqqoslaydi.

    Natija: o'rtacha farq (S2 − Landsat), o'rtacha mutlaq farq, korrelyatsiya, piksellar soni.
    3 kundan katta oraliqda taqqoslanmaydi.
    """
    if abs(time_diff_days) > max_days:
        return {
            "available": False,
            "time_diff_days": round(time_diff_days, 2),
            "message_uz": f"Sentinel-2 va Landsat kuzatuvlari orasida {abs(time_diff_days):.1f} kun bor (> {max_days:g}).",
        }
    valid = ~np.isnan(s2_ndvi) & ~np.isnan(landsat_ndvi)
    if aoi_mask is not None:
        valid &= aoi_mask.astype(bool)
    n = int(valid.sum())
    if n == 0:
        return {
            "available": False,
            "time_diff_days": round(time_diff_days, 2),
            "message_uz": "Taqqoslash uchun umumiy yaroqli piksellar yoʻq.",
        }
    a, b = s2_ndvi[valid].astype(np.float64), landsat_ndvi[valid].astype(np.float64)
    diff = a - b
    corr = None
    if n >= 3 and np.std(a) > 0 and np.std(b) > 0:
        corr = round(float(np.corrcoef(a, b)[0, 1]), 4)
    mean_abs = float(np.mean(np.abs(diff)))
    return {
        "available": True,
        "time_diff_days": round(time_diff_days, 2),
        "pixel_count": n,
        "mean_diff": round(float(np.mean(diff)), 4),
        "mean_abs_diff": round(mean_abs, 4),
        "s2_mean": round(float(np.mean(a)), 4),
        "landsat_mean": round(float(np.mean(b)), 4),
        "correlation": corr,
        "message_uz": (
            f"Sentinel-2 va Landsat NDVI oʻrtacha mutlaq farqi {mean_abs:.3f} "
            f"({n} piksel, {abs(time_diff_days):.1f} kun oraliq)."
        ),
    }
