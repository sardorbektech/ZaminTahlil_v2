"""3D ko'rinish uchun ma'lumotlar: relyef balandliklari va yer qoplami nomlari nuqtalari.

Manba — run katalogidagi o'lchangan qiymatlar (Copernicus DEM va yer qoplami tasnifi);
hech narsa interpolatsiya qilinmaydi: to'r kichraytirilganda blok o'rtachasi olinadi.
"""

import base64
import math
from typing import Any

import numpy as np
from scipy.ndimage import find_objects, label

from backend.app.core import constants as C
from backend.app.pipeline.grid import Grid, x_to_lon, y_to_lat


def block_mean(arr: np.ndarray, step: int) -> np.ndarray:
    """step×step bloklar bo'yicha NaN'siz o'rtacha (chekkadagi to'liq bo'lmagan bloklar ham hisoblanadi)."""
    if step <= 1:
        return arr.astype(np.float32)
    h, w = arr.shape
    hh, ww = math.ceil(h / step), math.ceil(w / step)
    pad = np.full((hh * step, ww * step), np.nan, dtype=np.float64)
    pad[:h, :w] = arr
    blocks = pad.reshape(hh, step, ww, step)
    with np.errstate(invalid="ignore"):
        valid = ~np.isnan(blocks)
        s = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
        n = valid.sum(axis=(1, 3))
        out = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    return out.astype(np.float32)


def terrain_payload(dem: np.ndarray, grid: Grid, max_side: int = C.TERRAIN3D_MAX_SIDE) -> dict[str, Any]:
    """Relyef to'ri: balandliklar (float32, base64, qator — shimoldan janubga), o'lchamlar va chegaralar."""
    step = max(1, math.ceil(max(grid.width, grid.height) / max_side))
    h = block_mean(dem, step)
    valid = ~np.isnan(h)
    if not valid.any():
        raise ValueError("DEM qiymatlari yoʻq")
    filled = np.where(valid, h, float(np.nanmin(h)))  # yo'q nuqtalar faqat geometriya uchun pastga tushiriladi
    lat_c = y_to_lat((grid.max_y + grid.min_y) / 2.0)
    k = math.cos(math.radians(lat_c))
    return {
        "width": int(h.shape[1]),
        "height": int(h.shape[0]),
        "step": step,
        "heights_b64": base64.b64encode(filled.astype("<f4").tobytes()).decode("ascii"),
        "valid_b64": base64.b64encode(np.packbits(valid.astype(np.uint8)).tobytes()).decode("ascii"),
        "min_m": float(np.nanmin(h)),
        "max_m": float(np.nanmax(h)),
        "size_x_m": float((grid.max_x - grid.min_x) * k),
        "size_y_m": float((grid.max_y - grid.min_y) * k),
        "bounds_latlon": grid.bounds_latlon(),
    }


def context_grid(grid: Grid) -> Grid:
    """AOI to'ri atrofidagi kengaytirilgan to'r (3D atrof ko'rinishi uchun).

    Har tomondan max(AOI tomoni, 1.5 km) qo'shiladi (umumiy tomon ≤ 40 km); piksel — DEM asl aniqligi (30 m)
    yoki tomon 512 pikseldan oshmasligi uchun kattaroq.
    """
    lat_c = y_to_lat((grid.max_y + grid.min_y) / 2.0)
    k = math.cos(math.radians(lat_c))  # proyeksiya metri → yer metri
    span_x = (grid.max_x - grid.min_x) * k
    span_y = (grid.max_y - grid.min_y) * k
    pad = max(max(span_x, span_y), C.CONTEXT3D_MIN_PAD_M)
    side_x = min(span_x + 2 * pad, C.CONTEXT3D_MAX_SIDE_M)
    side_y = min(span_y + 2 * pad, C.CONTEXT3D_MAX_SIDE_M)
    res = max(C.CONTEXT3D_DEM_RES_M, max(side_x, side_y) / C.CONTEXT3D_MAX_SIDE)
    p = res / k
    cx, cy = (grid.min_x + grid.max_x) / 2.0, (grid.min_y + grid.max_y) / 2.0
    w, h = max(2, math.ceil(side_x / res)), max(2, math.ceil(side_y / res))
    return Grid(min_x=cx - w * p / 2.0, max_y=cy + h * p / 2.0, pixel_size=p, width=w, height=h, res_m=res)


def pixel_to_lonlat(grid: Grid, row: float, col: float) -> tuple[float, float]:
    return x_to_lon(grid.min_x + (col + 0.5) * grid.pixel_size), y_to_lat(grid.max_y - (row + 0.5) * grid.pixel_size)


def label_points(
    classes: np.ndarray,
    grid: Grid,
    row_area_m2: np.ndarray,
    per_class: int = C.LABEL_MAX_PER_CLASS,
    min_pixels: int = C.LABEL_MIN_PIXELS,
) -> list[dict[str, Any]]:
    """Har bir sinfning eng katta bog'langan bo'laklari uchun nom qo'yiladigan nuqta.

    Nuqta — bo'lak ichidagi og'irlik markaziga eng yaqin piksel (shuning uchun doim o'sha sinf ustida).
    """
    out: list[dict[str, Any]] = []
    structure = np.ones((3, 3), dtype=bool)
    # Kichik bo'laklarga nom qo'yilmaydi (xarita yozuvlar bilan to'lib ketmasin)
    min_pixels = max(min_pixels, int((classes != C.CLASS_UNKNOWN).sum() * C.LABEL_MIN_AOI_FRACTION))
    for code, name in C.CLASS_LABELS_UZ.items():
        if code == C.CLASS_UNKNOWN:
            continue
        lab, n = label(classes == code, structure=structure)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel())[1:]
        order = np.argsort(sizes)[::-1][:per_class]
        slices = find_objects(lab)
        for idx in order:
            if sizes[idx] < min_pixels:
                break
            sl = slices[idx]
            ys, xs = np.nonzero(lab[sl] == idx + 1)
            ys, xs = ys + sl[0].start, xs + sl[1].start
            cy, cx = ys.mean(), xs.mean()
            j = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
            lon, lat = pixel_to_lonlat(grid, ys[j], xs[j])
            area = float(row_area_m2[ys].sum())
            out.append({
                "class_code": code,
                "label_uz": name,
                "color": C.CLASS_COLORS[code],
                "lon": lon,
                "lat": lat,
                "area_ha": round(area / 10000.0, 2),
            })
    out.sort(key=lambda d: -d["area_ha"])
    return out
