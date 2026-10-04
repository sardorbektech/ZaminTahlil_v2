"""SAR (Sentinel-1) tahlil formulalari moduli.

Lee 5x5 filtr, desibel (dB) va chiziqli birliklar, RVI va suv niqobi.
Barcha funksiyalar float32 massivlarida ishlaydi.
"""

import numpy as np
from scipy.ndimage import uniform_filter

from backend.app.core.constants import WATER_VV_MAX_DB


def db_to_linear(val_db: np.ndarray) -> np.ndarray:
    """Desibel (dB) qiymatlarini chiziqli (linear) amplituda/quvvatga o'tkazadi.

    Formula: 10 ** (val_db / 10)
    """
    return (10.0 ** (val_db / 10.0)).astype(np.float32)


def linear_to_db(val_lin: np.ndarray) -> np.ndarray:
    """Chiziqli qiymatlarni desibel (dB) ga o'tkazadi.

    Formula: 10 * log10(val_lin)
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(val_lin <= 0, np.nan, 10.0 * np.log10(val_lin))
    return res.astype(np.float32)


def lee_filter_5x5(img: np.ndarray, enl: float = 4.0) -> np.ndarray:
    """5x5 o'lchamli Lee speckle filtri (SAR shovqinini tozalash).

    Formula:
        Mahalliy o'rtacha mu va dispersiya var 5x5 darchada hisoblanadi.
        Og'irlik: W = max(0, 1 - (Cu^2 / Ci^2))
        Filtered = mu + W * (img - mu)
    Ishlatiladigan parametrlar: ENL (Equivalent Number of Looks), standart 4.0.
    """
    valid_mask = ~np.isnan(img)
    if not np.any(valid_mask):
        return img.copy()

    # NaN qiymatlarni vaqtincha to'ldirib turish
    fill_val = float(np.nanmean(img))
    filled = np.where(valid_mask, img, fill_val)

    # 5x5 o'rtacha va kvadrat o'rtacha
    mean_val = uniform_filter(filled, size=5, mode="reflect")
    mean_sq = uniform_filter(filled**2, size=5, mode="reflect")
    variance = np.maximum(mean_sq - mean_val**2, 0.0)

    # Shovqin koeffitsiyenti
    cu = 1.0 / np.sqrt(enl)
    ci_sq = np.where(mean_val > 1e-6, variance / (mean_val**2 + 1e-7), 0.0)

    # Og'irlik koeffitsiyenti
    with np.errstate(divide="ignore", invalid="ignore"):
        weights = np.where(ci_sq > cu**2, (ci_sq - cu**2) / (ci_sq + 1e-7), 0.0)
    weights = np.clip(weights, 0.0, 1.0)

    filtered = mean_val + weights * (filled - mean_val)
    filtered = np.where(valid_mask, filtered, np.nan)
    return filtered.astype(np.float32)


def compute_vh_minus_vv(vh_db: np.ndarray, vv_db: np.ndarray) -> np.ndarray:
    """VH va VV o'rtasidagi farq (dB shkalasida).

    Formula: VH - VV
    O'simlik biomassasi va strukturasi oshgan sari ushbu farq ortadi.
    """
    return (vh_db - vv_db).astype(np.float32)


def compute_rvi(vh_db: np.ndarray, vv_db: np.ndarray) -> np.ndarray:
    """Radar vegetatsiya indeksi (RVI) - chiziqli quvvat birliklarida.

    Formula: 4 * VH_linear / (VV_linear + VH_linear)
    Ishlatiladigan bandlar: Sentinel-1 IW polarizatsiyalari (VV va VH).
    """
    vh_lin = db_to_linear(vh_db)
    vv_lin = db_to_linear(vv_db)
    denom = vv_lin + vh_lin
    with np.errstate(divide="ignore", invalid="ignore"):
        rvi = np.where(denom <= 1e-7, np.nan, (4.0 * vh_lin) / denom)
    return np.clip(rvi, 0.0, 1.0).astype(np.float32)


def compute_sar_water_mask(vv_db: np.ndarray, threshold_db: float = WATER_VV_MAX_DB) -> np.ndarray:
    """SAR orqali suv yuzasini aniqlash niqobi (barcha ob-havoda ishlaydi).

    Formula: VV_db < threshold_db (odatda -15.0 dB)
    Suv yuzasi silliq bo'lgani uchun radarni o'zidan qaytaradi va qaytgan signal juda past bo'ladi.
    """
    with np.errstate(invalid="ignore"):
        mask = np.where(np.isnan(vv_db), 0.0, (vv_db < threshold_db).astype(np.float32))
    return mask
