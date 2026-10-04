"""GEE'dan kelgan xom massivlarni fizik birliklarga o'tkazish (sof NumPy, I/O yo'q).

Niqoblangan piksellar yuklashda maxsus belgi (sentinel) bilan to'ldiriladi va bu yerda NaN ga aylanadi.
Masshtablar GEE katalogidan olingan (core/constants.py).
"""

import numpy as np

from backend.app.core import constants as C

CS_MISSING_UINT16 = 65535  # Cloud Score+ kadri topilmagan piksellar


def structured_to_dict(arr: np.ndarray) -> dict[str, np.ndarray]:
    """computePixels (NUMPY_NDARRAY) strukturali massivini {band: 2D massiv} ga ajratadi."""
    if arr.dtype.names is None:
        raise ValueError("Strukturali massiv kutilgan edi")
    return {name: np.asarray(arr[name]) for name in arr.dtype.names}


def uint_dn_to_float(dn: np.ndarray, scale: float = 1.0, offset: float = 0.0) -> np.ndarray:
    """uint16 DN ni float32 ga o'tkazadi: qiymat = DN·scale + offset; DN == 0 → NaN."""
    out = dn.astype(np.float32) * np.float32(scale) + np.float32(offset)
    out[dn == C.NODATA_UINT16] = np.nan
    return out


def float_sentinel_to_nan(arr: np.ndarray) -> np.ndarray:
    """Float massivdagi NODATA_FLOAT belgilarini NaN ga almashtiradi."""
    out = arr.astype(np.float32, copy=True)
    out[arr <= C.NODATA_FLOAT + 0.5] = np.nan
    return out


def convert_s2(raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Sentinel-2: B* = DN / 10000; cs_cdf = DN / 10000 (65535 → NaN); SCL (0 → NaN)."""
    out: dict[str, np.ndarray] = {}
    for b, v in raw.items():
        if b == "cs_cdf":
            f = v.astype(np.float32) / np.float32(C.CLOUD_SCORE_UINT_SCALE)
            f[v == CS_MISSING_UINT16] = np.nan
            out[b] = f
        elif b == "SCL":
            out[b] = uint_dn_to_float(v)
        else:
            out[b] = uint_dn_to_float(v, C.S2_SR_SCALE)
    return out


def convert_landsat(raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Landsat L2: SR_B* = DN·0.0000275 − 0.2; ST_B10 va QA_PIXEL DN ko'rinishida (0 → NaN)."""
    out: dict[str, np.ndarray] = {}
    for b, v in raw.items():
        if b.startswith("SR_B"):
            out[b] = uint_dn_to_float(v, C.LANDSAT_SR_MULT, C.LANDSAT_SR_ADD)
        else:
            out[b] = uint_dn_to_float(v)
    return out


def convert_float_product(raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Sentinel-1 (dB), DEM (m), SMAP (m³/m³): faqat belgilarni NaN ga almashtiradi."""
    return {b: float_sentinel_to_nan(v) for b, v in raw.items()}
