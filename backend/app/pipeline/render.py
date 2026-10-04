"""Raster qatlamlarini PNG vizualizatsiyasi va .npz formatida saqlash moduli.

AOI tashqarisidagi yoki NaN piksellar to'liq shaffof (Alpha = 0) qilinadi.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from backend.app.core.constants import CLASS_COLORS


def array_to_rgba_png(
    arr: np.ndarray,
    kind: str,
    output_path: Path,
    aoi_mask: np.ndarray | None = None,
) -> None:
    """Numpy massivini turiga mos rang palitrasi bilan shaffof PNG ga aylantiradi."""
    height, width = arr.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    valid = ~np.isnan(arr)
    if aoi_mask is not None:
        valid &= aoi_mask.astype(bool)

    if kind == "landcover":
        # Diskret sinflar uchun ranglar
        for class_code, hex_color in CLASS_COLORS.items():
            mask = valid & (arr.astype(int) == class_code)
            if np.any(mask) and class_code != 0:
                h = hex_color.lstrip("#")
                rgb = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
                rgba[mask, 0] = rgb[0]
                rgba[mask, 1] = rgb[1]
                rgba[mask, 2] = rgb[2]
                rgba[mask, 3] = 220  # Ozgina shaffof

    elif kind in ["ndvi", "evi", "ndre"]:
        # Yashil-sariq-qizil shkalasi (-0.2 dan 0.8 gacha)
        val = np.clip((arr - (-0.1)) / 0.9, 0.0, 1.0)
        # R, G, B hisoblash
        r = np.where(val < 0.5, 240, (1.0 - val) * 2 * 240).astype(np.uint8)
        g = np.where(val >= 0.3, 220, val * 3 * 220).astype(np.uint8)
        b = np.full_like(r, 40)
        rgba[valid, 0] = r[valid]
        rgba[valid, 1] = g[valid]
        rgba[valid, 2] = b[valid]
        rgba[valid, 3] = 200

    elif kind in ["ndwi", "mndwi", "water_mask"]:
        # Suv ko'k shkalasi
        val = np.clip((arr - (-0.2)) / 0.6, 0.0, 1.0)
        rgba[valid, 0] = (30 * (1 - val)).astype(np.uint8)[valid]
        rgba[valid, 1] = (120 * val).astype(np.uint8)[valid]
        rgba[valid, 2] = (240 * val).astype(np.uint8)[valid]
        rgba[valid, 3] = 210

    elif kind == "lst":
        # Termal harorat (15 °C dan 45 °C gacha)
        val = np.clip((arr - 15.0) / 30.0, 0.0, 1.0)
        rgba[valid, 0] = (255 * val).astype(np.uint8)[valid]
        rgba[valid, 1] = (255 * (1 - np.abs(val - 0.5) * 2)).astype(np.uint8)[valid]
        rgba[valid, 2] = (255 * (1 - val)).astype(np.uint8)[valid]
        rgba[valid, 3] = 200

    else:
        # Standart oq-qora / gradient (min-max normallashtirish)
        min_v = np.nanmin(arr) if np.any(valid) else 0.0
        max_v = np.nanmax(arr) if np.any(valid) else 1.0
        diff = max_v - min_v if max_v > min_v else 1.0
        norm = np.clip((arr - min_v) / diff, 0.0, 1.0)
        gray = (norm * 255).astype(np.uint8)
        rgba[valid, 0] = gray[valid]
        rgba[valid, 1] = gray[valid]
        rgba[valid, 2] = gray[valid]
        rgba[valid, 3] = 200

    img = Image.fromarray(rgba, mode="RGBA")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")


def generate_custom_composite_png(
    r_arr: np.ndarray,
    g_arr: np.ndarray,
    b_arr: np.ndarray,
    output_path: Path,
    aoi_mask: np.ndarray | None = None,
) -> None:
    """Ixtiyoriy 3 ta band asosida RGB kompozit PNG hosil qiladi."""
    height, width = r_arr.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    valid = (~np.isnan(r_arr)) & (~np.isnan(g_arr)) & (~np.isnan(b_arr))
    if aoi_mask is not None:
        valid &= aoi_mask.astype(bool)

    def _stretch(a: np.ndarray) -> np.ndarray:
        p2 = np.nanpercentile(a[valid], 2) if np.any(valid) else 0.0
        p98 = np.nanpercentile(a[valid], 98) if np.any(valid) else 1.0
        diff = p98 - p2 if p98 > p2 else 1.0
        norm = np.clip((a - p2) / diff, 0.0, 1.0)
        return (norm * 255).astype(np.uint8)

    rgba[valid, 0] = _stretch(r_arr)[valid]
    rgba[valid, 1] = _stretch(g_arr)[valid]
    rgba[valid, 2] = _stretch(b_arr)[valid]
    rgba[valid, 3] = 255

    img = Image.fromarray(rgba, mode="RGBA")
    img.save(output_path, format="PNG")
