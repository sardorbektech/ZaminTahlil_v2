"""RGB vizual xususiyatlari (yorqinlik, xromatiklik, yashillik, tekstura) moduli.

Kompyuter ko'rishi (CV) modellarisiz, sof matematik massiv operatsiyalari.
Kirish: Sentinel-2 B4 (Red), B3 (Green), B2 (Blue) aks ettirish koeffitsiyentlari (0–1).
"""

import numpy as np
from scipy.ndimage import uniform_filter

from backend.app.core.constants import TEXTURE_WINDOW


def compute_brightness(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Optik yorqinlik.

    Formula: (Red + Green + Blue) / 3
    Bandlar: B4, B3, B2.
    """
    return ((red + green + blue) / 3.0).astype(np.float32)


def compute_chromaticity_green(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Yashil xromatiklik koordinatasi (yorug'likka bog'liq bo'lmagan rang ulushi).

    Formula: g = Green / (Red + Green + Blue); yig'indi 0 bo'lsa NaN.
    Bandlar: B4, B3, B2.
    """
    total = red + green + blue
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(np.abs(total) < 1e-7, np.nan, green / total)
    return res.astype(np.float32)


def compute_excess_green(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Yashillik ustunligi (Excess Green Index, ExG).

    Formula: 2·g − r − b, bu yerda r, g, b — xromatiklik koordinatalari (X / (R+G+B)).
    Bandlar: B4, B3, B2. Yig'indi 0 bo'lsa NaN.
    """
    total = red + green + blue
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(np.abs(total) < 1e-7, np.nan, (2.0 * green - red - blue) / total)
    return res.astype(np.float32)


def compute_texture_std(img: np.ndarray, size: int = TEXTURE_WINDOW) -> np.ndarray:
    """Mahalliy standart chetlanish (tekstura).

    Formula: sqrt(max(0, E[x²] − E[x]²)) 5x5 darcha ichida, faqat yaroqli piksellar bo'yicha
    (NaN piksellar o'rtachaga qo'shilmaydi). Kirish pikseli NaN bo'lsa natija ham NaN.
    Daraxtzor va imoratlarda yuqori, suv va bir xil dalalarda past.
    """
    valid = ~np.isnan(img)
    if not np.any(valid):
        return np.full(img.shape, np.nan, dtype=np.float32)
    w = valid.astype(np.float64)
    x = np.where(valid, img, 0.0).astype(np.float64)
    n = uniform_filter(w, size=size, mode="reflect")
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = uniform_filter(x, size=size, mode="reflect") / n
        mean_sq = uniform_filter(x * x, size=size, mode="reflect") / n
    var = np.maximum(mean_sq - mean**2, 0.0)
    return np.where(valid, np.sqrt(var), np.nan).astype(np.float32)
