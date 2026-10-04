"""RGB vizual xususiyatlari (tekstura, yorqinlik, xromatiklik) moduli.

Kompyuter ko'rishi (CV) modellarisiz, sof matematik massiv operatsiyalari.
"""

import numpy as np
from scipy.ndimage import uniform_filter


def compute_brightness(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """RGB optik yorqinligi (Brightness).

    Formula: (Red + Green + Blue) / 3.0
    """
    return ((red + green + blue) / 3.0).astype(np.float32)


def compute_excess_green(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Yashillik ustunligi (Excess Green Index - ExG).

    Formula: 2 * Green - Red - Blue
    O'simlik biomassasi va yashil maydonlarni optik darajada ajratadi.
    """
    return (2.0 * green - red - blue).astype(np.float32)


def compute_texture_std(img: np.ndarray, size: int = 5) -> np.ndarray:
    """Mahalliy standart chetlanish (Tekstura / G'adir-budurlik).

    Formula: sqrt(max(0, mean(img^2) - mean(img)^2)) 5x5 darcha ichida.
    Daraxtzorlar va imoratlar yuqori teksturaga, suv va sokin dalalar past teksturaga ega.
    """
    valid = ~np.isnan(img)
    filled = np.where(valid, img, np.nanmean(img))
    mean_val = uniform_filter(filled, size=size, mode="reflect")
    mean_sq = uniform_filter(filled**2, size=size, mode="reflect")
    var_val = np.maximum(mean_sq - mean_val**2, 0.0)
    texture = np.sqrt(var_val)
    return np.where(valid, texture, np.nan).astype(np.float32)
