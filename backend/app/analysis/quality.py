"""Ma'lumotlar sifati va ishonchliligi nazorati moduli.

Piksellarning yaroqliligi (valid %), bulut qoplamasi (cloud %),
Sentinel-2 va Landsat NDVI o'rtasidagi o'zaro taqqoslash (cross-check).
"""

from typing import Any

import numpy as np

from backend.app.core.constants import LOW_VALID_PIXEL_PCT_THRESHOLD
from backend.app.db.enums import QualityFlag


def evaluate_layer_quality(arr: np.ndarray, cloud_mask: np.ndarray | None = None) -> dict[str, Any]:
    """Raster qatlami sifat ko'rsatkichlarini hisoblaydi."""
    total_pixels = arr.size
    if total_pixels == 0:
        return {
            "valid_pct": 0.0,
            "cloud_pct": 0.0,
            "quality_flag": QualityFlag.LOW_CONFIDENCE,
            "is_low_confidence": True,
        }

    nan_pixels = int(np.sum(np.isnan(arr)))
    valid_pixels = total_pixels - nan_pixels
    valid_pct = (valid_pixels / total_pixels) * 100.0

    cloud_pct = 0.0
    if cloud_mask is not None:
        cloud_pixels = int(np.sum(cloud_mask > 0))
        cloud_pct = (cloud_pixels / total_pixels) * 100.0

    is_low = valid_pct < LOW_VALID_PIXEL_PCT_THRESHOLD
    flag = QualityFlag.LOW_CONFIDENCE if is_low else QualityFlag.GOOD
    if cloud_pct > 40.0:
        flag = QualityFlag.HIGH_CLOUD

    return {
        "valid_pct": round(valid_pct, 2),
        "cloud_pct": round(cloud_pct, 2),
        "quality_flag": flag,
        "is_low_confidence": is_low,
    }


def cross_check_ndvi(
    s2_ndvi: np.ndarray, landsat_ndvi: np.ndarray, time_diff_days: float
) -> dict[str, Any]:
    """Sentinel-2 va Landsat NDVI ko'rsatkichlarini o'zaro taqqoslash (3 kunlik oraliqda)."""
    valid = (~np.isnan(s2_ndvi)) & (~np.isnan(landsat_ndvi))
    if not np.any(valid):
        return {
            "available": False,
            "message_uz": "Taqqoslash uchun umumiy yaroqli piksellar mavjud emas",
        }

    diff = np.abs(s2_ndvi[valid] - landsat_ndvi[valid])
    mean_diff = float(np.mean(diff))
    max_diff = float(np.max(diff))
    corr = float(np.corrcoef(s2_ndvi[valid], landsat_ndvi[valid])[0, 1])

    is_consistent = mean_diff <= 0.15
    msg = (
        f"Sentinel-2 va Landsat NDVI muvofiqligi yuqori (oʻrtacha farq: {mean_diff:.3f})"
        if is_consistent
        else f"Diqqat: Sentinel-2 va Landsat NDVI oʻrtasida sezilarli farq mavjud ({mean_diff:.3f})"
    )

    return {
        "available": True,
        "time_diff_days": round(time_diff_days, 1),
        "mean_diff": round(mean_diff, 4),
        "max_diff": round(max_diff, 4),
        "correlation": round(corr, 4),
        "is_consistent": is_consistent,
        "message_uz": msg,
    }
