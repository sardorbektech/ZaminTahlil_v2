"""Spektral indekslar formulalari moduli.

Sof NumPy funksiyalari, float32 massivlari, nolga bo'lishda yoki yaroqsiz piksellarda NaN qiymati.
Har bir funksiyaning docstringi formulasi va ishlatiladigan spektral bandlarini o'zbek tilida ifodalaydi.
"""

import numpy as np


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Nolga bo'lishdan himoyalangan bo'lish amali: mahraj 0 yoki juda kichik bo'lsa NaN qaytaradi."""
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(np.abs(denominator) < 1e-7, np.nan, numerator / denominator)
    return res.astype(np.float32)


def compute_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normallashtirilgan farqli vegetatsiya indeksi (NDVI).

    Formula: (NIR - Red) / (NIR + Red)
    Ishlatiladigan bandlar: Sentinel-2 B8 (NIR) va B4 (Red).
    Landsat uchun: SR_B5 (NIR) va SR_B4 (Red).
    """
    return _safe_divide(nir - red, nir + red)


def compute_evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Kengaytirilgan vegetatsiya indeksi (EVI).

    Formula: 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1)
    Ishlatiladigan bandlar: Sentinel-2 B8 (NIR), B4 (Red), B2 (Blue).
    """
    denom = nir + 6.0 * red - 7.5 * blue + 1.0
    return _safe_divide(2.5 * (nir - red), denom)


def compute_ndre(nir: np.ndarray, re1: np.ndarray) -> np.ndarray:
    """Qizil chekka vegetatsiya indeksi (NDRE).

    Formula: (NIR - RE1) / (NIR + RE1)
    Ishlatiladigan bandlar: Sentinel-2 B8A (NIR) va B5 (RedEdge-1).
    """
    return _safe_divide(nir - re1, nir + re1)


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Normallashtirilgan farqli suv indeksi (NDWI - McFeeters).

    Formula: (Green - NIR) / (Green + NIR)
    Ishlatiladigan bandlar: Sentinel-2 B3 (Green) va B8 (NIR).
    """
    return _safe_divide(green - nir, green + nir)


def compute_mndwi(green: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """Modifikatsiyalangan normallashtirilgan suv indeksi (MNDWI - Xu).

    Formula: (Green - SWIR1) / (Green + SWIR1)
    Ishlatiladigan bandlar: Sentinel-2 B3 (Green) va B11 (SWIR1).
    """
    return _safe_divide(green - swir1, green + swir1)


def compute_ndmi(nir: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """Normallashtirilgan farqli namlik indeksi (NDMI / NDII).

    Formula: (NIR - SWIR1) / (NIR + SWIR1)
    Ishlatiladigan bandlar: Sentinel-2 B8 (NIR) va B11 (SWIR1).
    """
    return _safe_divide(nir - swir1, nir + swir1)


def compute_nbr(nir: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    """Normallashtirilgan yonish nisbati (NBR).

    Formula: (NIR - SWIR2) / (NIR + SWIR2)
    Ishlatiladigan bandlar: Sentinel-2 B8 (NIR) va B12 (SWIR2).
    """
    return _safe_divide(nir - swir2, nir + swir2)


def compute_ndbi(swir1: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Normallashtirilgan qurilish/imorat indeksi (NDBI).

    Formula: (SWIR1 - NIR) / (SWIR1 + NIR)
    Ishlatiladigan bandlar: Sentinel-2 B11 (SWIR1) va B8 (NIR).
    """
    return _safe_divide(swir1 - nir, swir1 + nir)


def compute_bsi(swir1: np.ndarray, red: np.ndarray, nir: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Ochiq tuproq indeksi (Bare Soil Index - BSI).

    Formula: ((SWIR1 + Red) - (NIR + Blue)) / ((SWIR1 + Red) + (NIR + Blue))
    Ishlatiladigan bandlar: Sentinel-2 B11 (SWIR1), B4 (Red), B8 (NIR), B2 (Blue).
    """
    numerator = (swir1 + red) - (nir + blue)
    denominator = (swir1 + red) + (nir + blue)
    return _safe_divide(numerator, denominator)
