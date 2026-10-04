"""Termal harorat (LST) formulalari moduli.

Landsat 8/9 ST_B10 termal bandidan sirt haroratini Selsiy (°C) darajasida hisoblaydi.
"""

import numpy as np


def compute_landsat_lst_celsius(st_b10_dn: np.ndarray) -> np.ndarray:
    """Landsat 8/9 ST_B10 bandidan Yer sirti haroratini (LST) Selsiy (°C) shkalasida hisoblaydi.

    Formula: (DN * 0.00341802 + 149.0) - 273.15
    Ishlatiladigan band: Landsat 8/9 Collection 2 Tier 1 Level 2 ST_B10.
    """
    with np.errstate(invalid="ignore"):
        # Yaroqsiz yoki to'ldiruvchi (fill) piksellarni NaN ga o'tkazamiz
        valid_mask = (st_b10_dn > 0) & (~np.isnan(st_b10_dn))
        kelvin = np.where(valid_mask, st_b10_dn * 0.00341802 + 149.0, np.nan)
        celsius = np.where(valid_mask, kelvin - 273.15, np.nan)
    return celsius.astype(np.float32)
