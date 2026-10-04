"""Termal harorat (LST) va Landsat yordamchi formulalari.

Landsat 8/9 Collection 2 Level 2 ST_B10 tayyor mahsulotidan sirt haroratini (°C) hisoblaydi.
"""

import numpy as np

from backend.app.core.constants import (
    KELVIN_OFFSET,
    LANDSAT_QA_MASK_BITS,
    LANDSAT_ST_ADD,
    LANDSAT_ST_MULT,
)


def compute_landsat_lst_celsius(st_b10_dn: np.ndarray) -> np.ndarray:
    """Landsat ST_B10 bandidan Yer sirti harorati (LST), °C.

    Formula: (DN · 0.00341802 + 149.0) − 273.15
    Band: Landsat 8/9 C2 L2 ST_B10. DN ≤ 0 yoki NaN — yaroqsiz (NaN).
    """
    with np.errstate(invalid="ignore"):
        valid = (~np.isnan(st_b10_dn)) & (st_b10_dn > 0)
        celsius = np.where(valid, st_b10_dn * LANDSAT_ST_MULT + LANDSAT_ST_ADD - KELVIN_OFFSET, np.nan)
    return celsius.astype(np.float32)


def landsat_qa_invalid_mask(qa_pixel: np.ndarray) -> np.ndarray:
    """Landsat QA_PIXEL bo'yicha yaroqsiz piksellar niqobi.

    Bitlar: 0 — fill, 1 — kengaytirilgan bulut, 2 — sirrus, 3 — bulut, 4 — bulut soyasi.
    Ulardan birortasi 1 bo'lsa yoki QA mavjud bo'lmasa (NaN) — True.
    """
    qa_nan = np.isnan(qa_pixel)
    qa = np.where(qa_nan, 0, qa_pixel).astype(np.uint16)
    bits = 0
    for b in LANDSAT_QA_MASK_BITS:
        bits |= 1 << b
    return qa_nan | ((qa & bits) != 0)
