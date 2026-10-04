"""Model kirishlari uchun belgilar to'plami (sof NumPy, I/O yo'q).

Klassik ML: (N_piksel × F_belgi) matritsa — faqat barcha belgilari yaroqli piksellar.
CV: (C × H × W) tensor — NaN o'rniga to'ldiruvchi qiymat va alohida yaroqlilik niqobi.
"""

import numpy as np


def build_feature_stack(
    arrays: dict[str, np.ndarray],
    names: list[str],
    aoi_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Belgilar matritsasi X (N × F, float32) va yaroqli piksellar niqobi (H × W, bool).

    Piksel yaroqli: barcha `names` massivlarida NaN emas va AOI ichida.
    Raises:
        KeyError: kerakli massiv yo'q bo'lsa (masalan, SAR kuzatuvi topilmagan).
    """
    stack = np.stack([np.asarray(arrays[n], dtype=np.float32) for n in names], axis=-1)
    valid = ~np.isnan(stack).any(axis=-1)
    if aoi_mask is not None:
        valid &= aoi_mask.astype(bool)
    return stack[valid], valid


def build_image_tensor(
    arrays: dict[str, np.ndarray], names: list[str], fill: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """CV modeli uchun (C × H × W) tensor va yaroqlilik niqobi (H × W)."""
    stack = np.stack([np.asarray(arrays[n], dtype=np.float32) for n in names], axis=0)
    valid = ~np.isnan(stack).any(axis=0)
    return np.nan_to_num(stack, nan=fill), valid


def unflatten(values: np.ndarray, valid: np.ndarray, fill: float = np.nan) -> np.ndarray:
    """N ta qiymatni (H × W) to'rga qaytaradi; yaroqsiz piksellar `fill` (NaN — ma'lumot yo'q)."""
    out = np.full(valid.shape, fill, dtype=np.float32)
    out[valid] = values.astype(np.float32)
    return out
