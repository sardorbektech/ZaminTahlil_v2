"""Relyef (DEM) morfometriyasi formulalari moduli.

Copernicus DEM (GLO-30) orqali Horn usulida nishablik va aspekt, hillshade, TRI, TPI
hamda pastqamliklarni hisoblash. Chegaradagi piksellar (3x3 darcha to'liq bo'lmagan) NaN.
"""

import numpy as np
from scipy.ndimage import uniform_filter

from backend.app.core.constants import (
    DEPRESSION_SLOPE_MAX_DEG,
    DEPRESSION_TPI_MAX,
    HILLSHADE_ALTITUDE_DEG,
    HILLSHADE_AZIMUTH_DEG,
    TPI_WINDOW,
)


def _window(dem: np.ndarray) -> tuple[np.ndarray, ...]:
    """3x3 darchaning a..i elementlari (markaz e)."""
    return (
        dem[:-2, :-2], dem[:-2, 1:-1], dem[:-2, 2:],
        dem[1:-1, :-2], dem[1:-1, 1:-1], dem[1:-1, 2:],
        dem[2:, :-2], dem[2:, 1:-1], dem[2:, 2:],
    )


def compute_slope_and_aspect_horn(
    dem: np.ndarray, cell_size_m: float = 30.0
) -> tuple[np.ndarray, np.ndarray]:
    """Horn (1981) usuli bo'yicha nishablik (daraja) va aspekt (kompas azimuti).

    Formula (3x3 darcha [a b c; d e f; g h i], qatorlar shimoldan janubga):
        dz/dx = ((c + 2f + i) − (a + 2d + g)) / (8 · cell)
        dz/dy = ((g + 2h + i) − (a + 2b + c)) / (8 · cell)
        slope = arctan(√(dz/dx² + dz/dy²)) · 180/π
        aspect = (450 − atan2(dz/dy, −dz/dx)·180/π) mod 360  (0 = shimol, 90 = sharq)
    Tekis joyda (slope = 0) aspekt aniqlanmagan — NaN.
    cell_size_m — pikselning YERDAGI o'lchami (metr).
    """
    rows, cols = dem.shape
    slope = np.full((rows, cols), np.nan, dtype=np.float32)
    aspect = np.full((rows, cols), np.nan, dtype=np.float32)
    if rows < 3 or cols < 3:
        return slope, aspect

    a, b, c, d, _e, f, g, h, i = _window(dem.astype(np.float64))
    dz_dx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / (8.0 * cell_size_m)
    dz_dy = ((g + 2.0 * h + i) - (a + 2.0 * b + c)) / (8.0 * cell_size_m)

    slope[1:-1, 1:-1] = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    asp = (450.0 - np.degrees(np.arctan2(dz_dy, -dz_dx))) % 360.0
    flat = (dz_dx == 0) & (dz_dy == 0)
    aspect[1:-1, 1:-1] = np.where(flat, np.nan, asp)
    return slope, aspect


def compute_hillshade(
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    azimuth_deg: float = HILLSHADE_AZIMUTH_DEG,
    altitude_deg: float = HILLSHADE_ALTITUDE_DEG,
) -> np.ndarray:
    """Relyef soya-yorug'lik modeli (Hillshade, 0–255).

    Formula:
        Z = radians(90 − altitude), Az = radians((360 − azimuth + 90) mod 360)
        A = radians((360 − aspect + 90) mod 360)
        shade = 255 · (cos Z · cos S + sin Z · sin S · cos(Az − A)), 0 dan kichik bo'lsa 0
    Tekis joyda (aspekt NaN) shade = 255 · cos Z. Standart: azimut 315°, balandlik 45°.
    """
    zenith = np.radians(90.0 - altitude_deg)
    az = np.radians((360.0 - azimuth_deg + 90.0) % 360.0)
    s = np.radians(slope_deg)
    a = np.radians((360.0 - np.nan_to_num(aspect_deg, nan=0.0) + 90.0) % 360.0)
    with np.errstate(invalid="ignore"):
        shade = np.cos(zenith) * np.cos(s) + np.sin(zenith) * np.sin(s) * np.cos(az - a)
        shade = np.clip(255.0 * shade, 0.0, 255.0)
    return np.where(np.isnan(slope_deg), np.nan, shade).astype(np.float32)


def compute_tri(dem: np.ndarray) -> np.ndarray:
    """Relyef g'adir-budurlik indeksi (TRI, Riley va boshq., 1999), metr.

    Formula: √(Σ (z_qo'shni − z_markaz)²) — 8 ta qo'shni bo'yicha.
    """
    rows, cols = dem.shape
    tri = np.full((rows, cols), np.nan, dtype=np.float32)
    if rows < 3 or cols < 3:
        return tri
    a, b, c, d, e, f, g, h, i = _window(dem.astype(np.float64))
    sq = sum((n - e) ** 2 for n in (a, b, c, d, f, g, h, i))
    tri[1:-1, 1:-1] = np.sqrt(sq)
    return tri


def compute_tpi(dem: np.ndarray, size: int = TPI_WINDOW) -> np.ndarray:
    """Topografik joylashuv indeksi (TPI), metr.

    Formula: z − o'rtacha(z) (size×size darcha, faqat yaroqli piksellar bo'yicha).
    Manfiy — pastqamlik/vodiy, musbat — tepalik/tizma.
    """
    valid = ~np.isnan(dem)
    if not np.any(valid):
        return np.full(dem.shape, np.nan, dtype=np.float32)
    w = valid.astype(np.float64)
    x = np.where(valid, dem, 0.0).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_local = uniform_filter(x, size=size, mode="reflect") / uniform_filter(w, size=size, mode="reflect")
    return np.where(valid, dem - mean_local, np.nan).astype(np.float32)


def compute_depressions(tpi: np.ndarray, slope_deg: np.ndarray) -> np.ndarray:
    """Suv to'planishi ehtimoli yuqori pastqamliklar niqobi (1/0, ma'lumot yo'q bo'lsa NaN).

    Formula: 1 agar TPI < −1.0 m (mahalliy chuqurlik) va slope < 3° (tekis pastlik).
    """
    with np.errstate(invalid="ignore"):
        mask = ((tpi < DEPRESSION_TPI_MAX) & (slope_deg < DEPRESSION_SLOPE_MAX_DEG)).astype(np.float32)
    mask[np.isnan(tpi) | np.isnan(slope_deg)] = np.nan
    return mask
